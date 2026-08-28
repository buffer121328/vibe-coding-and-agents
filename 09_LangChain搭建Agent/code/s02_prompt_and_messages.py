"""
s02_prompt_and_messages.py - LangChain 提示词模板与上下文消息流
------------------------------------------------------------------
对应章节：9.2 Prompt 模板与上下文消息流
核心功能：
1. 掌握 SystemMessage / HumanMessage / AIMessage / ToolMessage 四大消息类型
2. 使用 ChatPromptTemplate 进行动态变量填充
3. 使用 MessagesPlaceholder 动态插入历史多轮会话
4. Few-Shot 少样本提示词模板实战
"""

from langchain_core.prompts import (
    ChatPromptTemplate,
    MessagesPlaceholder,
    FewShotChatMessagePromptTemplate,
    PromptTemplate
)
from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage
)
from rich.console import Console
from rich.panel import Panel
from s01_model_io import get_chat_model

console = Console()

def demo_message_types():
    """演示 1：四大核心消息类型"""
    console.print(Panel("[bold cyan]1. 四大核心消息类型 (Message Types)[/bold cyan]", expand=False))
    
    messages = [
        SystemMessage(content="你是一位专业严谨的 Python 架构师。"),
        HumanMessage(content="请问什么是 GIL？"),
        AIMessage(content="GIL 是全局解释器锁（Global Interpreter Lock），用来限制多线程并发执行字节码。"),
        ToolMessage(content="{'gil_enabled': True}", tool_call_id="call_12345")
    ]
    
    for msg in messages:
        console.print(f"[bold yellow][{msg.type.upper()}][/bold yellow] {msg.content}")

def demo_chat_prompt_template():
    """演示 2：ChatPromptTemplate 动态模板构建"""
    console.print(Panel("[bold cyan]2. ChatPromptTemplate 动态多角色模板[/bold cyan]", expand=False))
    
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", "你是一名精通 {domain} 领域的翻译专家，目标是将内容翻译为生动优雅的 {target_lang}。"),
        ("human", "请翻译以下文本：\n{source_text}")
    ])
    
    # 填充变量
    formatted_messages = prompt_template.format_messages(
        domain="计算机科学与 AI",
        target_lang="中文",
        source_text="Vibe coding is an intent-driven programming paradigm powered by LLMs."
    )
    
    console.print("[bold green]格式化后的消息序列：[/bold green]")
    for msg in formatted_messages:
        console.print(f"- [{msg.type}]: {msg.content}")
        
    # 调用模型
    llm = get_chat_model()
    try:
        response = llm.invoke(formatted_messages)
        console.print(f"\n[bold blue]翻译结果：[/bold blue]{response.content}")
    except Exception as e:
        console.print(f"[red]模型调用跳过或报错：{e}[/red]")

def demo_messages_placeholder():
    """演示 3：MessagesPlaceholder 动态会话历史注入"""
    console.print(Panel("[bold cyan]3. MessagesPlaceholder 动态插入多轮历史[/bold cyan]", expand=False))
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个幽默风趣的客服小助手。"),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{user_input}")
    ])
    
    # 模拟历史对话
    chat_history = [
        HumanMessage(content="你好，我叫小明，我买的键盘一直没发货。"),
        AIMessage(content="小明你好！别着急，我已经帮你查到物流单号了，正在打包中呢！")
    ]
    
    # 组合为完整输入
    rendered = prompt.invoke({
        "history": chat_history,
        "user_input": "那我大概还要等多久能收到？"
    })
    
    console.print("[bold green]注入历史后的完整上下文：[/bold green]")
    for m in rendered.messages:
        console.print(f"• [{m.type}]: {m.content}")

def demo_few_shot_prompt():
    """演示 4：Few-Shot 少样本示例模板"""
    console.print(Panel("[bold cyan]4. Few-Shot 少样本模版（让大模型模仿特定风格）[/bold cyan]", expand=False))
    
    # 定义少样本示例
    examples = [
        {"input": "这个手机电池真耐用", "output": "【正面评价】续航表现优异"},
        {"input": "屏幕边缘有划痕，差评！", "output": "【负面评价】外观品控瑕疵"},
        {"input": "物流还行，包装一般般", "output": "【中性评价】服务一般/包装普通"}
    ]
    
    example_prompt = ChatPromptTemplate.from_messages([
        ("human", "{input}"),
        ("ai", "{output}")
    ])
    
    few_shot_prompt = FewShotChatMessagePromptTemplate(
        example_prompt=example_prompt,
        examples=examples
    )
    
    final_prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个电商评论情感分析机器人，请按照示例格式对用户评论进行结构化分类。"),
        few_shot_prompt,
        ("human", "{input}")
    ])
    
    rendered = final_prompt.invoke({"input": "用了一周突然开不了机，售后态度还极差！"})
    console.print(f"[bold green]Few-Shot 渲染结果：[/bold green]\n{rendered.to_string()}")

if __name__ == "__main__":
    console.print("[bold magenta]🚀 LangChain 1.x Prompt 模板与上下文消息流演示[/bold magenta]\n")
    demo_message_types()
    console.print("-" * 50)
    demo_chat_prompt_template()
    console.print("-" * 50)
    demo_messages_placeholder()
    console.print("-" * 50)
    demo_few_shot_prompt()
