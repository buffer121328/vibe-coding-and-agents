"""
s06_memory_and_trimming.py - 记忆管理与会话状态持久化
------------------------------------------------------------------
对应章节：9.6 记忆管理与会话状态持久化
核心功能：
1. 🆕 LangChain 1.x 现代方案：create_agent + LangGraph Checkpointer 线程级短期记忆
2. 经典 LCEL 方案：RunnableWithMessageHistory 按 session_id 多会话隔离
3. 使用 trim_messages 进行上下文滑动窗口裁剪与 Token 预算控制
4. 跨会话长期记忆（LangGraph Store / LangMem）入门
"""

from typing import Dict
from langchain_core.chat_history import InMemoryChatMessageHistory, BaseChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    SystemMessage,
    trim_messages
)
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from rich.console import Console
from rich.panel import Panel
from s01_model_io import get_chat_model, get_chat_model_primary

console = Console()

# 模拟会话存储字典 (内存中存储各 session_id 的历史)
session_store: Dict[str, InMemoryChatMessageHistory] = {}

def get_session_history(session_id: str) -> BaseChatMessageHistory:
    """根据 session_id 提取或新建历史记录容器"""
    if session_id not in session_store:
        session_store[session_id] = InMemoryChatMessageHistory()
    return session_store[session_id]

def demo_checkpointer_memory():
    """演示 1：🆕 1.x 现代方案 —— create_agent + Checkpointer 线程级记忆"""
    console.print(Panel("[bold cyan]1. 1.x 现代方案：LangGraph Checkpointer + thread_id 记忆[/bold cyan]", expand=False))

    from langgraph.checkpoint.memory import MemorySaver   # 与 InMemorySaver 是同一个类的两个名字
    from langchain.agents import create_agent

    # 创建检查点（开发用内存版；生产用 SqliteSaver / PostgresSaver）
    checkpointer = MemorySaver()

    agent = create_agent(
        model=get_chat_model_primary(),
        tools=[],
        checkpointer=checkpointer,
    )

    config_user_a = {"configurable": {"thread_id": "thread_user_alice"}}
    config_user_b = {"configurable": {"thread_id": "thread_user_bob"}}

    console.print("[bold yellow]👉 用户 Alice 第一次提问：[/bold yellow]")
    r1 = agent.invoke({"messages": [("user", "你好！我最喜欢的编程语言是 Python，我的生日是 10 月 1 日。")]}, config=config_user_a)
    console.print(f"[bold blue]AI 回复 Alice：[/bold blue]{r1['messages'][-1].content}\n")

    console.print("[bold yellow]👉 用户 Bob 第一次提问：[/bold yellow]")
    r2 = agent.invoke({"messages": [("user", "你好！我是 Bob，我主要写 C++。")]}, config=config_user_b)
    console.print(f"[bold blue]AI 回复 Bob：[/bold blue]{r2['messages'][-1].content}\n")

    console.print("[bold yellow]👉 用户 Alice 第二次提问（检验记忆是否混淆）：[/bold yellow]")
    r3 = agent.invoke({"messages": [("user", "你还记得我最喜欢什么语言吗？我的生日是几号？")]}, config=config_user_a)
    console.print(f"[bold blue]AI 回复 Alice：[/bold blue]{r3['messages'][-1].content}\n")

def demo_runnable_with_message_history():
    """演示 2：经典 LCEL 方案 RunnableWithMessageHistory 多轮会话状态管理"""
    console.print(Panel("[bold cyan]2. 经典 LCEL 方案：RunnableWithMessageHistory 多轮对话记忆[/bold cyan]", expand=False))
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一名贴心的智能生活管家。"),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{question}")
    ])
    
    llm = get_chat_model()
    chain = prompt | llm | StrOutputParser()
    
    # 包装为带记忆的 Runnable
    with_message_history = RunnableWithMessageHistory(
        chain,
        get_session_history,
        input_messages_key="question",
        history_messages_key="history"
    )
    
    config_user_a = {"configurable": {"session_id": "session_user_alice"}}
    config_user_b = {"configurable": {"session_id": "session_user_bob"}}
    
    console.print("[bold yellow]👉 用户 Alice 第一次提问：[/bold yellow]")
    r1 = with_message_history.invoke({"question": "你好！我最喜欢的编程语言是 Python，我的生日是 10 月 1 日。"}, config=config_user_a)
    console.print(f"[bold blue]AI 回复 Alice：[/bold blue]{r1}\n")
    
    console.print("[bold yellow]👉 用户 Bob 第一次提问：[/bold yellow]")
    r2 = with_message_history.invoke({"question": "你好！我是 Bob，我主要写 C++。"}, config=config_user_b)
    console.print(f"[bold blue]AI 回复 Bob：[/bold blue]{r2}\n")
    
    console.print("[bold yellow]👉 用户 Alice 第二次提问（检验记忆是否混淆）：[/bold yellow]")
    r3 = with_message_history.invoke({"question": "你还记得我最喜欢什么语言吗？我的生日是几号？"}, config=config_user_a)
    console.print(f"[bold blue]AI 回复 Alice：[/bold blue]{r3}\n")

def demo_trim_messages():
    """演示 3：trim_messages 智能滑动窗口裁剪"""
    console.print(Panel("[bold cyan]3. trim_messages 智能 Token 窗口裁剪[/bold cyan]", expand=False))
    
    # 构造一批超长历史消息
    messages = [
        SystemMessage(content="你是核心安全系统。"),
        HumanMessage(content="这是第 1 轮提问：今天星期几？"),
        AIMessage(content="今天是星期一。"),
        HumanMessage(content="这是第 2 轮提问：明天会下雨吗？"),
        AIMessage(content="天气预报明天有小雨。"),
        HumanMessage(content="这是第 3 轮提问：后天呢？"),
        AIMessage(content="后天大晴天。"),
        HumanMessage(content="这是第 4 轮提问：大后天我要出差。"),
        AIMessage(content="收到，祝出差顺利。"),
        HumanMessage(content="最新提问：我刚才问的第一个问题是什么？")
    ]
    
    console.print(f"[bold green]原始历史消息条数：[/bold green]{len(messages)} 条")
    
    # 使用 trim_messages 策略：保留最近 4 条消息，且必须保留 system 消息
    trimmed = trim_messages(
        messages,
        max_tokens=60,  # 设定极小 token 阈值演示截断
        token_counter=len, # 简单按字符/条数统计，生产环境可使用 tiktoken
        strategy="last",
        start_on="human",
        end_on=("human", "tool"),
        include_system=True
    )
    
    console.print(f"[bold yellow]裁剪后保留消息条数：[/bold yellow]{len(trimmed)} 条\n")
    for msg in trimmed:
        console.print(f"• [{msg.type}]: {msg.content}")

def demo_store_long_term_memory():
    """演示 4：跨会话长期记忆 —— LangGraph Store + namespace 分层"""
    console.print(Panel("[bold cyan]4. 跨会话长期记忆：Store + namespace 分层[/bold cyan]", expand=False))

    from langgraph.store.memory import InMemoryStore

    store = InMemoryStore()

    # 用元组 namespace 分层："users" 层下不同用户的画像
    store.put(("users", "zhangsan"), "preferences", {"color": "black", "budget": 5000})
    store.put(("users", "zhangsan"), "purchase_history", {"last": "机械键盘"})
    store.put(("users", "lisi"), "preferences", {"color": "white"})

    # 按 (namespace, key) 精确读回，天然隔离不同用户 / 不同维度
    item = store.get(("users", "zhangsan"), "preferences")
    console.print(f"[bold blue]张三画像（精确读回）：[/bold blue]{item.value}")

    # 按 namespace 前缀批量搜索（如拉取某用户全部档案）
    items = store.search(("users", "zhangsan"))
    console.print(f"[bold blue]张三全部档案（前缀搜索）：[/bold blue]{[(i.key, i.value) for i in items]}")

if __name__ == "__main__":
    console.print("[bold magenta]🚀 LangChain 1.x 记忆管理与会话状态持久化演示[/bold magenta]\n")
    demo_checkpointer_memory()
    console.print("-" * 50)
    demo_runnable_with_message_history()
    console.print("-" * 50)
    demo_trim_messages()
    console.print("-" * 50)
    demo_store_long_term_memory()

