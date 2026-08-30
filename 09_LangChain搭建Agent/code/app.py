"""
app.py - LangChain 1.x 搭建 Agent 统一 Gradio 交互工作台（13 章节教学实验台）
------------------------------------------------------------------
设计原则：教学透明 —— 每一页都把「发生了什么」透出来：
- 🔍 过程透视终端：每一步（渲染/调用/拦截/检索/裁剪）实时打印，拒绝黑盒
- 模板渲染结果、并行支流输出、工具 Schema→tool_calls→执行、裁剪明细、
  脱敏对照、命中片段，全部可见
- Codex 式左右气泡会话（用户右、助手左、头像光环）
启动：uv run python app.py   访问：http://127.0.0.1:7860
"""

import os
import io
import re
import json
import time
import contextlib
from datetime import datetime

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

from langchain_core.prompts import (
    ChatPromptTemplate,
    FewShotChatMessagePromptTemplate,
    MessagesPlaceholder,
)
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnablePassthrough

from s01_model_io import get_chat_model, get_chat_model_primary
from s04_structured_output import FinancialReportAnalysis
from s05_custom_tools import calculate_equal_monthly_loan
from s06_memory_and_trimming import trim_messages, HumanMessage, AIMessage, SystemMessage
from s07_callbacks_and_tracing import PerformanceAndCostCallback, SensitiveDataRedactCallback
from s08_rag_retrieval import build_vector_store, prepare_knowledge_base, format_docs
from s09_modern_agent import build_modern_agent
from s10_context_engineering import demo_dynamic_prompt, demo_dynamic_tools, demo_store_injection
from s11_custom_middleware import demo_node_style, demo_wrap_style, demo_class_middleware
from s12_guardrails_and_testing import (
    run_self_tests, content_filter_check, pii_redact,
    demo_pii_middleware, demo_custom_guardrails,
)
from s13_smart_buyer import SmartBuyerAgent, BuyerContext

# 全局初始化
smart_buyer_agent = SmartBuyerAgent()
modern_agent = build_modern_agent()   # 1.x create_agent（原 AgentExecutor 已弃用）

# ==============================================================================
# 通用工具
# ==============================================================================

def now():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def run_demo_captured(fn):
    """运行教学演示函数，捕获 stdout（rich 输出）并清洗 ANSI 后返回文本"""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            fn()
        text = buf.getvalue()
        if not text.strip():
            text = "（该演示未产生标准输出）"
    except Exception as e:
        text = f"❌ 演示运行失败：{e}\n\n提示：涉及真实模型调用的演示需要在 .env 中配置有效的 API Key。"
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)   # 清洗 ANSI 颜色码
    return text

# ==============================================================================
# 9.1 模型 I/O
# ==============================================================================

def tab1_invoke(prompt, temp):
    log = []
    t0 = time.time()
    log.append(f"[{now()}] [1/4] 收到 Prompt（{len(prompt)} 字符），Temperature={temp}")
    log.append(f"[{now()}] [2/4] llm.invoke() 发起同步 HTTP 请求，等待模型生成…")
    try:
        llm = get_chat_model(temperature=temp)
        res = llm.invoke(prompt)
        log.append(f"[{now()}] [3/4] 收到 AIMessage（{len(res.content)} 字符），耗时 {time.time()-t0:.2f}s")
        log.append(f"[{now()}] [4/4] 提取 response_metadata → 右侧「响应元数据」面板")
        meta = json.dumps(res.response_metadata, indent=2, ensure_ascii=False)
        return res.content, meta, "\n".join(log)
    except Exception as e:
        log.append(f"[{now()}] ❌ 调用失败：{e}")
        return f"调用失败：{e}", "{}", "\n".join(log)

def tab1_stream(prompt, temp):
    llm = get_chat_model(temperature=temp)
    buffer = ""
    n_chunks = 0
    log = [f"[{now()}] [1/2] llm.stream() 建立流式连接，逐 chunk 接收："]
    log_line = "\n".join(log)
    try:
        for chunk in llm.stream(prompt):
            if chunk.content:
                n_chunks += 1
                buffer += chunk.content
                yield buffer, gr.update(), log_line
        log_line += f"\n[{now()}] [2/2] 共接收 {n_chunks} 个 chunk，拼接为完整回复 ✓"
        yield buffer, gr.update(), log_line
    except Exception as e:
        yield f"流式调用失败：{e}", gr.update(), log_line + f"\n❌ {e}"

def tab1_profile():
    llm = get_chat_model_primary()
    profile = getattr(llm, "profile", None) or {}
    keys = ["tool_calling", "structured_output", "multimodal",
            "max_input_tokens", "max_output_tokens"]
    shown = {k: profile.get(k, "（档案中无此项）") for k in keys}
    log = (f"[{now()}] [能力档案] llm.profile 读取自本地档案（数据源 models.dev），"
           f"零 Token、零网络请求\n[{now()}] 工程价值：写代码前先查档案，自动决定"
           f"「能不能绑工具 / 要不要 JSON 兜底 / 上下文窗口多大」")
    return json.dumps(shown, indent=2, ensure_ascii=False), log

# ==============================================================================
# 9.2 Prompt 模板
# ==============================================================================

TRANS_TPL = ChatPromptTemplate.from_messages([
    ("system", "你是一名精通 {domain} 领域的翻译专家，目标是将内容翻译为生动优雅的 {target_lang}。"),
    ("human", "请翻译以下文本：\n{source_text}"),
])

FEWSHOT_EXAMPLES = [
    {"input": "这个手机电池真耐用", "output": "【正面评价】续航表现优异"},
    {"input": "屏幕边缘有划痕，差评！", "output": "【负面评价】外观品控瑕疵"},
]
FEWSHOT_FINAL = ChatPromptTemplate.from_messages([
    ("system", "请按照示例对用户评论进行情感与特征分类。"),
    FewShotChatMessagePromptTemplate(
        example_prompt=ChatPromptTemplate.from_messages([("human", "{input}"), ("ai", "{output}")]),
        examples=FEWSHOT_EXAMPLES,
    ),
    ("human", "{input}"),
])

def render_messages(messages):
    return "\n".join(f"[{m.type:7s}] {m.content}" for m in messages)

def tab2_render(domain, lang, text):
    msgs = TRANS_TPL.invoke(
        {"domain": domain, "target_lang": lang, "source_text": text}).to_messages()
    log = (f"[{now()}] [1/2] ChatPromptTemplate 模板中有 3 个变量槽：{{domain}} / {{target_lang}} / {{source_text}}\n"
           f"[{now()}] [2/2] invoke(变量字典) 完成填充 → 得到强类型消息列表（见右侧）。\n"
           f"对比手写 f-string：角色由消息对象承载，模型能明确区分「人设」与「用户输入」，杜绝注入混淆。")
    return render_messages(msgs), "（本按钮免费：只渲染模板，不调用模型）", log

def tab2_translate_stream(domain, lang, text):
    msgs = TRANS_TPL.invoke(
        {"domain": domain, "target_lang": lang, "source_text": text}).to_messages()
    rendered = render_messages(msgs)
    yield rendered, "⏳ 正在调用模型…", \
        f"[{now()}] [1/3] 模板渲染完成（{len(msgs)} 条消息）\n[{now()}] [2/3] prompt | llm | parser 管道启动，流式接收："
    llm = get_chat_model()
    buffer = ""
    try:
        for chunk in llm.stream(msgs):
            if chunk.content:
                buffer += chunk.content
                yield rendered, buffer, \
                    f"[{now()}] [1/3] 模板渲染完成（{len(msgs)} 条消息）\n[{now()}] [2/3] 管道启动，已接收 {len(buffer)} 字符…"
        yield rendered, buffer, \
            f"[{now()}] [1/3] 模板渲染完成（{len(msgs)} 条消息）\n[{now()}] [2/3] 管道启动 ✓\n[{now()}] [3/3] StrOutputParser 提取纯文本 ✓"
    except Exception as e:
        yield rendered, f"调用失败：{e}", "❌ 模型调用失败，请检查 .env 的 API Key"

def tab2_fewshot(input_text):
    msgs = FEWSHOT_FINAL.invoke({"input": input_text}).to_messages()
    log = (f"[{now()}] Few-Shot 模板把「示例库」整体注入为 human/ai 交替消息对：\n"
           f"    示例 1：{FEWSHOT_EXAMPLES[0]['input']} → {FEWSHOT_EXAMPLES[0]['output']}\n"
           f"    示例 2：{FEWSHOT_EXAMPLES[1]['input']} → {FEWSHOT_EXAMPLES[1]['output']}\n"
           f"[{now()}] 大模型通过模仿示例学会输出格式——这就是少样本提示（免费演示，仅渲染）。")
    return render_messages(msgs), log

# ==============================================================================
# 9.3 LCEL 并行
# ==============================================================================

def tab3_parallel_stream(topic):
    llm = get_chat_model()
    parser = StrOutputParser()
    events = []

    def make_branch(name, tpl):
        base = ChatPromptTemplate.from_template(tpl) | llm | parser
        def run(x):
            t0 = time.time()
            events.append(f"[{now()}] ▶️ [{name}] 支流启动")
            r = base.invoke(x)
            events.append(f"[{now()}] ⏹ [{name}] 支流完成，耗时 {time.time()-t0:.2f}s")
            return r
        return RunnableLambda(run)

    parallel = RunnableParallel({
        "topic": RunnablePassthrough(),
        "praise": make_branch("赞美支流", "为主题 '{topic}' 写两句赞美诗。"),
        "roast": make_branch("吐槽支流", "为主题 '{topic}' 写两句程序员视角的犀利吐槽。"),
    })
    summary_chain = (ChatPromptTemplate.from_template(
        "【主题】：{topic}\n【赞美】：{praise}\n【吐槽】：{roast}\n请给出 20 字以内的综合点评。")
        | llm | parser)

    yield "", "", "", f"[{now()}] [阶段 1/3] RunnableParallel 同时派发两条支流（真并发，注意时间戳交错）…"
    t0 = time.time()
    try:
        res = parallel.invoke({"topic": topic})
        total = time.time() - t0
        events.append(f"[{now()}] 并行阶段总耗时 {total:.2f}s ≈ 较慢那条支流的耗时（而非两条之和）→ 这就是并发加速")
        yield res["praise"], res["roast"], \
            f"[{now()}] [阶段 2/3] 双支流完成 ✓ 汇聚节点把三路结果拼进 summary_prompt…", "\n".join(events)
        t1 = time.time()
        summary = summary_chain.invoke({"topic": topic, "praise": res["praise"], "roast": res["roast"]})
        events.append(f"[{now()}] ⏹ [汇聚] summary_prompt | llm | parser 完成，耗时 {time.time()-t1:.2f}s")
        yield res["praise"], res["roast"], summary, "\n".join(events)
    except Exception as e:
        yield f"失败：{e}", "", "", "\n".join(events) + f"\n❌ {e}"

# ==============================================================================
# 9.4 结构化输出
# ==============================================================================

SCHEMA_JSON = FinancialReportAnalysis.model_json_schema()

def tab4_extract_stream(text):
    """流式结构化提取：等待期实时反馈进度（首包 → 流式接收 → Pydantic 校验），
    不再让页面干等 8~15 秒没有动静。"""
    t0 = time.time()
    log = [f"[{now()}] [1/3] with_structured_output(Schema)：把 Pydantic 模型转成 JSON Schema 注入请求（见下方「报关单」）",
           f"[{now()}] ⏳ Function Calling 已发出，等待模型首包（通常 8~15 秒，含思考时间）…"]
    yield "⏳ 模型思考中…", "\n".join(log)
    try:
        llm = get_chat_model_primary(temperature=0)
        structured_llm = llm.with_structured_output(FinancialReportAnalysis, strict=True)
        first_at = None
        data = None
        for partial in structured_llm.stream(text):
            if first_at is None:
                first_at = time.time() - t0
                log.append(f"[{now()}] [2/3] 首包到达（{first_at:.1f}s）→ 模型开始返回字段，流式接收中…")
            data = partial
            filled = sum(1 for v in (data.model_dump() or {}).values() if v not in (None, "", []))
            yield f"⏳ 已接收 {filled} 个字段…", "\n".join(log)
        log.append(f"[{now()}] [3/3] Pydantic 校验通过 ✓（字段名/类型/取值范围全部合规）→ 强类型对象，总耗时 {time.time()-t0:.1f}s")
        yield json.dumps(data.model_dump(), indent=2, ensure_ascii=False), "\n".join(log)
    except Exception as e:
        log.append(f"❌ 提取失败：{e}")
        yield f"提取失败：{e}", "\n".join(log)

# ==============================================================================
# 9.5 自定义工具
# ==============================================================================

def tab5_schema():
    schema = calculate_equal_monthly_loan.args
    extras = getattr(calculate_equal_monthly_loan, "extras", None)
    log = (f"[{now()}] [1/2] @tool 装饰器读取函数签名 + Docstring → 自动生成 JSON Schema（右侧）\n"
           f"[{now()}] [2/2] Pydantic args_schema 是参数「卡尺」：本金 gt=0、年限 1~30、利率 0.1~20，"
           f"非法参数在进入函数体前就被拦截")
    if extras:
        log += f"\n[{now()}] 🆕 1.2+ 工具 extras（厂商专属参数，一处配置随处生效）：{json.dumps(extras, ensure_ascii=False)}"
    return json.dumps(schema, indent=2, ensure_ascii=False), log

def tab5_model_invoke_stream(principal, years, rate):
    ask = (f"我打算贷 {principal} 万元、分 {int(years)} 年还清，年化利率 {rate}%，"
           f"请帮我精确计算等额本息的每月还款额和总利息。")
    log = [f"[{now()}] [1/4] 用户自然语言：{ask}", f"[{now()}] [2/4] llm.bind_tools([工具]) 把工具声明注入请求…"]
    status = "⏳ 正在让模型决策…"
    yield status, None, "", "\n".join(log)
    try:
        llm = get_chat_model_primary(temperature=0)
        bound = llm.bind_tools([calculate_equal_monthly_loan])
        ai = bound.invoke(ask)
        if not getattr(ai, "tool_calls", None):
            log.append(f"[{now()}] ⚠️ 模型未返回 tool_calls（判断无需调用工具），直接文本回答。")
            yield ai.content, None, "", "\n".join(log)
            return
        tcs = [{"name": tc["name"], "args": tc["args"]} for tc in ai.tool_calls]
        log.append(f"[{now()}] [3/4] 模型返回 tool_calls（右侧 JSON）：它「点名」要用的工具与参数——模型只出主意，不执行代码")
        first = ai.tool_calls[0]
        result = calculate_equal_monthly_loan.invoke(first["args"])
        log.append(f"[{now()}] [4/4] 运行时执行真实函数 → 结果将作为 ToolMessage 回填给模型继续推理（create_agent 内自动完成）")
        yield (ai.content or "（模型无文本，只发起工具调用）",
               json.dumps(tcs, indent=2, ensure_ascii=False),
               str(result), "\n".join(log))
    except Exception as e:
        yield f"失败：{e}", None, "", "\n".join(log) + f"\n❌ {e}"

def tab5_direct_run(principal, years, rate):
    log = [f"[{now()}] 直接执行工具（绕过模型）：Pydantic 先校验参数边界，再进入函数体"]
    try:
        result = calculate_equal_monthly_loan.invoke({
            "principal": float(principal), "years": int(years), "annual_rate": float(rate)})
        log.append(f"[{now()}] 参数校验通过 ✓ 函数执行完成")
        return str(result), "\n".join(log)
    except Exception as e:
        log.append(f"[{now()}] ❌ 参数校验拦截：{e}")
        return f"工具执行报错：{e}", "\n".join(log)

# ==============================================================================
# 9.6 记忆裁剪
# ==============================================================================

BASE_MESSAGES = [
    SystemMessage(content="你是安全监控系统。"),
    HumanMessage(content="第1条提问：系统状态如何？"),
    AIMessage(content="系统一切正常。"),
    HumanMessage(content="第2条提问：CPU 使用率？"),
    AIMessage(content="CPU 使用率 25%。"),
    HumanMessage(content="第3条提问：内存占用？"),
    AIMessage(content="内存占用 4.2GB。"),
    HumanMessage(content="第4条提问：网络带宽？"),
    AIMessage(content="当前下行 120Mbps。"),
]

def tab6_trim(count, budget):
    msgs = BASE_MESSAGES[:int(count)]
    trimmed = trim_messages(
        msgs, max_tokens=int(budget), token_counter=len,
        strategy="last", start_on="human", include_system=True)
    kept = {(m.type, m.content) for m in trimmed}

    # 左栏：原始完整对话（裁剪前模型看到的全部历史）
    raw_lines = [f"共 {len(msgs)} 条（Token 预算 {int(budget)}）", "─" * 36]
    for i, m in enumerate(msgs):
        icon = {"system": "🧭", "human": "👤", "ai": "🤖"}.get(m.type, "💬")
        raw_lines.append(f"#{i} {icon} [{m.type:6s}] {str(m.content)[:34]}")

    # 右栏：逐条命运标注（对照视图）
    fate_lines = [f"原始 {len(msgs)} 条 → 裁剪后保留 {len(trimmed)} 条", "─" * 36]
    for i, m in enumerate(msgs):
        mark = "✅ 保留" if (m.type, m.content) in kept else "✂️ 裁掉"
        icon = {"system": "🧭", "human": "👤", "ai": "🤖"}.get(m.type, "💬")
        fate_lines.append(f"{mark}  #{i} {icon} [{m.type:6s}] {str(m.content)[:30]}")
    if len(trimmed) < len(msgs):
        fate_lines.append("─" * 36)
        fate_lines.append(f"（{len(msgs) - len(trimmed)} 条旧消息被滑出窗口：预算 {int(budget)} 只够装下最近的对话）")

    log = (f"[{now()}] 策略解读：\n"
           f"  · strategy=\"last\" —— 从最新往回保留（最近的上下文最重要）\n"
           f"  · include_system=True —— 顶层 System 人设永远不动（大脑设定不能丢）\n"
           f"  · start_on=\"human\" —— 裁完的第一条有效消息必须是 human，符合对话开启惯例\n"
           f"[{now()}] token_counter=len 是教学用的简化计数，生产环境请用 tiktoken。\n"
           f"[{now()}] 进阶：SummarizationMiddleware 会把旧消息「摘要」而非丢弃（见 9.6 课件）。")
    return "\n".join(raw_lines), "\n".join(fate_lines), log

# ==============================================================================
# 9.7 Callbacks 与脱敏
# ==============================================================================

def local_redact(text):
    text = re.sub(r"1[3-9]\d{9}", "[REDACTED_PHONE]", text)
    text = re.sub(r"\d{17}[\dXx]", "[REDACTED_ID]", text)
    text = re.sub(r"\b\d{16,19}\b", "[REDACTED_CARD]", text)
    text = re.sub(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "[REDACTED_EMAIL]", text)
    return text

def tab7_audit_stream(input_text):
    sent = local_redact(input_text)
    diff = f"原始输入：\n{input_text}\n\n{'─'*34}\n\n实际发送给模型：\n{sent}"
    log = [f"[{now()}] [1/3] 安检 X 光机：本地脱敏管道改写 Prompt（右侧对照），敏感字段 0 出境"]
    yield "", diff, "", "\n".join(log)
    try:
        cb = PerformanceAndCostCallback()
        redact_cb = SensitiveDataRedactCallback()
        chain = ChatPromptTemplate.from_template("请处理用户输入并给出建议：{input}") | get_chat_model() | StrOutputParser()
        log.append(f"[{now()}] [2/3] 黑匣子挂载：on_llm_start 计时启动 → 调用模型 → on_llm_end 记录 Token 账单")
        t0 = time.time()
        res = chain.invoke({"input": sent}, config={"callbacks": [cb, redact_cb]})
        audit = (f"耗时: {time.time()-t0:.2f}s\nPrompt Tokens: {cb.prompt_tokens}\n"
                 f"Completion Tokens: {cb.completion_tokens}\n总 Tokens: {cb.total_tokens}\n预估成本: ${cb.total_cost:.6f}")
        log.append(f"[{now()}] [3/3] 回调属性可随时读取 → 右侧「审计报表」（Callbacks 默认后台异步执行，不阻塞主流程）")
        yield res, diff, audit, "\n".join(log)
    except Exception as e:
        yield f"调用失败：{e}", diff, "", "\n".join(log) + f"\n❌ {e}"

# ==============================================================================
# 9.8 RAG
# ==============================================================================

def tab8_rag_stream(question):
    log = [f"[{now()}] [1/4] 读取内置企业规范文档并切块（RecursiveCharacterTextSplitter）…"]
    yield "", "⏳ 检索中…", "\n".join(log)
    try:
        raw_docs = prepare_knowledge_base()
        vectorstore = build_vector_store(raw_docs)
        retriever = vectorstore.as_retriever(search_kwargs={"k": 2})
        log.append(f"[{now()}] [2/4] 每块文本经 Embeddings 变成高维向量，存入 Chroma")
        log.append(f"[{now()}] [3/4] 问题向量化 → 相似度检索 Top-2 片段（智能图书索引员）：")
        chunks = retriever.invoke(question)
        frag = "\n\n".join(
            f"【片段 {i+1} · 来源: {d.metadata.get('source','?')}】\n{d.page_content.strip()[:220]}"
            for i, d in enumerate(chunks))
        yield "", frag, "\n".join(log)
        log.append(f"[{now()}] [4/4] 把片段拼进 prompt 的 {{context}} → 模型「开卷作答」（严禁脱离资料胡编）")
        prompt = ChatPromptTemplate.from_template("参考规范回答问题：\n{context}\n\n问题：{question}")
        rag_chain = ({"context": retriever | format_docs, "question": RunnablePassthrough()}
                     | prompt | get_chat_model(temperature=0.1) | StrOutputParser())
        answer = rag_chain.invoke(question)
        yield answer, frag, "\n".join(log)
    except Exception as e:
        yield f"RAG 失败：{e}", "", "\n".join(log) + f"\n❌ {e}"

# ==============================================================================
# 9.9 Modern Agent（Codex 式气泡会话 + 流式）
# ==============================================================================

def tab9_agent_chat(user_msg, history, steps_log):
    if not user_msg or not user_msg.strip():
        yield history, steps_log, ""
        return
    history = history or []
    steps_log = steps_log or ""
    lc_history = []
    for m in history:
        if m["role"] == "user":
            lc_history.append(("user", m["content"]))
        elif m["role"] == "assistant" and m["content"]:
            lc_history.append(("assistant", m["content"]))
    history = history + [{"role": "user", "content": user_msg}]

    answer = ""
    turn_steps = []
    seen_tools = {}

    def full_log():
        if not turn_steps:
            return steps_log
        return steps_log + ("\n\n" if steps_log else "") + "\n\n".join(turn_steps)

    try:
        for chunk, _meta in modern_agent.stream(
                {"messages": lc_history + [("user", user_msg)]}, stream_mode="messages"):
            for tc in (getattr(chunk, "tool_call_chunks", None) or []):
                idx = tc.get("index", 0)
                if tc.get("name"):
                    seen_tools.setdefault(idx, {"name": tc["name"], "args": ""})
                slot = seen_tools.get(idx)
                if slot is not None and tc.get("args"):
                    slot["args"] += tc["args"]
            if getattr(chunk, "type", "") == "tool":
                for slot in seen_tools.values():
                    if slot.get("args"):
                        turn_steps.append(f"🧠 调用工具: {slot['name']}\n参数: {slot['args']}")
                        slot["args"] = ""
                turn_steps.append(f"⚙️ 工具返回: {chunk.content}")
                yield (history + [{"role": "assistant", "content": answer or "🛠️ 工具执行中，请稍候…"}],
                       full_log(), "")
                continue
            content = getattr(chunk, "content", None)
            if content:
                answer += content if isinstance(content, str) else "".join(
                    c.get("text", "") for c in content if isinstance(c, dict))
                yield history + [{"role": "assistant", "content": answer}], full_log(), ""
        yield history + [{"role": "assistant", "content": answer or "（模型未返回文本）"}], full_log(), ""
    except Exception as e:
        yield history + [{"role": "assistant", "content": f"Agent 运行报错：{e}"}], full_log(), ""

# ==============================================================================
# 9.10 / 9.11 / 9.12 教学演示（捕获 stdout）
# ==============================================================================

def tab_demo(fn):
    return run_demo_captured(fn)

def tab12_local_check(text):
    hit = content_filter_check([{"role": "user", "content": text}])
    redacted = pii_redact(text)
    verdict = "🚫 拦截（命中黑名单关键词，before_agent 直接 jump_to=end，模型不会被调用）" if hit else "✅ 放行（未命中黑名单）"
    detail = json.dumps(hit, ensure_ascii=False, indent=2) if hit else "null"
    out = (f"确定性护栏判定：{verdict}\n\n拦截详情：{detail}\n\n"
           f"邮箱脱敏（确定性实现，与 PIIMiddleware redact 等价）：\n{redacted}")
    log = (f"[{now()}] [1/3] before_agent / 确定性护栏：纯代码判断（黑名单），零 Token、毫秒级\n"
           f"[{now()}] [2/3] PII 脱敏：正则改写，敏感信息不出境\n"
           f"[{now()}] [3/3] 模型性护栏（输出审查）与人类在环，请运行右侧 LLM 演示按钮")
    return out, log

# ==============================================================================
# 9.13 SmartBuyer 实战
# ==============================================================================

def tab13_buyer_chat(user_msg, history, session_id, user_id):
    if not user_msg or not user_msg.strip():
        yield history, "", ""
        return
    history = history or []
    history = history + [{"role": "user", "content": user_msg}]
    callback = PerformanceAndCostCallback()
    config = {"configurable": {"thread_id": session_id or "web_shopper"}, "callbacks": [callback]}
    kwargs = {"config": config}
    if user_id and user_id.strip():
        kwargs["context"] = BuyerContext(user_id=user_id.strip())
    answer = ""
    turn_steps = []
    seen_tools = {}

    def steps_str():
        return "\n\n".join(turn_steps)

    try:
        for chunk, _meta in smart_buyer_agent.agent.stream(
                {"messages": [("user", user_msg)]}, stream_mode="messages", **kwargs):
            for tc in (getattr(chunk, "tool_call_chunks", None) or []):
                idx = tc.get("index", 0)
                if tc.get("name"):
                    seen_tools.setdefault(idx, {"name": tc["name"], "args": ""})
                slot = seen_tools.get(idx)
                if slot is not None and tc.get("args"):
                    slot["args"] += tc["args"]
            if getattr(chunk, "type", "") == "tool":
                for slot in seen_tools.values():
                    if slot.get("args"):
                        turn_steps.append(f"👉 命中工具: {slot['name']}\n👉 参数: {slot['args']}")
                        slot["args"] = ""
                turn_steps.append(f"👉 工具返回: {str(chunk.content)[:400]}")
                yield history + [{"role": "assistant", "content": answer or "🔍 参谋正在检索避坑宝典与全网差评…"}], steps_str(), ""
                continue
            content = getattr(chunk, "content", None)
            if content:
                answer += content if isinstance(content, str) else "".join(
                    c.get("text", "") for c in content if isinstance(c, dict))
                yield history + [{"role": "assistant", "content": answer}], steps_str(), ""
        audit = f"Tokens: {callback.total_tokens} | 成本: ${callback.total_cost:.6f}"
        yield history + [{"role": "assistant", "content": answer or "（模型未返回文本）"}], steps_str(), audit
    except Exception as e:
        yield history + [{"role": "assistant", "content": f"选购参谋执行报错：{e}"}], steps_str(), ""

def tab13_clear(session_id):
    return [], "", f"🔄 会话已重置，当前 ID：{session_id or 'web_shopper'}（新会话从零开始记忆）"

def tab13_report(demand):
    try:
        report = smart_buyer_agent.generate_structured_report(demand)
        return json.dumps(report.model_dump(), indent=2, ensure_ascii=False)
    except Exception as e:
        return f"生成结构化报告失败：{e}"

# ==============================================================================
# 设计令牌与主题
# ==============================================================================

custom_css = """
/* ===== 设计令牌：第九章「实验台控制台」 ===== */
body { background:#f3f4fb; }
.gradio-container {
    --paper:#f3f4fb; --card:#ffffff; --line:#e5e7f3;
    --ink:#1b1850; --chain:#4f46e5; --spark:#7c3aed; --amber:#f59e0b; --mint:#10b981; --muted:#63668a;
    --mono:"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", Roboto, sans-serif;
    max-width: min(1560px, 97vw) !important;
    margin: 0 auto !important;
    color: var(--ink);
    background:
        radial-gradient(1100px 480px at 88% -120px, rgba(124, 58, 237, .09), transparent 62%),
        radial-gradient(900px 420px at -8% -60px, rgba(79, 70, 229, .08), transparent 58%),
        radial-gradient(800px 520px at 50% 112%, rgba(16, 185, 129, .05), transparent 60%),
        var(--paper);
    overflow-x: clip;
}
/* ===== 全局细滚动条 ===== */
.gradio-container ::-webkit-scrollbar { width:8px; height:8px; }
.gradio-container ::-webkit-scrollbar-track { background:transparent; }
.gradio-container ::-webkit-scrollbar-thumb { background:#c7cbe4; border-radius:8px; }
.gradio-container ::-webkit-scrollbar-thumb:hover { background:#aab0d6; }
/* ===== 全局输入件圆角 ===== */
.gradio-container textarea,
.gradio-container input[type="text"],
.gradio-container input[type="number"] { border-radius: 12px !important; }
/* ===== 侧边栏 ===== */
#nav-sidebar { background: linear-gradient(180deg, #f9f9ff 0%, #f0f1fa 100%) !important; border-right: 1px solid var(--line) !important; }
#nav-logo { text-align: center; padding: 16px 8px 10px 8px; }
#nav-logo h2 {
    margin: 0 0 7px 0; font-size: 1.24em; font-weight: 800; letter-spacing: 1px;
    color: #4f46e5;
    background: linear-gradient(92deg, #4f46e5 10%, #7c3aed 60%, #a855f7);
    -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
}
#nav-logo p { margin: 0; font-family: var(--mono); font-size: 0.68em; letter-spacing: 0.2em; color: var(--muted); }
#nav-radio .wrap { gap: 11px !important; padding: 4px 2px !important; }
#nav-radio label {
    background: rgba(255, 255, 255, .85); border: 1px solid #e0e3f4 !important;
    border-radius: 11px !important; padding: 9px 12px !important;
    transition: all .16s ease; cursor: pointer;
    color: var(--ink) !important; font-size: 0.9em;
    box-shadow: 0 1px 3px rgba(27, 24, 80, .07);
}
#nav-radio label:hover {
    border-color: #c7ccf5 !important; box-shadow: 0 4px 12px rgba(79, 70, 229, .12);
    transform: translateY(-1px);
}
#nav-radio label.selected {
    background: linear-gradient(120deg, #4f46e5, #7c3aed) !important;
    border-color: transparent !important;
    box-shadow: 0 6px 16px rgba(79, 70, 229, .32);
    transform: translateY(-1px);
}
#nav-radio label.selected, #nav-radio label.selected * { color: #ffffff !important; }
#nav-radio label input { display: none; }
/* ===== Hero 控制台横幅：点阵网格 + 琥珀辉光 ===== */
.hero {
    position: relative; overflow: hidden;
    display: flex; align-items: center; justify-content: space-between; gap: 24px; flex-wrap: wrap;
    background: linear-gradient(118deg, #1e1b4b 0%, #3730a3 48%, #6d28d9 100%);
    border-radius: 20px; padding: 26px 30px; margin-bottom: 18px;
    color: #f8fafc;
    box-shadow: 0 14px 38px -14px rgba(67, 56, 202, .48), inset 0 1px 0 rgba(255, 255, 255, .08);
}
.hero::before {
    content: ""; position: absolute; inset: 0; pointer-events: none;
    background-image: radial-gradient(rgba(255, 255, 255, .13) 1px, transparent 1.4px);
    background-size: 24px 24px; opacity: .45;
}
.hero::after {
    content: ""; position: absolute; width: 460px; height: 460px; right: -150px; top: -260px; pointer-events: none;
    background: radial-gradient(circle at center, rgba(252, 211, 77, .30), transparent 62%);
    filter: blur(18px);
}
.hero > * { position: relative; z-index: 1; }
.hero .eyebrow {
    display: inline-flex; align-items: center; gap: 8px;
    font-family: var(--mono); font-size: 0.72em; letter-spacing: 0.24em; color: #fcd34d !important;
    background: rgba(252, 211, 77, .10); border: 1px solid rgba(252, 211, 77, .35);
    padding: 5px 12px; border-radius: 999px; margin-bottom: 12px;
}
.hero h1 { margin: 0; font-size: clamp(1.4em, 2.4vw, 1.95em); font-weight: 800; letter-spacing: .5px; color: #ffffff; text-shadow: 0 2px 18px rgba(0, 0, 0, .25); }
.hero p { margin: 10px 0 0; max-width: 860px; color: #d6daf7 !important; font-size: 0.92em; line-height: 1.75; }
.hero-tags { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }
.hero-tags span {
    font-size: 0.76em; color: #e0e7ff !important; background: rgba(255, 255, 255, .10);
    border: 1px solid rgba(255, 255, 255, .20); padding: 4px 12px; border-radius: 999px;
    backdrop-filter: blur(4px);
}
.hero-side { display: flex; flex-direction: column; align-items: center; gap: 8px; }
.hero-chain {
    font-family: var(--mono); font-size: 0.92em; color: #e0e7ff;
    background: rgba(15, 10, 50, .35); border: 1px solid rgba(255, 255, 255, .18);
    padding: 13px 20px; border-radius: 14px; white-space: nowrap;
    max-width: 100%; overflow-x: auto;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, .08);
}
.hero-chain b { color: #fcd34d; font-weight: 700; padding: 0 2px; }
.hero-chain-cap { font-family: var(--mono); font-size: 0.68em; letter-spacing: 0.18em; color: #a5b4fc; }
/* ===== 页头说明条：编号徽章 + 公式芯片 ===== */
.tab-head {
    display: flex; gap: 15px; align-items: flex-start;
    background: linear-gradient(90deg, #ffffff 55%, #fbfbff);
    border: 1px solid var(--line); border-radius: 16px;
    padding: 14px 18px; margin-bottom: 16px;
    box-shadow: 0 1px 2px rgba(27, 24, 80, .05), 0 14px 34px -22px rgba(27, 24, 80, .16);
}
.tab-badge {
    flex: 0 0 auto; font-family: var(--mono); font-weight: 800; font-size: 1.05em; letter-spacing: .03em;
    color: #ffffff; background: linear-gradient(135deg, #4f46e5, #7c3aed);
    border-radius: 12px; padding: 9px 13px;
    box-shadow: 0 6px 16px rgba(79, 70, 229, .30);
}
.tab-body { min-width: 0; }
.tab-body h3 { margin: 0 0 4px 0; font-size: 1.12em; font-weight: 700; color: var(--ink); }
.tab-body p { margin: 0 0 8px 0; font-size: 0.87em; color: var(--muted); line-height: 1.65; }
.pipe-line {
    display: inline-block; font-family: var(--mono); font-size: 0.78em; color: #4338ca;
    background: #eef0fe; border: 1px solid #dfe3fc; border-radius: 8px; padding: 4px 12px;
    box-shadow: inset 0 1px 0 #ffffff;
}
.pipe-line::before { content: "λ "; color: #7c3aed; font-weight: 700; }
.pipe-line b { color: #b45309; font-weight: 700; }
@media (max-width: 760px) { .tab-head { flex-direction: column; } }
/* ===== 过程透视终端：样式表末尾统一 rules（避免被 dedupe 置为 initial，见文件尾） ===== */
.console .label-wrap span::before { content: "▍ "; color: #34d399; }
.console ::-webkit-scrollbar-thumb { background: #2c3a5c; }
/* ===== 卡片：白底浮卡 + 更清晰的边界 ===== */
.col-card {
    display: flex; flex-direction: column; row-gap: 12px !important;
    background: var(--card); border: 1.5px solid #d3d7ee; border-radius: 16px;
    padding: 14px 16px 16px 16px;
    box-shadow: 0 2px 6px rgba(27, 24, 80, .07), 0 14px 34px -20px rgba(27, 24, 80, .16);
}
/* 卡片与相邻组件拉开间距，避免按钮/卡片贴在一起 */
.col-card { margin-bottom: 10px; }
.gradio-container .gap-normal { gap: 14px !important; }
.col-card > :last-child { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; }
.col-card > :last-child > * { flex: 1 1 auto; min-height: 0; }
.col-card > :last-child label { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; }
.col-card > :last-child textarea { flex: 1 1 auto; min-height: 150px; resize: none !important; }
.col-card > :last-child .cm-editor,
.col-card > :last-child .CodeMirror { height: 100% !important; }
.col-card textarea,
.col-card input[type="text"],
.col-card input[type="number"] {
    background: #f8f9fe !important; border-color: #e4e7f5 !important;
}
.col-card textarea:focus,
.col-card input[type="text"]:focus,
.col-card input[type="number"]:focus {
    background: #ffffff !important; border-color: #6366f1 !important;
    box-shadow: 0 0 0 3px rgba(99, 102, 241, .15) !important;
}
#log-9 textarea { height: calc(62vh + 60px) !important; min-height: 320px; }
#log-13 textarea { height: calc(50vh + 100px) !important; min-height: 240px; }
/* ===== 按钮（渐变主按钮紧凑版，与卡片明确分隔） ===== */
.gradio-container button.primary {
    background: linear-gradient(135deg, #4f46e5, #7c3aed) !important;
    border: none !important; color: #ffffff !important; font-weight: 600 !important;
    letter-spacing: 0.02em;
    box-shadow: 0 3px 10px rgba(79, 70, 229, 0.26);
    transition: transform .15s ease, box-shadow .15s ease, filter .15s ease;
}
.gradio-container button.primary:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 16px rgba(79, 70, 229, 0.34);
    filter: saturate(1.08);
}
.gradio-container button.primary:active { transform: translateY(0); box-shadow: 0 2px 8px rgba(79, 70, 229, 0.26); }
.gradio-container button.secondary {
    background: #ffffff !important;
    border: 1px solid #d5d8ec !important; color: #312e81 !important; font-weight: 500;
    box-shadow: 0 1px 3px rgba(27, 24, 80, 0.07) !important;
    transition: all .15s ease;
}
.gradio-container button.secondary:hover {
    border-color: #a5b4fc !important; background: #eef2ff !important;
    color: #4338ca !important; box-shadow: 0 2px 8px rgba(79, 70, 229, 0.10) !important;
}
/* 默认按钮尺寸收紧：内边距与高度都下调，避免撑成大色块 */
.gradio-container button.lg { padding: 6px 14px !important; font-size: 0.88em !important; border-radius: 9px !important; min-height: 0 !important; }
.gradio-container button.sm { border-radius: 8px !important; padding: 5px 12px !important; font-size: 0.86em !important; min-height: 0 !important; }
.gradio-container .gr-button-block { width: 100% !important; margin: 0 !important; }
/* ===== 按钮动作行：多按钮并排、行内自适应宽度、间距紧凑 ===== */
.btn-row { gap: 8px !important; align-items: center !important; margin: 2px 0 10px 0 !important; }
.btn-row button {
    width: auto !important; min-width: 0 !important; flex: 0 0 auto !important;
    padding: 6px 14px !important; font-size: 0.86em !important; min-height: 0 !important;
}
/* 右下角贴附：按钮行右对齐、紧贴输入框下缘 */
.btn-row.tail { justify-content: flex-end; margin: 8px 0 2px 0 !important; }
.btn-row.tail button { padding: 8px 18px !important; font-size: 0.92em !important; }
/* 等分动作行：按钮放大、各占一列（与下方三卡对齐） */
.btn-row.split { gap: 12px !important; margin: 2px 0 12px 0 !important; }
.btn-row.split button { flex: 1 1 0 !important; padding: 10px 14px !important; font-size: 0.95em !important; }
/* ===== 输入单元：外壳即输入框，按钮悬浮在框内右下角 ===== */
.input-unit {
    background: var(--card); border: 1.5px solid #d3d7ee; border-radius: 16px;
    padding: 2px 6px 6px 6px; margin-bottom: 10px;
    box-shadow: 0 2px 6px rgba(27, 24, 80, .07), 0 14px 34px -20px rgba(27, 24, 80, .16);
}
.input-unit:focus-within { border-color: #6366f1; }
/* 输入框自身隐形：外框就是唯一边界，按钮才能「长在框里」 */
.input-unit label.container { border: none !important; background: transparent !important; box-shadow: none !important; }
.input-unit textarea,
.input-unit input[type="text"],
.input-unit input[type="number"] {
    border: none !important; background: transparent !important; box-shadow: none !important;
}
.input-unit .btn-row { margin-bottom: 0 !important; }
.input-unit .btn-row.tail { margin: 0 8px 2px 0 !important; }
/* ===== 虚线次级框：滑杆等控制件区块 ===== */
.dashed-zone {
    border: 1.5px dashed #c9cff2 !important; border-radius: 14px !important;
    background: rgba(248, 249, 254, .6) !important;
    padding: 10px 12px !important;
}
/* ===== 输入单元内容垂直居中（滑杆页等无文本框场景） ===== */
.input-unit.center-content { display: flex; flex-direction: column; justify-content: center; }
/* ===== 输入单元为弹性列时，输入区吃满剩余高度，按钮钉在框内右下 ===== */
.input-unit.fill { display: flex; flex-direction: column; }
.input-unit.fill > :first-child { flex: 1 1 auto !important; min-height: 0 !important; }
/* center-content + fill 组合：滑杆等控件组垂直居中，按钮行仍钉在最底部 */
.input-unit.fill.center-content { justify-content: flex-start; }
.input-unit.fill.center-content > :nth-child(2) { margin-top: auto !important; }
.input-unit.fill label.container { height: 100% !important; display: flex; flex-direction: column; }
.input-unit.fill textarea { flex: 1 1 auto !important; height: 100% !important; resize: none !important; }
/* 灰块修复：fill 拉伸时 text-container 自带的浅灰底/圆角会露出来 */
.input-unit.fill .input-container,
.input-unit.fill .text-container,
.input-unit.fill .wrap,
.input-unit.fill .form,
.input-unit.fill .block:not(.input-unit) {
    background: transparent !important; border: none !important; box-shadow: none !important;
}
/* 兜底：input-unit 内任何直接子层不允许自带背景 */
.input-unit > div > div { background: transparent !important; }
.input-unit.fill .btn-row.tail { flex: 0 0 auto !important; margin-top: auto !important; }
/* ===== 聊天输入条：外壳即框（9.9/9.13），发送/清空嵌在框内右下 ===== */
.chat-input-unit {
    background: var(--card); border: 1.5px solid #d3d7ee; border-radius: 16px;
    padding: 6px 10px 8px 12px; margin-bottom: 10px;
    box-shadow: 0 2px 6px rgba(27, 24, 80, .07), 0 14px 34px -20px rgba(27, 24, 80, .16);
}
.chat-input-unit:focus-within { border-color: #6366f1; }
.chat-input-unit label.container { border: none !important; background: transparent !important; box-shadow: none !important; }
.chat-input-unit textarea {
    border: none !important; background: transparent !important; box-shadow: none !important;
    padding: 8px 4px !important;
}
/* 卡片内按钮行不参与纵向拉伸（修复卡片尾部大片空白） */
.col-card > .btn-row:last-child { flex: 0 0 auto !important; }
/* 兼容旧类名（若有遗留）：同样并排 */
.btn-stack { row-gap: 8px !important; }
.btn-stack button {
    width: auto !important; min-width: 0 !important;
    align-self: flex-start !important;
    padding: 6px 14px !important; font-size: 0.86em !important;
    min-height: 0 !important;
}
/* ===== 会话窗口（Codex 式气泡，无头像版） ===== */
#chat-9 .bubble, #chat-13 .bubble {
    border-radius: 16px !important;
    padding: 10px 16px !important;
    border: 1px solid #e8eaf6;
    box-shadow: 0 1px 3px rgba(30, 27, 75, 0.08);
    font-size: 0.95em; line-height: 1.68;
    max-width: min(86%, 760px);
}
#chat-9 .bubble.bot, #chat-13 .bubble.bot,
#chat-9 .bot-row .bubble, #chat-13 .bot-row .bubble {
    background: #ffffff !important; border-top-left-radius: 5px !important;
}
#chat-9 .bubble.user, #chat-13 .bubble.user,
#chat-9 .user-row .bubble, #chat-13 .user-row .bubble {
    background: linear-gradient(135deg, #eef2ff, #f5f0ff) !important;
    border: 1px solid #ddd6fe !important; color: #312e81 !important;
    border-top-right-radius: 5px !important;
    box-shadow: 0 2px 10px rgba(79, 70, 229, 0.10);
}
#chat-9 .avatar-container img, #chat-13 .avatar-container img {
    border-radius: 50% !important;
    box-shadow: 0 0 0 2px #ffffff, 0 2px 8px rgba(79, 70, 229, 0.28);
}
/* ===== 输入框 ===== */
#composer-9 textarea, #composer-13 textarea, #session-13 input {
    border-radius: 14px !important;
    border: 1.5px solid #d5d8ec !important;
    background: #ffffff;
    transition: border-color .15s ease, box-shadow .15s ease;
}
#composer-9 textarea:focus, #composer-13 textarea:focus, #session-13 input:focus {
    border-color: #6366f1 !important;
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15) !important;
}
#session-13 input { font-family: var(--mono); font-size: 0.9em; }
/* ===== 滑杆与开关的主题色 ===== */
.gradio-container input[type="range"] { accent-color: #4f46e5; }
/* ===== 会话输入行：紧凑输入框 + 右侧小按钮 ===== */
#composer-row-9, #composer-row-13 { align-items: flex-end; gap: 12px !important; }
#composer-row-9 button, #composer-row-13 button {
    padding: 7px 16px !important; font-size: 0.9em !important;
    border-radius: 10px !important;
    min-width: 0 !important; width: auto !important; flex: 0 0 auto !important;
    min-height: 0 !important; max-height: 52px !important;
}
#composer-row-9 textarea, #composer-row-13 textarea {
    min-height: 0 !important;
}
#composer-row-9 button.secondary + button.secondary,
#composer-row-13 button.secondary { margin-left: 6px; }
/* ===== 分组与布局辅助层 ===== */
.gr-group { background: transparent !important; border: none !important; box-shadow: none !important; }
.styler { background: transparent !important; }
/* ===== 页脚 ===== */
.footer {
    text-align: center; color: var(--muted); font-size: 0.85em;
    margin-top: 28px; padding: 18px 0 26px 0; border-top: 1px solid var(--line);
}
.footer b { color: var(--ink); }
.footer a { color: var(--chain); text-decoration: none; font-weight: 600; }
.footer a:hover { text-decoration: underline; }
.footer-line { margin-bottom: 6px; }
.footer-note { margin-top: 6px; font-family: var(--mono); font-size: 0.92em; opacity: .75; }
/* ===== 过程透视终端（dedupe 会把同属性 !important 合并到高特异性规则，
   故这里用与 Gradio 升级版同构的双前缀 + 重复类名，特异性压过 .col-card 浅底） ===== */
.gradio-container.gradio-container-6-26-0 .contain .gradio-container.gradio-container-6-26-0 .contain .console textarea,
.gradio-container.gradio-container-6-26-0 .contain .console textarea,
.gradio-container .console textarea {
    background-image: linear-gradient(180deg, #0d1428, #0a0f1f) !important;
    background-color: #0a0f1f !important;
    color: #eaf6ee !important;
    font-family: var(--mono) !important; font-size: 0.88em !important;
    line-height: 1.75 !important;
    border: 1px solid #27324f !important; border-radius: 14px !important;
    box-shadow: inset 0 0 36px rgba(59, 130, 246, .08), inset 0 1px 0 rgba(255, 255, 255, .05);
    caret-color: #4ade80;
}
"""

THEME = gr.themes.Soft(
    primary_hue="indigo", secondary_hue="violet", neutral_hue="slate",
    radius_size=gr.themes.sizes.radius_lg)

# ==============================================================================
# UI
# ==============================================================================
PAGES = [
    "📡 9.1 模型 I/O 与流式",
    "🎭 9.2 Prompt 模板",
    "⚡ 9.3 LCEL 链式编排",
    "📋 9.4 结构化输出",
    "🛠️ 9.5 自定义工具",
    "🧠 9.6 记忆与裁剪",
    "🔍 9.7 Callbacks 审计",
    "📚 9.8 RAG 知识库",
    "🤖 9.9 Modern Agent",
    "🧩 9.10 上下文工程",
    "🔧 9.11 自定义中间件",
    "🛡️ 9.12 护栏与安全",
    "🌟 9.13 SmartBuyer 实战",
]

with gr.Blocks(title="LangChain 1.x Agent 教学工作台") as demo:

    # ================= 左侧边栏 =================
    with gr.Sidebar(open=True, elem_id="nav-sidebar", width="280px"):
        gr.HTML("""<div id="nav-logo"><h2>🌊 Vibe Coding</h2><p>LANGCHAIN 1.X LAB · CH09</p></div>""")
        page_selector = gr.Radio(choices=PAGES, value=PAGES[0], label="章节导航",
                                 elem_id="nav-radio", show_label=False, container=True)

    # ================= 顶部横幅 =================
    gr.HTML("""
    <div class="hero">
      <div class="hero-main">
        <div class="eyebrow">VIBE CODING · CHAPTER 09 LAB</div>
        <h1>LangChain 1.x Agent 教学工作台</h1>
        <p>十三道递进实验关卡。每一页都有「过程透视」终端：模板渲染结果、并行支流、工具调用链、裁剪明细、脱敏对照、检索片段——拒绝黑盒，看得见才学得会。</p>
        <div class="hero-tags">
          <span>🧩 LCEL 管道</span><span>🤖 create_agent</span><span>🛠️ 工具调用</span>
          <span>🧠 记忆裁剪</span><span>📚 RAG</span><span>🛡️ 护栏中间件</span>
        </div>
      </div>
      <div class="hero-side">
        <div class="hero-chain">prompt <b>|</b> llm <b>|</b> tools <b>|</b> memory <b>|</b> agent</div>
        <div class="hero-chain-cap">THE LCEL PIPELINE</div>
      </div>
    </div>
    """)

    def head(num, emoji, title, formula, desc):
        return f"""<div class="tab-head"><div class="tab-badge">{num}</div>
        <div class="tab-body"><h3>{emoji} {title}</h3>
        <p>{desc}</p><div class="pipe-line">{formula}</div></div></div>"""

    # ================= 页面 9.1：控制台式布局（上输入、中输出、下双面板） =================
    with gr.Group(visible=True) as pg1:
        gr.HTML(head("9.1", "📡", "模型统一 I/O 与元数据捕获",
                     "prompt <b>|</b> llm <b>|</b> response_metadata",
                     "invoke() 同步 ｜ stream() 逐 chunk 流式 ｜ .profile 模型能力档案（零 Token）。下方终端逐步打印发生了什么。"))
        with gr.Column(elem_classes=["input-unit"]):
            t1_prompt = gr.Textbox(label="Prompt 提示词", lines=4,
                                   value="请用一句话解释什么是 LangChain 1.x？")
            with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                t1_temp = gr.Slider(0.0, 1.0, value=0.7, label="Temperature",
                                    info="越高越发散", scale=2, min_width=200,
                                    elem_classes=["dashed-zone"])
                t1_btn = gr.Button("🚀 同步调用", variant="primary", size="sm")
                t1_stream_btn = gr.Button("⚡ 流式输出", size="sm")
                t1_profile_btn = gr.Button("🪪 能力档案", size="sm")
        t1_out = gr.Textbox(label="模型回复（实时流式）", lines=8,
                            placeholder="点击上方任意按钮后，这里实时输出模型回复…")
        with gr.Row(equal_height=True):
            with gr.Column(scale=1, elem_classes=["col-card"]):
                t1_meta = gr.Code(label="响应元数据 / 能力档案 (Token 统计、能力开关)", language="json")
            with gr.Column(scale=1, elem_classes=["col-card"]):
                t1_console = gr.Textbox(label="🔍 过程透视", lines=9, interactive=False,
                                        elem_classes=["console"], placeholder="点击按钮后，这里逐步打印本节发生了什么…")
        t1_btn.click(tab1_invoke, inputs=[t1_prompt, t1_temp], outputs=[t1_out, t1_meta, t1_console])
        t1_stream_btn.click(tab1_stream, inputs=[t1_prompt, t1_temp], outputs=[t1_out, t1_meta, t1_console])
        t1_profile_btn.click(tab1_profile, inputs=[], outputs=[t1_meta, t1_console])

    # ================= 页面 9.2：左输入右渲染 + 底部双卡 =================
    with gr.Group(visible=False) as pg2:
        gr.HTML(head("9.2", "🎭", "ChatPromptTemplate 动态模板与消息流",
                     "system <b>|</b> human <b>|</b> template_vars",
                     "模板不是黑盒：先「仅渲染」看变量如何填进 System/Human 消息，再调用模型；Few-Shot 演示展示示例如何注入。"))
        with gr.Row(equal_height=False):
            with gr.Column(scale=2, elem_classes=["input-unit"]):
                t2_text = gr.Textbox(label="待翻译文本 / 测试评论", lines=9, scale=5,
                                     value="LangChain provides standardized abstractions and LCEL piping for composing complex LLM chains.")
                with gr.Row(equal_height=False):
                    t2_domain = gr.Textbox(label="专业领域", value="AI 智能体与编译器技术", scale=1,
                                           elem_classes=["dashed-zone"])
                    t2_lang = gr.Textbox(label="目标语言", value="中文 (信达雅风格)", scale=1,
                                         elem_classes=["dashed-zone"])
                with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                    t2_render_btn = gr.Button("🔍 仅渲染模板 (免费)", variant="primary", size="sm")
                    t2_btn = gr.Button("🎬 渲染并流式翻译", size="sm")
                    t2_fewshot_btn = gr.Button("🎯 Few-Shot 注入演示", size="sm")
            with gr.Column(scale=3, elem_classes=["col-card"]):
                t2_msgs = gr.Textbox(label="渲染后的消息列表（模型实际看到的完整输入）", lines=13,
                                     placeholder="点击「仅渲染模板」后，这里显示填充完成的消息列表…")
        with gr.Row(equal_height=True):
            with gr.Column(scale=1, elem_classes=["col-card"]):
                t2_out = gr.Textbox(label="模型翻译输出（实时流式）", lines=8, placeholder="点击「渲染并流式翻译」后输出…")
            with gr.Column(scale=1, elem_classes=["col-card"]):
                t2_console = gr.Textbox(label="🔍 过程透视", lines=8, interactive=False, elem_classes=["console"],
                                        placeholder="点击按钮后，这里讲解模板填充与消息模型…")
        t2_render_btn.click(tab2_render, inputs=[t2_domain, t2_lang, t2_text], outputs=[t2_msgs, t2_out, t2_console])
        t2_btn.click(tab2_translate_stream, inputs=[t2_domain, t2_lang, t2_text], outputs=[t2_msgs, t2_out, t2_console])
        t2_fewshot_btn.click(tab2_fewshot, inputs=t2_text, outputs=[t2_msgs, t2_console])

    # ================= 页面 9.3：并行双卡 + 汇聚/终端行 =================
    with gr.Group(visible=False) as pg3:
        gr.HTML(head("9.3", "⚡", "LCEL 管道与 RunnableParallel 并行分支",
                     "RunnableParallel <b>|</b> summary_prompt <b>|</b> llm <b>|</b> parser",
                     "赞美与吐槽两条支流「同时」执行：左右两张支流卡同时填充，终端时间戳交错可见并发证据。"))
        with gr.Column(elem_classes=["input-unit"]):
            t3_topic = gr.Textbox(label="讨论主题", lines=2, value="开源大模型与闭源商业模型的竞争")
            with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                t3_btn = gr.Button("🔀 并行执行双分支（赞美 + 吐槽 → 综合）", variant="primary", size="sm")
        with gr.Row(equal_height=True):
            t3_praise = gr.Textbox(label="🌸 赞美支流输出（并行分支 1）", lines=7, placeholder="支流 1 的结果…")
            t3_roast = gr.Textbox(label="🌶️ 吐槽支流输出（并行分支 2）", lines=7, placeholder="支流 2 的结果…")
        with gr.Row(equal_height=True):
            with gr.Column(scale=3, elem_classes=["col-card"]):
                t3_summary = gr.Textbox(label="✅ 汇聚节点综合点评", lines=6,
                                        placeholder="两支流结果拼入 summary_prompt 后的产物…")
            with gr.Column(scale=2, elem_classes=["col-card"]):
                t3_console = gr.Textbox(label="🔍 过程透视", lines=6, interactive=False, elem_classes=["console"],
                                        placeholder="点击按钮后，这里显示两条支流的启动/完成时间戳与耗时对比…")
        t3_btn.click(tab3_parallel_stream, inputs=t3_topic, outputs=[t3_praise, t3_roast, t3_summary, t3_console])

    # ================= 页面 9.4：左输入+终端 / 右报关单 =================
    with gr.Group(visible=False) as pg4:
        gr.HTML(head("9.4", "📋", "Pydantic 强类型结构化提取",
                     "llm.with_structured_output(Schema)",
                     "下方实时展示注入给模型的 JSON Schema——模型按单填表，Pydantic 质检通过后才返回强类型对象。"))
        with gr.Row(equal_height=True):
            with gr.Column(scale=2, elem_classes=["col-card"]):
                with gr.Column(elem_classes=["input-unit fill"]):
                    t4_text = gr.Textbox(label="非结构化财报新闻文本", lines=13, value="""TechStar 2025Q3 营收 158.6 亿元，同比超预期增长 28.5%，其中 AI 业务占比 42%；净利润 24.1 亿元符合预期。面临海外供应链限制与算力成本上升风险。综合评级买入，情绪评分 88。""")
                    with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                        t4_btn = gr.Button("🧾 一键强类型提取 (Pydantic)", variant="primary", size="sm")
                t4_console = gr.Textbox(label="🔍 过程透视", lines=6, interactive=False, elem_classes=["console"],
                                        placeholder="点击按钮后，这里打印注入 → 调用 → 校验三步…")
            with gr.Column(scale=3, elem_classes=["col-card"]):
                t4_out = gr.Code(label="结构化 JSON 输出", language="json", lines=13)
                t4_schema = gr.JSON(label="注入给模型的 JSON Schema（模型要填的「报关单」）", value=SCHEMA_JSON, max_height=340)
        t4_btn.click(tab4_extract_stream, inputs=t4_text, outputs=[t4_out, t4_console])

    # ================= 页面 9.5：参数一行 + 三卡并排 =================
    with gr.Group(visible=False) as pg5:
        gr.HTML(head("9.5", "🛠️", "自定义工具：Schema → tool_calls → 执行",
                     "@tool → args_schema → bind_tools → tool_calls",
                     "三段式拆解工具调用全流程：① 看 Schema 怎么生成 ② 模型「点名」工具与参数 ③ 运行时才真正执行。"))
        with gr.Row(equal_height=False):
            t5_p = gr.Number(label="贷款本金 (万元)", value=100, scale=1)
            t5_y = gr.Number(label="贷款年限 (年)", value=30, scale=1)
            t5_r = gr.Number(label="年化利率 (%)", value=3.2, scale=1)
        with gr.Row(equal_height=False, elem_classes=["btn-row split"]):
            t5_schema_btn = gr.Button("🔍 查看工具 Schema (免费)", variant="primary", size="sm")
            t5_model_btn = gr.Button("🤖 模型自主调用全流程", size="sm")
            t5_direct_btn = gr.Button("⚡ 直接执行工具 (校验演示)", size="sm")
        with gr.Row(equal_height=True):
            with gr.Column(scale=1, elem_classes=["col-card"]):
                t5_schema_out = gr.JSON(label="工具 JSON Schema（Docstring + 类型注解自动生成）", max_height=260)
            with gr.Column(scale=1, elem_classes=["col-card"]):
                t5_calls_out = gr.JSON(label="模型返回的 tool_calls（模型「点名」要调的工具与参数）", max_height=260)
            with gr.Column(scale=1, elem_classes=["col-card"]):
                t5_result = gr.Textbox(label="工具执行结果（运行时真正跑函数的输出）", lines=9,
                                       placeholder="点击「模型自主调用全流程」后，运行时执行函数的结果…")
        t5_console = gr.Textbox(label="🔍 过程透视", lines=7, interactive=False, elem_classes=["console"],
                                placeholder="点击按钮后，这里逐步拆解工具调用四阶段…")
        t5_schema_btn.click(tab5_schema, inputs=[], outputs=[t5_schema_out, t5_console])
        t5_model_btn.click(tab5_model_invoke_stream, inputs=[t5_p, t5_y, t5_r],
                           outputs=[t5_result, t5_calls_out, t5_result, t5_console])
        t5_direct_btn.click(tab5_direct_run, inputs=[t5_p, t5_y, t5_r], outputs=[t5_result, t5_console])

    # ================= 页面 9.6：原始对话 vs 裁剪命运 对照 =================
    with gr.Group(visible=False) as pg6:
        gr.HTML(head("9.6", "🧠", "trim_messages 智能滑动窗口裁剪",
                     "checkpointer + thread_id <b>|</b> trim_messages",
                     "左边是裁剪前模型看到的完整历史，右边逐条标注 ✅保留 / ✂️裁掉——拖动预算滑杆，看旧消息如何被滑出窗口。"))
        with gr.Row(equal_height=True):
            with gr.Column(scale=2, elem_classes=["col-card"]):
                with gr.Column(elem_classes=["input-unit fill center-content"]):
                    t6_count = gr.Slider(1, 9, value=9, step=1, label="模拟历史总消息条数",
                                         info="对话累计的完整历史")
                    t6_tok = gr.Slider(3, 15, value=9, step=1, label="滑动窗口预算（保留最近 N 条消息）",
                                       info="strategy='last'：从最新往回保留——预算 5 就是只带最近 5 条进上下文")
                    with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                        t6_btn = gr.Button("✂️ 执行裁剪并查看明细", variant="primary", size="sm")
                t6_console = gr.Textbox(label="🔍 过程透视", lines=8, interactive=False, elem_classes=["console"],
                                        placeholder="点击按钮后，这里解读裁剪策略…")
            with gr.Column(scale=3, elem_classes=["col-card"]):
                t6_raw = gr.Textbox(label="📜 原始完整对话（裁剪前模型看到的全部历史）", lines=15,
                                    placeholder="点击「执行裁剪」后，这里显示原始消息列表…")
                t6_out = gr.Textbox(label="🎯 裁剪明细（逐条标注保留/裁掉）", lines=15,
                                    placeholder="点击「执行裁剪」后，这里逐条标注每条消息的命运…")
        t6_btn.click(tab6_trim, inputs=[t6_count, t6_tok], outputs=[t6_raw, t6_out, t6_console])

    # ================= 页面 9.7：左脱敏右账单 =================
    with gr.Group(visible=False) as pg7:
        gr.HTML(head("9.7", "🔍", "Callbacks 审计与隐私脱敏",
                     "on_llm_start → on_llm_end <b>|</b> PII redact",
                     "脱敏前后的 Prompt 对照、黑匣子记录的耗时与 Token 账单——全部摆上桌面。"))
        with gr.Row(equal_height=True):
            with gr.Column(scale=2, elem_classes=["col-card"]):
                with gr.Column(elem_classes=["input-unit fill"]):
                    t7_in = gr.Textbox(label="输入包含敏感信息的内容", lines=8,
                                       value="请帮我查询客户 13912345678（邮箱 foo.bar@qq.com）的购买意向，并分析产品核心价值。")
                    with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                        t7_btn = gr.Button("📼 触发带审计探针的链路调用", variant="primary", size="sm")
                t7_console = gr.Textbox(label="🔍 过程透视", lines=6, interactive=False, elem_classes=["console"],
                                        placeholder="点击按钮后，这里打印回调生命周期…")
            with gr.Column(scale=3, elem_classes=["col-card"]):
                t7_diff = gr.Textbox(label="🛡️ 脱敏对照（原始输入 vs 实际发送）", lines=8)
                with gr.Row(equal_height=True):
                    t7_out = gr.Textbox(label="模型处理回复", lines=5, placeholder="脱敏后的内容送入模型…")
                    t7_audit = gr.Textbox(label="📊 审计报表 (耗时 / Token / 费用)", lines=5)
        t7_btn.click(tab7_audit_stream, inputs=t7_in, outputs=[t7_out, t7_diff, t7_audit, t7_console])

    # ================= 页面 9.8：检索片段为主角 =================
    with gr.Group(visible=False) as pg8:
        gr.HTML(head("9.8", "📚", "ChromaDB 向量检索增强 (RAG)",
                     "retriever <b>|</b> format_docs <b>|</b> prompt <b>|</b> llm",
                     "开卷考试也要看见「翻到了哪页」：先展示命中的知识片段，再看基于片段的回答。"))
        with gr.Column(elem_classes=["input-unit"]):
            t8_q = gr.Textbox(label="向企业技术规范库提问", lines=3,
                              value="系统灰度金丝雀发布的初始流量比例和观察时间是多少？")
            with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                t8_btn = gr.Button("🔎 检索知识库并回答", variant="primary", size="sm")
        with gr.Row(equal_height=True):
            with gr.Column(scale=3, elem_classes=["col-card"]):
                t8_frags = gr.Textbox(label="命中的知识片段（向量检索 Top-2）", lines=12,
                                      placeholder="点击按钮后，这里展示检索到的原文片段与来源…")
            with gr.Column(scale=2, elem_classes=["col-card"]):
                t8_out = gr.Textbox(label="基于 RAG 的精准回答", lines=12)
        t8_console = gr.Textbox(label="🔍 过程透视", lines=7, interactive=False, elem_classes=["console"],
                                placeholder="点击按钮后，这里打印切块→向量化→检索→组装→生成全链路…")
        t8_btn.click(tab8_rag_stream, inputs=t8_q, outputs=[t8_out, t8_frags, t8_console])

    # ================= 页面 9.9：Codex 式会话 =================
    with gr.Group(visible=False) as pg9:
        gr.HTML(head("9.9", "🤖", "Modern Agent：create_agent 多轮对话",
                     "create_agent(model, tools) → messages pipeline",
                     "Codex 式左右气泡：你的消息在右、Agent 在左。回复逐 token 流式，右侧流水线实时记录每次工具调用。"))
        with gr.Row(equal_height=True):
            with gr.Column(scale=5):
                t9_chat = gr.Chatbot(label="Agent 对话", height="62vh", elem_id="chat-9", resizable=True,
                                     buttons=None, avatar_images=(None, None),
                                     layout="bubble", group_consecutive_messages=False,
                                     placeholder="给我一条复合指令，例如：算一道数学题 + 查天气 + 换汇率…")
                with gr.Column(elem_classes=["chat-input-unit"]):
                    t9_in = gr.Textbox(lines=4, scale=10, show_label=False, container=False,
                                       placeholder="给我一条复合指令，例如：算一道数学题 + 查天气 + 换汇率…",
                                       elem_id="composer-9", max_lines=6)
                    with gr.Row(equal_height=False, elem_classes=["btn-row tail"], elem_id="composer-row-9"):
                        t9_clear = gr.Button("🗑️ 清空", size="sm")
                        t9_send = gr.Button("🚀 发送", variant="primary", size="sm")
            with gr.Column(scale=2):
                t9_steps = gr.Textbox(label="🔍 推理与工具调用流水线（实时刷新）", lines=6, interactive=False,
                                      buttons=["copy"], elem_id="log-9")
        t9_send.click(tab9_agent_chat, inputs=[t9_in, t9_chat, t9_steps], outputs=[t9_chat, t9_steps, t9_in])
        t9_in.submit(tab9_agent_chat, inputs=[t9_in, t9_chat, t9_steps], outputs=[t9_chat, t9_steps, t9_in])
        t9_clear.click(lambda: ([], "", ""), outputs=[t9_chat, t9_steps, t9_in])

    # ================= 页面 9.10：概念卡 + 演示按钮 + 大终端 =================
    with gr.Group(visible=False) as pg10:
        gr.HTML(head("9.10", "🧩", "上下文工程与动态上下文注入",
                     "@dynamic_prompt(request) → Runtime <b>|</b> State <b>|</b> Store",
                     "三类上下文 × 三数据源：每个演示都真实调用模型——对比两种场景下注入的 System Prompt、可见工具与回复风格差异。"))
        with gr.Row(equal_height=True):
            with gr.Column(scale=2, elem_classes=["col-card"]):
                gr.Markdown("""### 三种数据源
- **Runtime Context**：一次调用的瞬时配置（如 `user_id`）
- **State**：本轮会话内的动态状态（消息数、阶段）
- **Store**：跨会话长期画像（用户偏好）

### 三种注入点
- 动态 System Prompt（`@dynamic_prompt`）
- 动态工具选择（`@wrap_model_call` 裁剪工具清单）
- 画像注入（Store + Context 双剑合璧）""")
            with gr.Column(scale=3, elem_classes=["col-card"]):
                with gr.Row(equal_height=False, elem_classes=["btn-row split"]):
                    t10_run1 = gr.Button("📝 动态 System Prompt", variant="primary", size="sm")
                    t10_run2 = gr.Button("🧰 动态工具选择", size="sm")
                    t10_run3 = gr.Button("🗄️ Store 画像注入", size="sm")
                gr.Markdown("""- **演示 1**：短对话 vs 长对话，System Prompt 自动追加「简洁」指令
- **演示 2**：未认证时 `private_search` 被真实裁掉，模型只能调用 public 工具
- **演示 3**：老用户（简洁直接画像）vs 新用户的回复风格对比""")
        t10_console = gr.Textbox(label="🔍 演示终端输出（来自 code/s10_context_engineering.py）", lines=17,
                                 interactive=False, elem_classes=["console"],
                                 placeholder="点击演示按钮后，这里显示脚本完整运行输出…")
        t10_run1.click(lambda: tab_demo(demo_dynamic_prompt), inputs=[], outputs=t10_console)
        t10_run2.click(lambda: tab_demo(demo_dynamic_tools), inputs=[], outputs=t10_console)
        t10_run3.click(lambda: tab_demo(demo_store_injection), inputs=[], outputs=t10_console)

    # ================= 页面 9.11：概念卡 + 演示按钮 + 大终端 =================
    with gr.Group(visible=False) as pg11:
        gr.HTML(head("9.11", "🔧", "自定义中间件与生命周期钩子",
                     "@before_model → @wrap_model_call → @after_model",
                     "Node-style 熔断 / Wrap-style 重试 / 类式计数限流：每个演示都真实执行——对比放行与熔断、观察失败→重试自愈全过程。"))
        with gr.Row(equal_height=True):
            with gr.Column(scale=2, elem_classes=["col-card"]):
                gr.Markdown("""### 两种钩子风格
- **Node-style**：`before_model` / `after_model` 等，在执行点前后插入逻辑，可改状态、可熔断（`jump_to: end`）
- **Wrap-style**：`wrap_model_call` 包住整个调用，可重试/改请求/短路

### 进阶
- 类式中间件（同步 + 异步双实现）
- `state_schema` 自定义状态，让中间件拥有「记忆」""")
            with gr.Column(scale=3, elem_classes=["col-card"]):
                with gr.Row(equal_height=False, elem_classes=["btn-row split"]):
                    t11_run1 = gr.Button("🚦 Node-style 钩子", variant="primary", size="sm")
                    t11_run2 = gr.Button("🔁 Wrap-style 重试", size="sm")
                    t11_run3 = gr.Button("🧱 类式中间件", size="sm")
                gr.Markdown("""- **演示 1**：正常放行 vs 50 条历史触发 `jump_to='end'` 零 Token 熔断
- **演示 2**：模拟网络抖动，wrap_model_call 失败自动重试 3 次后自愈
- **演示 3**：日志中间件 + `state_schema` 调用计数真实累计""")
        t11_console = gr.Textbox(label="🔍 演示终端输出（来自 code/s11_custom_middleware.py）", lines=17,
                                 interactive=False, elem_classes=["console"],
                                 placeholder="点击演示按钮后，这里显示脚本完整运行输出…")
        t11_run1.click(lambda: tab_demo(demo_node_style), inputs=[], outputs=t11_console)
        t11_run2.click(lambda: tab_demo(demo_wrap_style), inputs=[], outputs=t11_console)
        t11_run3.click(lambda: tab_demo(demo_class_middleware), inputs=[], outputs=t11_console)

    # ================= 页面 9.12：安检台布局 =================
    with gr.Group(visible=False) as pg12:
        gr.HTML(head("9.12", "🛡️", "生产级防护：护栏、PII 与注入防护",
                     "before_agent 拦截 → PII redact → after_agent 审查",
                     "先玩免费的「本地安检门」（零 Token 毫秒级），再跑真实调用演示：看模型亲口承认只看到脱敏占位符、黑名单请求被零 Token 拦截。"))
        with gr.Row(equal_height=True):
            with gr.Column(scale=2, elem_classes=["col-card"]):
                with gr.Column(elem_classes=["input-unit fill"]):
                    t12_in = gr.Textbox(label="输入测试文本（试试黑名单词或邮箱）", lines=7,
                                        value="联系我 admin@example.com，我想学习 hack 技术")
                    with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                        t12_check_btn = gr.Button("🚪 本地安检门 (免费)", variant="primary", size="sm")
                        t12_selftest_btn = gr.Button("🧪 出厂自测", size="sm")
            with gr.Column(scale=3, elem_classes=["col-card"]):
                t12_out = gr.Textbox(label="安检结果（拦截判定 + 脱敏后文本）", lines=8,
                                     placeholder="点击「本地安检门」后立即出结果…")
        with gr.Row(equal_height=False, elem_classes=["btn-row split"]):
            t12_run1 = gr.Button("🛡️ 演示：PII 中间件", size="sm")
            t12_run2 = gr.Button("🧱 演示：自定义护栏", size="sm")
        t12_console = gr.Textbox(label="🔍 演示终端输出（来自 code/s12_guardrails_and_testing.py）", lines=12,
                                 interactive=False, elem_classes=["console"],
                                 placeholder="点击 LLM 演示或自测后，这里显示脚本运行输出…")
        t12_check_btn.click(tab12_local_check, inputs=t12_in, outputs=[t12_out, t12_console])
        t12_selftest_btn.click(lambda: tab_demo(run_self_tests), inputs=[], outputs=t12_console)
        t12_run1.click(lambda: tab_demo(demo_pii_middleware), inputs=[], outputs=t12_console)
        t12_run2.click(lambda: tab_demo(demo_custom_guardrails), inputs=[], outputs=t12_console)

    # ================= 页面 9.13：整机总装 =================
    with gr.Group(visible=False) as pg13:
        gr.HTML(head("9.13", "🌟", "SmartBuyer 综合实战（9.1~9.12 全零件总装）",
                     "RAG <b>|</b> search <b>|</b> calc <b>|</b> 护栏 <b>|</b> 画像注入",
                     "整机规格：避坑 RAG + 差评搜索 + 性价比测算 + 三层中间件栈 + 动态画像剧本。填「顾客 ID」体验 Store 画像让参谋换一种说话风格！"))
        with gr.Row(equal_height=False, elem_classes=["btn-row split"]):
            preset1 = gr.Button("💻 5000元轻薄本", size="sm")
            preset2 = gr.Button("🎧 2000元降噪耳机", size="sm")
            preset3 = gr.Button("📱 3000元性能手机", size="sm")
            preset4 = gr.Button("🖥️ 千元4K显示器", size="sm")
        with gr.Row(equal_height=True):
            with gr.Column(scale=3):
                with gr.Row(equal_height=True):
                    t13_session = gr.Dropdown(label="会话 ID（一份记忆）", value="buyer_user_01",
                                              choices=["buyer_user_01", "buyer_user_02", "buyer_user_03"],
                                              allow_custom_value=True, elem_id="session-13", scale=1)
                    t13_uid = gr.Dropdown(label="顾客 ID（Store 画像注入，可换着试）", value="user-veteran",
                                          choices=["user-veteran", "user-rookie", "user-guest"],
                                          allow_custom_value=True, scale=1)
                t13_chat = gr.Chatbot(label="SmartBuyer 选购问诊", height="50vh", elem_id="chat-13", resizable=True,
                                      buttons=["copy"], avatar_images=(None, None),
                                      layout="bubble", group_consecutive_messages=False,
                                      placeholder="说说你的预算、用途和纠结点，参谋马上开工…")
                with gr.Column(elem_classes=["chat-input-unit"]):
                    t13_query = gr.Textbox(lines=4, scale=10, show_label=False, container=False,
                                           placeholder="说说你的预算、用途和纠结点，参谋马上开工…",
                                           elem_id="composer-13", max_lines=6)
                    with gr.Row(equal_height=False, elem_classes=["btn-row tail"], elem_id="composer-row-13"):
                        t13_new = gr.Button("🔄 新会话", size="sm")
                        t13_btn = gr.Button("🛒 发送", variant="primary", size="sm")
                t13_tip = gr.Markdown("")
            with gr.Column(scale=2):
                t13_profile = gr.JSON(label="🧠 Store 长期画像（当前顾客 ID 命中的画像，随上方下拉切换）",
                                      value=smart_buyer_agent.store.get(("buyers",), "user-veteran").value,
                                      max_height=200)
                t13_steps = gr.Textbox(label="🔍 工具调用与画像注入明细（实时）", lines=8, interactive=False,
                                       buttons=["copy"], elem_id="log-13")
                t13_audit = gr.Textbox(label="📊 Token 与财务账单", lines=3, interactive=False)
        with gr.Row(equal_height=True):
            with gr.Column(scale=2, elem_classes=["col-card"]):
                with gr.Column(elem_classes=["input-unit fill"]):
                    t13_demand = gr.Textbox(label="一键结构化报表：输入预算与要求", lines=5,
                                            value="预算 2000 元，想买一款佩戴舒服、降噪给力、音质好的头戴式耳机，经常坐飞机和高铁使用。")
                    with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                        t13_report_btn = gr.Button("🧾 生成标准决策报表", variant="primary", size="sm")
            with gr.Column(scale=3, elem_classes=["col-card"]):
                t13_report = gr.Code(label="标准选购决策 JSON (ShoppingDecisionReport)", language="json", lines=6)
        preset1.click(lambda: "预算 5000 左右，买什么轻薄本适合写代码、日常办公，续航长一点，内存最好 32G。", outputs=t13_query)
        preset2.click(lambda: "预算 2000 元左右，买什么头戴式降噪耳机比较好？主要在地铁飞机上用，要求降噪强、不夹头。", outputs=t13_query)
        preset3.click(lambda: "预算 3000 元左右，想买一部拍照清晰、玩游戏不发烫、充电快的手机，推荐哪几款？", outputs=t13_query)
        preset4.click(lambda: "预算 1500 元以内买 4K 显示器做编程和办公，有什么需要注意的屏幕参数陷阱？", outputs=t13_query)
        t13_btn.click(tab13_buyer_chat, inputs=[t13_query, t13_chat, t13_session, t13_uid],
                      outputs=[t13_chat, t13_steps, t13_audit]).then(lambda: "", outputs=t13_query)
        t13_query.submit(tab13_buyer_chat, inputs=[t13_query, t13_chat, t13_session, t13_uid],
                         outputs=[t13_chat, t13_steps, t13_audit]).then(lambda: "", outputs=t13_query)
        t13_new.click(tab13_clear, inputs=t13_session, outputs=[t13_chat, t13_steps, t13_tip])

        def refresh_profile(uid):
            """顾客 ID 变化 → 实时读 Store 画像（无画像则提示新客）"""
            rec = smart_buyer_agent.store.get(("buyers",), uid or "")
            if rec is None:
                return {"提示": f"Store 中暂无 {uid or '（空）'} 的画像 —— 新客首次对话后可由中间件写入偏好"}
            return rec.value

        t13_uid.change(refresh_profile, inputs=t13_uid, outputs=t13_profile)
        t13_report_btn.click(tab13_report, inputs=t13_demand, outputs=t13_report)

    # ================= 导航切换 =================
    page_groups = [pg1, pg2, pg3, pg4, pg5, pg6, pg7, pg8, pg9, pg10, pg11, pg12, pg13]

    def show_page(selected):
        return [gr.update(visible=(selected == name)) for name in PAGES]

    page_selector.change(show_page, inputs=page_selector, outputs=page_groups)

    # ================= 页脚 =================
    gr.HTML("""
    <div class="footer">
      <div class="footer-line">🌊 <b>Vibe Coding 开源教学知识库</b> · 第九章配套实验台（13 关卡）｜
      📖 <a href="https://docs.langchain.com/" target="_blank">LangChain 官方文档</a> ｜
      🔍 每页都有「过程透视」终端 · 拒绝黑盒</div>
      <div class="footer-note">Powered by LangChain 1.x · Gradio · 模型密钥存放于 .env，请勿外传</div>
    </div>
    """)

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860, share=False, theme=THEME, css=custom_css)
