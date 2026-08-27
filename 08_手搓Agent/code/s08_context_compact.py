"""
s08_context_compact.py - 8.8 上下文工程与“截断 + 压缩”双轨机制 (Token 预算、裁剪截断与 /compact 摘要)
==============================================================================
工业级 Coding Agent（参考 learn-claude-code / deepagents）必备的上下文管理体系：
1. 【截断轨 (Truncation)】0ms 零延迟、0 API 成本的硬防御：
   - 工具输出首尾截断 (Tool Result Budget: Head 20 + Tail 20)
   - 消息滑动窗口截断 (Sliding Window FIFO: 锁定 System Prompt，按 Token 预算向前丢弃过期轮次)
2. 【压缩轨 (Compression)】基于大模型语义理解的深度防线：
   - 深度历史摘要 (/compact: 将数十轮试错与长日志提炼为结构化《前情提要背景摘要》)
3. 【全策略对比 (Compare Matrix)】：多维度对比截断 vs 压缩的 Token 收益、时延与信息保留度
==============================================================================
"""

import time
import tiktoken
from typing import List, Dict, Any, Tuple
from s01_env_setup import ZhipuGLMClient

def estimate_tokens(messages: List[Dict[str, Any]]) -> int:
    """🧮 估算当前消息列表占用的 Token 数量"""
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
    except Exception:
        encoding = None

    total = 0
    for msg in messages:
        content = str(msg.get("content", ""))
        if encoding:
            total += len(encoding.encode(content)) + 4
        else:
            # 中英混合文本：粗略按 1 token ≈ 1.5 字符估算
            total += int(len(content) / 1.5) + 4
    return total

def parse_raw_dialogue_to_messages(raw_text: str) -> List[Dict[str, Any]]:
    """
    💬 智能多轮对话解析器：将自然语言长对话文本转换为标准 messages 列表
    支持识别：“用户：/ 助理：”、“User: / Assistant:”、“Human: / AI:” 等常见格式
    """
    lines = raw_text.strip().splitlines()
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": "你是一个资深全栈工程师与智能编程助手。"}
    ]
    
    current_role = None
    current_content: List[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_content:
                current_content.append("")
            continue

        # 匹配用户角色标识
        if any(stripped.startswith(prefix) for prefix in ["用户：", "用户:", "User:", "user:", "Human:", "human:"]):
            if current_role and current_content:
                messages.append({"role": current_role, "content": "\n".join(current_content).strip()})
                current_content = []
            current_role = "user"
            content = stripped.split(":", 1)[-1] if ":" in stripped else stripped.split("：", 1)[-1]
            current_content.append(content.strip())
        # 匹配助理角色标识
        elif any(stripped.startswith(prefix) for prefix in ["助理：", "助理:", "Assistant:", "assistant:", "AI:", "ai:"]):
            if current_role and current_content:
                messages.append({"role": current_role, "content": "\n".join(current_content).strip()})
                current_content = []
            current_role = "assistant"
            content = stripped.split(":", 1)[-1] if ":" in stripped else stripped.split("：", 1)[-1]
            current_content.append(content.strip())
        else:
            # 属于上一条消息的多行延续内容（如代码块、报错日志等）
            if current_role is None:
                current_role = "user"
            current_content.append(line)

    if current_role and current_content:
        messages.append({"role": current_role, "content": "\n".join(current_content).strip()})

    # 如果无法解析出多轮，则作为单一用户消息
    if len(messages) == 1 and raw_text.strip():
        messages.append({"role": "user", "content": raw_text.strip()})

    return messages


class ContextManager:
    """
    🗜️ Agent 上下文工程管理器（双轨防御体系）：
    - 截断轨：工具输出首尾裁剪 (Tool Result Budget) + 滑动窗口 Token 预算硬裁剪 (Sliding Window FIFO)
    - 压缩轨：手写 /compact 深度历史摘要与自适应水位线触发
    """
    def __init__(
        self,
        client: ZhipuGLMClient,
        max_context_tokens: int = 4000,
        compact_threshold: float = 0.75, # 达到 75% 容量时触发压缩
        tool_result_line_limit: int = 40,
    ):
        self.client = client
        self.max_tokens = max_context_tokens
        self.compact_threshold_tokens = int(max_context_tokens * compact_threshold)
        self.tool_line_limit = tool_result_line_limit

    # ==========================================================================
    # ✂️ 第一轨：截断策略 (Truncation Track) —— 0ms 零延迟、0 API 成本
    # ==========================================================================
    def truncate_tool_result(self, raw_result: str, line_limit: int = None) -> str:
        """
        ✂️ 策略 1：工具超长输出首尾截断 (Tool Result Budget)
        【生活化比喻】像折叠 50 页体检单：只看前面诊断 + 后面异常，中间正常流水直接折叠。
        """
        limit = line_limit or self.tool_line_limit
        lines = raw_result.splitlines()
        if len(lines) <= limit:
            return raw_result

        half = limit // 2
        omitted = len(lines) - limit
        truncated_lines = (
            lines[:half]
            + [f"\n... ✂️ [中间已自动省略 {omitted} 行冗余输出，保留首尾 {limit} 行核心日志] ...\n"]
            + lines[-half:]
        )
        return "\n".join(truncated_lines)

    def truncate_sliding_window(
        self, 
        messages: List[Dict[str, Any]], 
        max_tokens: int = None, 
        preserve_recent_turns: int = 2
    ) -> Tuple[List[Dict[str, Any]], str, int]:
        """
        🪟 策略 2：基于 Token 预算的滑动窗口截断 (Sliding Window FIFO Truncation)
        【工作原理】
        1. 永久锁定第 0 条 System Prompt（核心人设与全局规则绝不丢失）；
        2. 永久保留最近 N 轮对话（preserve_recent_turns，确保当前连贯性）；
        3. 从最老的早期历史（索引 1 开始）向前逐条剔除，直到总 Token 降至预算上限之内；
        4. 耗时 0ms，无需调用任何 LLM API。
        """
        budget = max_tokens or self.max_tokens
        curr_tokens = estimate_tokens(messages)
        if curr_tokens <= budget:
            return messages, f"🟢 无需截断：当前 Token 占用 {curr_tokens} <= 预算 {budget}", 0

        if len(messages) <= 3:
            return messages, "⚠️ 消息轮次极少，无法进一步截断", 0

        has_system = (messages[0].get("role") == "system")
        system_msg = messages[0] if has_system else None
        
        # 待处理的消息体
        body_messages = messages[1:] if has_system else messages[:]
        min_preserve = max(preserve_recent_turns * 2, 2)
        
        if len(body_messages) <= min_preserve:
            return messages, "⚠️ 历史消息已达保留底线，无法继续丢弃", 0

        dropped_count = 0
        # 从最旧的消息开始依次剔除，直到满足 Token 预算或达到最小保留轮次
        while len(body_messages) > min_preserve:
            candidate = ([system_msg] if system_msg else []) + body_messages
            if estimate_tokens(candidate) <= budget:
                break
            body_messages.pop(0)
            dropped_count += 1

        final_messages = ([system_msg] if system_msg else []) + body_messages
        after_tokens = estimate_tokens(final_messages)
        saved_rate = ((curr_tokens - after_tokens) / curr_tokens) * 100

        info = (
            f"✂️ 滑动窗口截断完成（耗时 0ms）：\n"
            f"- 丢弃早期过期消息: {dropped_count} 条\n"
            f"- 保留 System 规则 + 最近 {len(body_messages)} 条交互\n"
            f"- Token 变化: {curr_tokens} ➔ {after_tokens} (释放 {saved_rate:.1f}%)"
        )
        return final_messages, info, dropped_count

    def truncate_by_turn(self, messages: List[Dict[str, Any]], max_turns: int = 4) -> Tuple[List[Dict[str, Any]], str]:
        """按轮次数量的硬滑动窗口截断（保留 System Prompt + 最近 N 轮）"""
        if len(messages) <= (max_turns * 2 + 1):
            return messages, f"消息轮次未超标 (<= {max_turns} 轮)"
        
        system_msg = messages[0] if messages[0].get("role") == "system" else None
        recent = messages[-(max_turns * 2):]
        truncated = ([system_msg] if system_msg else []) + recent
        return truncated, f"已保留 System 设定与最近 {max_turns} 轮对话 (丢弃早期 {len(messages) - len(truncated)} 条)"

    # ==========================================================================
    # 📦 第二轨：压缩策略 (Compression Track) —— 语义深度提炼、保留核心 Facts
    # ==========================================================================
    def compact_history(
        self, 
        messages: List[Dict[str, Any]], 
        max_summary_words: int = 250
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        📦 策略 3：手写 /compact 深度历史摘要
        【生活化比喻】像秘书写《会议决议备忘录》：把 20 轮试错流水账提炼成一页核心事实。
        【工作原理】
        1. 提取 System Prompt 与最近 2 轮对话；
        2. 将中间冗长的早期多轮对话打包提交给轻量大模型；
        3. 提炼出结构化的事实：用户目标、技术选型、已解决的 Bug、修改的文件、遗留 Todo；
        4. 重新组装上下文：System + 📋【前情提要背景摘要】+ 最近 2 轮。
        """
        before_tokens = estimate_tokens(messages)
        
        # 边界保护：若消息极少或总 Token 已经非常少（如 < 300），压缩反而会增加摘要模板开销
        if len(messages) <= 3:
            return messages, "⚠️ 当前消息轮次少于 3 条，无需执行深度压缩。"
        if before_tokens < 350:
            return messages, f"💡 当前上下文仅 {before_tokens} Token（极小体积），直接压缩反而会增加摘要系统词开销，建议继续对话。"

        system_msg = (
            messages[0] 
            if messages and messages[0].get("role") == "system" 
            else {"role": "system", "content": "你是一个资深全栈工程师与智能编程助手。"}
        )
        # 保留最近 2 轮（4 条）或 1 轮（2 条）最新交互，其余早期历史全部用于压缩
        preserve_tail_count = 2 if len(messages) >= 6 else 1
        history_to_compress = messages[1:-preserve_tail_count]
        recent_messages = messages[-preserve_tail_count:]

        prompt = f"""你是一个专业的 AI 上下文压缩专家。请对以下过往多轮交互历史进行高度结构化、高信息密度的前情提要提炼：

【提炼规则】
1. 🎯 核心目标与技术栈：提取用户的核心开发诉求、技术选型与偏好；
2. 🛠️ 关键事实与已完成项：列出已排查解决的 Bug、修改或创建的关键文件、确定的参数；
3. ⚠️ 丢弃所有冗余流水账：忽略中间反复试错的废话、长篇打印日志、打招呼碎碎念；
4. 📝 输出控制：输出一段 {max_summary_words} 字以内的 Markdown 结构化摘要，包含「背景目标」、「已达成事实」、「当前进展状态」。

【待压缩的多轮交互历史】：
{str(history_to_compress)}
"""
        start_t = time.time()
        try:
            res = self.client.chat([{"role": "user", "content": prompt}], temperature=0.2)
            summary_text = res.choices[0].message.content.strip()
            elapsed_ms = int((time.time() - start_t) * 1000)
        except Exception as e:
            summary_text = f"过往历史已提炼 (摘要调用降级: {e})"
            elapsed_ms = 0

        compacted_messages = [
            system_msg,
            {
                "role": "system",
                "content": f"📋 【/compact 历史背景与前情提要摘要】:\n{summary_text}"
            }
        ] + recent_messages

        after_tokens = estimate_tokens(compacted_messages)
        saved_tokens = max(0, before_tokens - after_tokens)
        comp_rate = (saved_tokens / max(before_tokens, 1)) * 100

        info = (
            f"📦 /compact 深度压缩完成（LLM 耗时 {elapsed_ms}ms）：\n"
            f"- Token 变化: {before_tokens} ➔ {after_tokens} (净节约 {saved_tokens} Tokens，压缩率 {comp_rate:.1f}%)\n"
            f"- 结构提炼: 提炼了前 {len(history_to_compress)} 条多轮历史，保留 System 设定与最近 {len(recent_messages)} 条对话"
        )
        return compacted_messages, info

    def check_and_compress(self, messages: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], bool, str]:
        """🚨 自动容量水位线检测并触发决策（MiniAgent 闭环调用）"""
        current_tokens = estimate_tokens(messages)
        if current_tokens > self.compact_threshold_tokens:
            new_msgs, info = self.compact_history(messages)
            return new_msgs, True, f"🚨 触发自动压缩（当前 {current_tokens} > 阈值 {self.compact_threshold_tokens}）\n{info}"
        return messages, False, f"🟢 当前 Token 占用正常 ({current_tokens} / {self.max_tokens})"

    # ==========================================================================
    # ⚖️ 全策略对比矩阵 (Strategy Comparison Matrix)
    # ==========================================================================
    def compare_all_strategies(
        self, 
        messages: List[Dict[str, Any]], 
        budget_tokens: int = 800
    ) -> Dict[str, Any]:
        """
        📊 一键并行对比：原始完整 vs 滑动窗口截断 vs /compact 深度压缩
        返回各策略的 Token 消耗、压缩幅度、耗时与保留能力评估
        """
        raw_tokens = estimate_tokens(messages)
        
        # 1. 滑动截断
        t0 = time.time()
        trunc_msgs, trunc_info, dropped = self.truncate_sliding_window(messages, max_tokens=budget_tokens)
        trunc_ms = int((time.time() - t0) * 1000)
        trunc_tokens = estimate_tokens(trunc_msgs)

        # 2. 深度压缩
        compact_msgs, compact_info = self.compact_history(messages)
        compact_tokens = estimate_tokens(compact_msgs)

        return {
            "raw": {
                "tokens": raw_tokens,
                "msg_count": len(messages),
                "latency_ms": 0,
                "info_retention": "100% (完全保留，但高昂且容易 Lost in the Middle)",
            },
            "truncation": {
                "tokens": trunc_tokens,
                "msg_count": len(trunc_msgs),
                "saved_rate": f"{((raw_tokens - trunc_tokens) / max(raw_tokens, 1)) * 100:.1f}%",
                "latency_ms": trunc_ms,
                "info_retention": "低 (早期对话细节彻底丢弃，仅保留近期轮次)",
                "info": trunc_info,
                "messages": trunc_msgs,
            },
            "compact": {
                "tokens": compact_tokens,
                "msg_count": len(compact_msgs),
                "saved_rate": f"{((raw_tokens - compact_tokens) / max(raw_tokens, 1)) * 100:.1f}%",
                "info_retention": "极高 (LLM 语义提炼，技术选型/已修Bug/项目目标完整保留)",
                "info": compact_info,
                "messages": compact_msgs,
            }
        }


# ==============================================================================
# 🧪 独立测试套件
# ==============================================================================
if __name__ == "__main__":
    client = ZhipuGLMClient()
    cm = ContextManager(client, max_context_tokens=1200)

    print("==================================================================")
    print("✂️ 1. 工具超长输出首尾截断测试 (Tool Result Budget)")
    print("==================================================================")
    mock_log = "\n".join([
        f"[2026-08-27 10:00:{i:02d}] INFO Service-Worker-{i%4}: processing batch {i}, status=200, db_pool_active=12"
        for i in range(120)
    ])
    truncated_log = cm.truncate_tool_result(mock_log, line_limit=20)
    print(f"原始行数: {len(mock_log.splitlines())} 行 ➔ 截断后: {len(truncated_log.splitlines())} 行")
    print("截断效果预览:\n" + truncated_log[:300] + "\n...\n" + truncated_log[-200:])

    print("\n==================================================================")
    print("🛒 2. 模拟真实长对话（电商系统全栈开发 + 支付排错 ~1800 Tokens）")
    print("==================================================================")
    long_dialogue_text = """用户：你好，我正在用 Vue3 + FastAPI 重构电商系统的收银台模块，请帮我设计架构。
助理：收到！建议采用分层架构：前端 Pinia 管理支付状态机（Pending/Paying/Success/Failed），后端 FastAPI 提供防重下单接口，接入微信与支付宝 SDK，使用 Redis 分布式锁保障幂等性。
用户：我按照你的建议写了支付接口，但是压测时并发一高就报 500 错误，日志显示：psycopg2.OperationalError: deadlock detected，该怎么排查？
助理：这是高并发下的数据库死锁！原因是在更新库存表 (inventory) 和创建订单表 (orders) 时锁获取顺序不一致。排查方案：
1. 统一所有事务内的加锁顺序（始终先锁 orders 再锁 inventory）；
2. 使用 `SELECT ... FOR UPDATE` 时按商品 ID 升序排序加锁；
3. 将扣减库存逻辑改为原子 SQL：`UPDATE inventory SET stock = stock - 1 WHERE id = 101 AND stock > 0`。
用户：改完原子 SQL 后死锁解决了！现在前端想接入二维码轮询支付状态，帮我写个轮询组件。
助理：没问题，这是使用 Vue3 `<script setup>` 编写的支付二维码与 2 秒间隔轮询组件代码：
```vue
<template>
  <div class="pay-box">
    <img :src="qrCodeUrl" />
    <p v-if="paying">支付中，请使用微信扫码...</p>
  </div>
</template>
<script setup>
import { ref, onMounted, onUnmounted } from 'vue';
const paying = ref(true);
let timer = null;
const checkStatus = async () => {
  const res = await fetch('/api/pay/status');
  if (res.status === 200) { paying.value = false; clearInterval(timer); }
};
onMounted(() => { timer = setInterval(checkStatus, 2000); });
onUnmounted(() => { clearInterval(timer); });
</script>
```
用户：太棒了！现在支付已联调通过。接下来我们要开发退款审批流模块，需要对接财务 ERP。
助理：收到，退款审批流建议设计为状态机：用户申请 ➔ 客服初审 ➔ 财务复核 ➔ 触发原路退款 ➔ 同步 ERP 凭证。我为你生成退款数据表模型与审批状态枚举。"""

    parsed_messages = parse_raw_dialogue_to_messages(long_dialogue_text)
    raw_tokens = estimate_tokens(parsed_messages)
    print(f"解析多轮消息条数: {len(parsed_messages)} 条，总 Token 估算: {raw_tokens}")

    print("\n==================================================================")
    print("🪟 3. 滑动窗口截断测试 (Token 预算限制 600)")
    print("==================================================================")
    trunc_msgs, trunc_info, dropped = cm.truncate_sliding_window(parsed_messages, max_tokens=600)
    print(trunc_info)
    print(f"截断后保留条数: {len(trunc_msgs)} 条，最终 Token: {estimate_tokens(trunc_msgs)}")

    print("\n==================================================================")
    print("📦 4. 手写 /compact 深度历史压缩测试")
    print("==================================================================")
    compact_msgs, compact_info = cm.compact_history(parsed_messages)
    print(compact_info)
    print("\n【压缩后上下文内容预览】:")
    for i, m in enumerate(compact_msgs):
        print(f"  [{i}] [{m['role']}] {str(m['content'])[:120]}...")
