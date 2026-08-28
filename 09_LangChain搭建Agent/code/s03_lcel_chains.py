"""
s03_lcel_chains.py - LCEL 表达式语言与流式链式编排
------------------------------------------------------------------
对应章节：9.3 LCEL 表达式语言与流式调度
核心功能：
1. 掌握 LCEL 核心管道符 `|` 与 Runnable 协议标准
2. 使用 StrOutputParser 进行简洁文本提取
3. 使用 RunnableParallel、RunnablePassthrough 实现多分支并行管道
4. 使用 RunnableLambda 插入自定义业务逻辑函数
5. 使用 with_fallbacks() 实现多模型容灾降级
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import (
    RunnableParallel,
    RunnablePassthrough,
    RunnableLambda
)
from rich.console import Console
from rich.panel import Panel
from s01_model_io import get_chat_model

console = Console()

def demo_basic_lcel_chain():
    """演示 1：基础 LCEL 管道流 (Prompt | Model | StrOutputParser)"""
    console.print(Panel("[bold cyan]1. 基础 LCEL 链：Prompt | LLM | StrOutputParser[/bold cyan]", expand=False))
    
    prompt = ChatPromptTemplate.from_template("请用一句话幽默地解释 {concept} 的本质。")
    llm = get_chat_model()
    parser = StrOutputParser()
    
    # 极简 LCEL 组装
    chain = prompt | llm | parser
    
    console.print("[dim]LCEL 架构：ChatPromptTemplate ➔ ChatOpenAI ➔ StrOutputParser[/dim]")
    try:
        result = chain.invoke({"concept": "递归函数"})
        console.print(f"[bold green]输入：[/bold green]递归函数")
        console.print(f"[bold blue]输出：[/bold blue]{result}\n")
    except Exception as e:
        console.print(f"[red]执行报错：{e}[/red]")

def demo_parallel_chains():
    """演示 2：RunnableParallel 并行分支与聚合"""
    console.print(Panel("[bold cyan]2. RunnableParallel 多任务并行分支[/bold cyan]", expand=False))
    
    llm = get_chat_model()
    parser = StrOutputParser()
    
    # 分支 1：写赞美诗
    poem_chain = (
        ChatPromptTemplate.from_template("为主题 '{topic}' 写两句优美的赞美诗。")
        | llm
        | parser
    )
    
    # 分支 2：写犀利吐槽
    roast_chain = (
        ChatPromptTemplate.from_template("为主题 '{topic}' 写两句程序员视角的犀利吐槽。")
        | llm
        | parser
    )
    
    # 汇总分支：并行执行两个子链
    map_chain = RunnableParallel({
        "topic": RunnablePassthrough(),
        "praise": poem_chain,
        "roast": roast_chain
    })
    
    # 终极聚合链
    summary_prompt = ChatPromptTemplate.from_template(
        "【主题】：{topic}\n"
        "【赞美面】：{praise}\n"
        "【吐槽面】：{roast}\n"
        "请作为客观评论家，给出一句 20 字以内的综合结语。"
    )
    
    full_chain = map_chain | summary_prompt | llm | parser
    
    try:
        console.print("[bold yellow]正在并行执行双分支管道...[/bold yellow]")
        result = full_chain.invoke({"topic": "加班文化"})
        console.print(f"[bold blue]最终综合点评：[/bold blue]\n{result}")
    except Exception as e:
        console.print(f"[red]并行执行报错：{e}[/red]")

def demo_custom_lambda():
    """演示 3：RunnableLambda 注入原生 Python 过滤与处理"""
    console.print(Panel("[bold cyan]3. RunnableLambda 自定义函数无缝混编[/bold cyan]", expand=False))
    
    def sanitize_input(text: str) -> str:
        """过滤掉输入中的敏感关键字"""
        clean_text = text.replace("垃圾", "**").replace("笨蛋", "**")
        return clean_text.strip()
    
    def count_length(text: str) -> dict:
        """包装为统计结果字典"""
        return {"content": text, "char_count": len(text)}
    
    llm = get_chat_model()
    
    chain = (
        RunnableLambda(sanitize_input)
        | ChatPromptTemplate.from_template("将以下文本翻译为英文：{input}")
        | llm
        | StrOutputParser()
        | RunnableLambda(count_length)
    )
    
    try:
        raw_text = " 这款软件写的太垃圾了，完全是个笨蛋设计！ "
        console.print(f"[bold green]原始输入：[/bold green]{raw_text}")
        output = chain.invoke(raw_text)
        console.print(f"[bold blue]经过脱敏翻译与字数统计后的结果：[/bold blue]{output}")
    except Exception as e:
        console.print(f"[red]执行报错：{e}[/red]")

def demo_fallbacks():
    """演示 4：with_fallbacks 容灾降级机制"""
    console.print(Panel("[bold cyan]4. with_fallbacks 高可用容灾双活[/bold cyan]", expand=False))
    
    from langchain_openai import ChatOpenAI
    
    # 模拟一个会抛出错误的不可用主模型（使用错误端点）
    primary_bad_llm = ChatOpenAI(
        model="gpt-4o-non-existent",
        api_key="bad-key",
        base_url="https://invalid.example.com/v1",
        max_retries=0
    )
    
    # 可用的备份模型
    backup_llm = get_chat_model()
    
    # 将 backup_llm 绑定为主模型的 fallback
    resilient_llm = primary_bad_llm.with_fallbacks([backup_llm])
    
    chain = ChatPromptTemplate.from_template("什么是容灾备份？请用 15 个字回答。") | resilient_llm | StrOutputParser()
    
    try:
        console.print("[bold yellow]正在发起请求（主模型故意报错，自动触发 Fallback 切换）...[/bold yellow]")
        res = chain.invoke({})
        console.print(f"[bold green]✅ 成功由备用模型返回：[/bold green]{res}")
    except Exception as e:
        console.print(f"[red]全部模型调用失败：{e}[/red]")

if __name__ == "__main__":
    console.print("[bold magenta]🚀 LangChain 1.x LCEL 链式编排与流式调度演示[/bold magenta]\n")
    demo_basic_lcel_chain()
    console.print("-" * 50)
    demo_parallel_chains()
    console.print("-" * 50)
    demo_custom_lambda()
    console.print("-" * 50)
    demo_fallbacks()
