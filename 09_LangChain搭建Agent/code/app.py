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

    yield "", "", f"[{now()}] [阶段 1/3] RunnableParallel 同时派发两条支流（真并发，注意时间戳交错）…"
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
    log = [f"[{now()}] [1/3] with_structured_output(Schema)：把 Pydantic 模型转成 JSON Schema 注入请求（见下方「报关单」）"]
    yield "⏳ 提取中…", "\n".join(log)
    try:
        llm = get_chat_model_primary()
        structured_llm = llm.with_structured_output(FinancialReportAnalysis)
        data = structured_llm.invoke(text)
        log.append(f"[{now()}] [2/3] 模型经 Function Calling 返回符合 Schema 的 JSON")
        log.append(f"[{now()}] [3/3] Pydantic 校验通过 ✓（字段名/类型/取值范围全部合规）→ 直接得到强类型对象")
        return json.dumps(data.model_dump(), indent=2, ensure_ascii=False), "\n".join(log)
    except Exception as e:
        log.append(f"❌ 提取失败：{e}")
        return f"提取失败：{e}", "\n".join(log)

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
    lines = [f"原始 {len(msgs)} 条 → 裁剪后保留 {len(trimmed)} 条（预算 {int(budget)}）", "─" * 42]
    for i, m in enumerate(msgs):
        mark = "✅ 保留" if (m.type, m.content) in kept else "✂️ 裁掉 "
        lines.append(f"{mark}  #{i} [{m.type:7s}] {str(m.content)[:36]}")
    log = (f"[{now()}] 策略解读：\n"
           f"  · strategy=\"last\" —— 从最新往回保留（最近的上下文最重要）\n"
           f"  · include_system=True —— 顶层 System 人设永远不动（大脑设定不能丢）\n"
           f"  · start_on=\"human\" —— 裁完的第一条有效消息必须是 human，符合对话开启惯例\n"
           f"[{now()}] token_counter=len 是教学用的简化计数，生产环境请用 tiktoken。\n"
           f"[{now()}] 进阶：SummarizationMiddleware 会把旧消息「摘要」而非丢弃（见 9.6 课件）。")
    return "\n".join(lines), log

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
.gradio-container {
    --paper:#f6f7fc; --card:#ffffff; --line:#e3e5f1;
    --ink:#1e1b4b; --chain:#4f46e5; --spark:#7c3aed; --amber:#f59e0b; --muted:#5c5f78;
    --serif:"Songti SC","Noto Serif SC","Source Han Serif SC",Georgia,serif;
    --mono:"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", Roboto, sans-serif;
    max-width: min(1560px, 97vw) !important;
    margin: 0 auto !important;
    background: var(--paper);
    overflow-x: clip;
}
/* ===== 侧边栏 ===== */
#nav-sidebar { background: #f1f2fa !important; border-right: 1px solid var(--line); }
#nav-logo { text-align: center; padding: 12px 6px 4px 6px; }
#nav-logo h2 { margin: 0 0 6px 0; font-family: var(--serif); font-size: 1.22em; letter-spacing: 1px; color: var(--chain); }
#nav-logo p { margin: 0; font-family: var(--mono); font-size: 0.72em; letter-spacing: 0.16em; color: var(--muted); }
#nav-radio .wrap { gap: 5px !important; }
#nav-radio label {
    background: transparent; border: 1px solid transparent !important;
    border-radius: 9px !important; padding: 6px 10px !important;
    transition: all .15s ease; cursor: pointer;
    color: var(--ink) !important; font-size: 0.9em;
}
#nav-radio label:hover { background: #ffffff; border-color: var(--line) !important; }
#nav-radio label.selected {
    background: linear-gradient(90deg, var(--chain), var(--spark)) !important;
    border-color: transparent !important;
    box-shadow: 0 6px 14px rgba(79, 70, 229, 0.30);
}
#nav-radio label.selected, #nav-radio label.selected * { color: #ffffff !important; }
#nav-radio label input { display: none; }
/* ===== Hero 控制台横幅 ===== */
.hero {
    display: flex; align-items: center; justify-content: space-between; gap: 20px; flex-wrap: wrap;
    background: linear-gradient(115deg, #312e81 0%, #4338ca 55%, #6d28d9 100%);
    border-radius: 16px; padding: 20px 26px; margin-bottom: 16px;
    color: #f8fafc; box-shadow: 0 8px 26px rgba(67, 56, 202, 0.22);
}
.hero .eyebrow { font-family: var(--mono); font-size: 0.74em; letter-spacing: 0.22em; color: #fcd34d; margin-bottom: 6px; }
.hero h1 { margin: 0; font-family: var(--serif); font-size: clamp(1.3em, 2.3vw, 1.85em); letter-spacing: 0.5px; }
.hero p { margin: 8px 0 0; max-width: 820px; color: #d9dcf5; font-size: 0.9em; line-height: 1.7; }
.hero-chain {
    font-family: var(--mono); font-size: 0.92em; color: #e0e7ff;
    background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.16);
    padding: 12px 18px; border-radius: 12px; white-space: nowrap;
    max-width: 100%; overflow-x: auto;
}
.hero-chain b { color: #fcd34d; font-weight: 700; padding: 0 2px; }
/* ===== 页头说明条 ===== */
.tab-head {
    background: var(--card); border: 1px solid var(--line); border-left: 4px solid var(--chain);
    border-radius: 12px; padding: 11px 18px; margin-bottom: 14px;
}
.tab-head h3 { margin: 0 0 3px 0; font-family: var(--serif); font-size: 1.1em; color: var(--ink); }
.tab-head p { margin: 0 0 7px 0; font-size: 0.86em; color: var(--muted); }
.pipe-line {
    display: inline-block; font-family: var(--mono); font-size: 0.8em;
    color: var(--chain); background: #eef0fe; border: 1px dashed #c4c9f6;
    border-radius: 7px; padding: 3px 10px;
}
.pipe-line b { color: #b45309; font-weight: 700; }
/* ===== 过程透视终端 ===== */
.console textarea {
    background: #0f172a !important; color: #86efac !important;
    font-family: var(--mono) !important; font-size: 0.84em !important;
    line-height: 1.7 !important;
    border: 1px solid #1e293b !important; border-radius: 12px !important;
}
/* ===== 卡片：弹性等高、留白透气 ===== */
.col-card { display: flex; flex-direction: column; row-gap: 16px !important; }
.col-card > :last-child { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; }
.col-card > :last-child > * { flex: 1 1 auto; min-height: 0; }
.col-card > :last-child label { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; }
.col-card > :last-child textarea { flex: 1 1 auto; min-height: 150px; resize: none !important; }
.col-card > :last-child .cm-editor,
.col-card > :last-child .CodeMirror { height: 100% !important; }
#log-9 textarea { height: calc(54vh + 96px) !important; min-height: 280px; }
#log-13 textarea { height: calc(44vh + 120px) !important; min-height: 220px; }
/* ===== 按钮（shadcn/ui 风格） ===== */
.gradio-container button.primary {
    background: linear-gradient(135deg, #4f46e5, #7c3aed) !important;
    border: none !important; color: #ffffff !important; font-weight: 600 !important;
    letter-spacing: 0.02em;
    box-shadow: 0 4px 14px rgba(79, 70, 229, 0.28);
    transition: transform .15s ease, box-shadow .15s ease, filter .15s ease;
}
.gradio-container button.primary:hover {
    transform: translateY(-1px);
    box-shadow: 0 8px 22px rgba(79, 70, 229, 0.36);
    filter: saturate(1.08);
}
.gradio-container button.primary:active { transform: translateY(0); box-shadow: 0 3px 10px rgba(79, 70, 229, 0.28); }
.gradio-container button.secondary {
    background: #ffffff !important;
    border: 1px solid #d5d8ec !important; color: #312e81 !important; font-weight: 500;
    transition: all .15s ease;
}
.gradio-container button.secondary:hover {
    border-color: #a5b4fc !important; background: #eef2ff !important;
    color: #4338ca !important; box-shadow: 0 2px 8px rgba(79, 70, 229, 0.10);
}
.gradio-container button.lg { padding: 13px 24px !important; font-size: 1.02em !important; border-radius: 12px !important; }
.gradio-container button.sm { border-radius: 10px !important; }
/* ===== 会话窗口（Codex 式气泡） ===== */
#chat-9 .bubble, #chat-13 .bubble {
    border-radius: 16px !important;
    padding: 10px 16px !important;
    border: 1px solid #e8eaf6;
    box-shadow: 0 1px 3px rgba(30, 27, 75, 0.08);
    font-size: 0.95em; line-height: 1.68;
    max-width: min(80%, 660px);
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
/* ===== 会话输入行：大输入框 + 右侧紧凑按钮（带间隙） ===== */
#composer-row-9, #composer-row-13 { align-items: center; gap: 14px !important; }
#composer-row-9 button, #composer-row-13 button {
    padding: 9px 18px !important; font-size: 0.92em !important;
    border-radius: 10px !important;
    min-width: 0 !important; width: auto !important; flex: 0 0 auto !important;
}
#composer-row-9 button.secondary + button.secondary,
#composer-row-13 button.secondary { margin-left: 6px; }
/* ===== 分组与布局辅助层 ===== */
.gr-group { background: transparent !important; border: none !important; box-shadow: none !important; }
.styler { background: transparent !important; }
/* ===== 页脚 ===== */
.footer { text-align: center; color: var(--muted); font-size: 0.85em; margin-top: 26px; padding: 14px 0; border-top: 1px solid var(--line); }
.footer a { color: var(--chain); text-decoration: none; }
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
    with gr.Sidebar(open=True, elem_id="nav-sidebar", width="16%"):
        gr.HTML("""<div id="nav-logo"><h2>🌊 Vibe Coding</h2><p>LANGCHAIN 1.X LAB · CH09</p></div>""")
        page_selector = gr.Radio(choices=PAGES, value=PAGES[0], label="章节导航",
                                 elem_id="nav-radio", show_label=False, container=True)

    # ================= 顶部横幅 =================
    gr.HTML("""
    <div class="hero">
      <div>
        <div class="eyebrow">VIBE CODING · CHAPTER 09 LAB</div>
        <h1>LangChain 1.x Agent 教学工作台</h1>
        <p>十三道递进实验关卡。每一页都有「过程透视」终端：模板渲染结果、并行支流、工具调用链、裁剪明细、脱敏对照、检索片段——拒绝黑盒，看得见才学得会。</p>
      </div>
      <div class="hero-chain">prompt <b>|</b> llm <b>|</b> tools <b>|</b> memory <b>|</b> agent</div>
    </div>
    """)

    def head(num, emoji, title, formula, desc):
        return f"""<div class="tab-head"><h3>{emoji} {num} {title}</h3>
        <p>{desc}</p><div class="pipe-line">{formula}</div></div>"""

    # ================= 页面 9.1：控制台式布局（上输入、中输出、下双面板） =================
    with gr.Group(visible=True) as pg1:
        gr.HTML(head("9.1", "📡", "模型统一 I/O 与元数据捕获",
                     "prompt <b>|</b> llm <b>|</b> response_metadata",
                     "invoke() 同步 ｜ stream() 逐 chunk 流式 ｜ .profile 模型能力档案（零 Token）。下方终端逐步打印发生了什么。"))
        t1_prompt = gr.Textbox(label="Prompt 提示词", lines=3, value="请用一句话解释什么是 LangChain 1.x？")
        with gr.Row(equal_height=True):
            t1_temp = gr.Slider(0.0, 1.0, value=0.7, label="Temperature (多样性)",
                                info="越高越发散，越低越严谨", scale=3)
            t1_btn = gr.Button("🚀 同步调用 (invoke)", variant="primary", scale=2)
            t1_stream_btn = gr.Button("⚡ 流式打字机 (stream)", scale=2)
            t1_profile_btn = gr.Button("🪪 能力档案 (.profile)", scale=2)
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
        with gr.Row(equal_height=True):
            with gr.Column(scale=2, elem_classes=["col-card"]):
                t2_domain = gr.Textbox(label="专业领域", value="AI 智能体与编译器技术")
                t2_lang = gr.Textbox(label="目标语言", value="中文 (信达雅风格)")
                t2_text = gr.Textbox(label="待翻译文本 / 测试评论", lines=4, value="LangChain provides standardized abstractions and LCEL piping for composing complex LLM chains.")
                t2_render_btn = gr.Button("🔍 仅渲染模板 (免费)", variant="primary")
                t2_btn = gr.Button("🎬 渲染并流式翻译")
                t2_fewshot_btn = gr.Button("🎯 Few-Shot 示例注入演示 (免费)")
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
        t3_topic = gr.Textbox(label="讨论主题", lines=2, value="开源大模型与闭源商业模型的竞争")
        t3_btn = gr.Button("🔀 并行执行双分支 (赞美 + 吐槽 ➔ 综合)", variant="primary")
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
                t4_text = gr.Textbox(label="非结构化财报新闻文本", lines=9, value="""TechStar 2025Q3 营收 158.6 亿元，同比超预期增长 28.5%，其中 AI 业务占比 42%；净利润 24.1 亿元符合预期。面临海外供应链限制与算力成本上升风险。综合评级买入，情绪评分 88。""")
                t4_btn = gr.Button("🧾 一键强类型提取 (Pydantic Schema)", variant="primary")
                t4_console = gr.Textbox(label="🔍 过程透视", lines=6, interactive=False, elem_classes=["console"],
                                        placeholder="点击按钮后，这里打印注入 → 调用 → 校验三步…")
            with gr.Column(scale=3, elem_classes=["col-card"]):
                t4_out = gr.Code(label="结构化 JSON 输出", language="json", lines=9)
                t4_schema = gr.JSON(label="注入给模型的 JSON Schema（模型要填的「报关单」）", value=SCHEMA_JSON, max_height=280)
        t4_btn.click(tab4_extract_stream, inputs=t4_text, outputs=[t4_out, t4_console])

    # ================= 页面 9.5：参数一行 + 三卡并排 =================
    with gr.Group(visible=False) as pg5:
        gr.HTML(head("9.5", "🛠️", "自定义工具：Schema → tool_calls → 执行",
                     "@tool → args_schema → bind_tools → tool_calls",
                     "三段式拆解工具调用全流程：① 看 Schema 怎么生成 ② 模型「点名」工具与参数 ③ 运行时才真正执行。"))
        with gr.Row(equal_height=True):
            t5_p = gr.Number(label="贷款本金 (万元)", value=100, scale=1)
            t5_y = gr.Number(label="贷款年限 (年)", value=30, scale=1)
            t5_r = gr.Number(label="年化利率 (%)", value=3.2, scale=1)
        with gr.Row(equal_height=True):
            t5_schema_btn = gr.Button("🔍 查看工具 Schema (免费)", variant="primary", scale=1)
            t5_model_btn = gr.Button("🤖 模型自主调用全流程 (bind_tools)", scale=1)
            t5_direct_btn = gr.Button("⚡ 直接执行工具 (校验演示)", scale=1)
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

    # ================= 页面 9.6：左控制台右明细 =================
    with gr.Group(visible=False) as pg6:
        gr.HTML(head("9.6", "🧠", "trim_messages 智能滑动窗口裁剪",
                     "checkpointer + thread_id <b>|</b> trim_messages",
                     "裁剪不再是黑盒：每一条历史消息都会标注 ✅保留 / ✂️裁掉，直观理解策略如何工作。"))
        with gr.Row(equal_height=True):
            with gr.Column(scale=2, elem_classes=["col-card"]):
                t6_count = gr.Slider(1, 9, value=9, step=1, label="模拟历史总消息条数")
                t6_tok = gr.Slider(15, 100, value=30, step=5, label="Token/长度预算限制", info="预算越小，裁得越狠")
                t6_btn = gr.Button("✂️ 执行裁剪并查看明细", variant="primary")
                t6_console = gr.Textbox(label="🔍 过程透视", lines=8, interactive=False, elem_classes=["console"],
                                        placeholder="点击按钮后，这里解读裁剪策略…")
            with gr.Column(scale=3, elem_classes=["col-card"]):
                t6_out = gr.Textbox(label="裁剪明细（逐条标注保留/裁掉）", lines=15,
                                    placeholder="点击按钮后，这里逐条标注每条消息的命运…")
        t6_btn.click(tab6_trim, inputs=[t6_count, t6_tok], outputs=[t6_out, t6_console])

    # ================= 页面 9.7：左脱敏右账单 =================
    with gr.Group(visible=False) as pg7:
        gr.HTML(head("9.7", "🔍", "Callbacks 审计与隐私脱敏",
                     "on_llm_start → on_llm_end <b>|</b> PII redact",
                     "脱敏前后的 Prompt 对照、黑匣子记录的耗时与 Token 账单——全部摆上桌面。"))
        with gr.Row(equal_height=True):
            with gr.Column(scale=2, elem_classes=["col-card"]):
                t7_in = gr.Textbox(label="输入包含敏感信息的内容", lines=5,
                                   value="请帮我查询客户 13912345678（邮箱 foo.bar@qq.com）的购买意向，并分析产品核心价值。")
                t7_btn = gr.Button("📼 触发带审计探针的链路调用", variant="primary")
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
        with gr.Row(equal_height=True):
            t8_q = gr.Textbox(label="向企业技术规范库提问", lines=2, scale=4,
                              value="系统灰度金丝雀发布的初始流量比例和观察时间是多少？")
            t8_btn = gr.Button("🔎 检索知识库并回答", variant="primary", scale=1)
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
            with gr.Column(scale=3):
                t9_chat = gr.Chatbot(label="Agent 对话", height="54vh", elem_id="chat-9", resizable=True,
                                     buttons=["copy"], avatar_images=("🧑‍💻", "🤖"),
                                     layout="bubble", group_consecutive_messages=False,
                                     placeholder="给我一条复合指令，例如：算一道数学题 + 查天气 + 换汇率…")
                with gr.Row(equal_height=True, elem_id="composer-row-9"):
                    t9_in = gr.Textbox(lines=3, scale=10, show_label=False, container=False,
                                       placeholder="", elem_id="composer-9")
                    t9_send = gr.Button("🚀 发送", variant="primary", scale=1, size="sm")
                    t9_clear = gr.Button("🗑️ 清空", scale=1, size="sm")
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
                     "三类上下文 × 三数据源：点击任一演示，终端打印该模式注入前后的 System Prompt 与工具清单对比。"))
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
                t10_run1 = gr.Button("📝 演示 1：动态 System Prompt（按会话长度自适应）", variant="primary")
                t10_run2 = gr.Button("🧰 演示 2：动态工具选择（按认证状态裁剪工具）")
                t10_run3 = gr.Button("🗄️ 演示 3：Store 长期画像注入")
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
                     "Node-style 4 钩子 + Wrap-style 2 钩子：点一个演示，终端打印每个钩子被调用的时机与状态变化。"))
        with gr.Row(equal_height=True):
            with gr.Column(scale=2, elem_classes=["col-card"]):
                gr.Markdown("""### 两种钩子风格
- **Node-style**：`before_model` / `after_model` 等，在执行点前后插入逻辑，可改状态、可熔断（`jump_to: end`）
- **Wrap-style**：`wrap_model_call` 包住整个调用，可重试/改请求/短路

### 进阶
- 类式中间件（同步 + 异步双实现）
- `state_schema` 自定义状态，让中间件拥有「记忆」""")
            with gr.Column(scale=3, elem_classes=["col-card"]):
                t11_run1 = gr.Button("🚦 演示 1：Node-style（消息上限熔断 + 响应日志）", variant="primary")
                t11_run2 = gr.Button("🔁 演示 2：Wrap-style（模型调用自动重试）")
                t11_run3 = gr.Button("🧱 演示 3：类式中间件（自定义状态计数）")
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
                     "先玩免费的「本地安检门」（零 Token 毫秒级），再跑完整中间件演示看模型性护栏如何工作。"))
        with gr.Row(equal_height=True):
            with gr.Column(scale=2, elem_classes=["col-card"]):
                t12_in = gr.Textbox(label="输入测试文本（试试黑名单词或邮箱）", lines=5,
                                    value="联系我 admin@example.com，我想学习 hack 技术")
                t12_check_btn = gr.Button("🚪 本地安检门检测 (免费 · 确定性护栏)", variant="primary")
                t12_selftest_btn = gr.Button("🧪 运行出厂自测（免费 · run_self_tests）")
            with gr.Column(scale=3, elem_classes=["col-card"]):
                t12_out = gr.Textbox(label="安检结果（拦截判定 + 脱敏后文本）", lines=8,
                                     placeholder="点击「本地安检门」后立即出结果…")
        with gr.Row(equal_height=True):
            t12_run1 = gr.Button("🛡️ 演示：PII 中间件（LLM）", scale=1)
            t12_run2 = gr.Button("🧱 演示：自定义输入/输出护栏（LLM）", scale=1)
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
        with gr.Row(equal_height=True):
            preset1 = gr.Button("💻 5000元编程轻薄本", scale=1)
            preset2 = gr.Button("🎧 2000元降噪耳机", scale=1)
            preset3 = gr.Button("📱 3000元性能手机", scale=1)
            preset4 = gr.Button("🖥️ 千元4K显示器避坑", scale=1)
        with gr.Row(equal_height=True):
            with gr.Column(scale=3):
                with gr.Row(equal_height=True):
                    t13_session = gr.Textbox(label="会话 ID（一份记忆）", value="buyer_user_01",
                                             elem_id="session-13", scale=1)
                    t13_uid = gr.Textbox(label="顾客 ID（Store 画像注入，可换着试）", value="user-veteran",
                                         placeholder="如 user-veteran / user-newbie", scale=1)
                t13_chat = gr.Chatbot(label="SmartBuyer 选购问诊", height="44vh", elem_id="chat-13", resizable=True,
                                      buttons=["copy"], avatar_images=("🧑‍🛒", "🛡️"),
                                      layout="bubble", group_consecutive_messages=False,
                                      placeholder="说说你的预算、用途和纠结点，参谋马上开工…")
                with gr.Row(equal_height=True, elem_id="composer-row-13"):
                    t13_query = gr.Textbox(lines=3, scale=10, show_label=False, container=False,
                                           placeholder="", elem_id="composer-13")
                    t13_btn = gr.Button("🛒 发送", variant="primary", scale=1, size="sm")
                    t13_new = gr.Button("🔄 新会话", scale=1, size="sm")
                t13_tip = gr.Markdown("")
            with gr.Column(scale=2):
                t13_steps = gr.Textbox(label="🔍 工具调用与画像注入明细（实时）", lines=10, interactive=False,
                                       buttons=["copy"], elem_id="log-13")
                t13_audit = gr.Textbox(label="📊 Token 与财务账单", lines=3, interactive=False)
        with gr.Row(equal_height=True):
            with gr.Column(scale=2, elem_classes=["col-card"]):
                t13_demand = gr.Textbox(label="一键结构化报表：输入预算与要求", lines=4,
                                        value="预算 2000 元，想买一款佩戴舒服、降噪给力、音质好的头戴式耳机，经常坐飞机和高铁使用。")
                t13_report_btn = gr.Button("🧾 生成 Pydantic 标准决策报表", variant="primary")
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
        t13_report_btn.click(tab13_report, inputs=t13_demand, outputs=t13_report)

    # ================= 导航切换 =================
    page_groups = [pg1, pg2, pg3, pg4, pg5, pg6, pg7, pg8, pg9, pg10, pg11, pg12, pg13]

    def show_page(selected):
        return [gr.update(visible=(selected == name)) for name in PAGES]

    page_selector.change(show_page, inputs=page_selector, outputs=page_groups)

    # ================= 页脚 =================
    gr.HTML("""
    <div class="footer">
      🌊 <b>Vibe Coding 开源教学知识库</b> · 第九章配套实验台（13 关卡）｜
      📖 <a href="https://docs.langchain.com/" target="_blank">LangChain 官方文档</a> ｜
      🔍 每页都有「过程透视」终端 · 拒绝黑盒
      <br/>Powered by LangChain 1.x · Gradio · 模型密钥存放于 .env，请勿外传
    </div>
    """)

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860, share=False, theme=THEME, css=custom_css)
