"""
s01_model_io.py - LangChain 1.x 统一模型 I/O 与流式调用
------------------------------------------------------------------
对应章节：9.1 初识 LangChain 与生态架构
核心功能：
1. 使用 ChatOpenAI / init_chat_model 初始化模型（统一工厂）
2. 演示 invoke()、stream()、batch() 三种调用姿势
3. 提取 Token 消耗元数据与响应对象结构
"""

import os
import sys
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# 加载环境变量
load_dotenv()

console = Console()

def get_chat_model_primary(temperature: float = 0.7):
    """
    首选模型：小米 MiMo（OpenAI 兼容端点）
    读取 MIMO_API_KEY / MIMO_BASE_URL / MIMO_MODEL，未配置时向后兼容回落 OPENAI_*/MODEL_NAME。
    注意：本函数返回的是真实 ChatOpenAI 模型对象（支持 bind_tools / with_structured_output /
    create_agent）；普通 LCEL 链请直接使用 get_chat_model()（自带双模型容灾回退）。
    """
    from langchain_openai import ChatOpenAI

    api_key = os.getenv("MIMO_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    api_base = os.getenv("MIMO_BASE_URL", "") or os.getenv("OPENAI_API_BASE", "https://api.xiaomimimo.com/v1")
    model_name = os.getenv("MIMO_MODEL", "") or os.getenv("MODEL_NAME", "mimo-v2.5-pro")

    return ChatOpenAI(
        model=model_name,
        api_key=api_key or "sk-dummy-key",
        base_url=api_base,
        temperature=temperature,
        streaming=True,
        timeout=float(os.getenv("FALLBACK_TIMEOUT_SECONDS", "45")),
        max_retries=0,  # 45 秒超时不重试，超时即交给备选模型
    )

def get_chat_model_fallback(temperature: float = 0.7):
    """
    备选模型：火山方舟 (Volcengine Ark) DeepSeek
    读取 ARK_API_KEY / ARK_BASE_URL / ARK_MODEL_ENDPOINT，未配置时向后兼容回落 OPENAI_*/MODEL_NAME。
    """
    from langchain_openai import ChatOpenAI

    api_key = os.getenv("ARK_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    api_base = os.getenv("ARK_BASE_URL", "") or os.getenv("OPENAI_API_BASE", "https://ark.cn-beijing.volces.com/api/v3")
    model_name = os.getenv("ARK_MODEL_ENDPOINT", "") or os.getenv("MODEL_NAME", "deepseek-chat")

    return ChatOpenAI(
        model=model_name,
        api_key=api_key or "sk-dummy-key",
        base_url=api_base,
        temperature=temperature,
        streaming=True,
        timeout=60.0,
        max_retries=2,
    )

def get_chat_model(temperature: float = 0.7):
    """
    统一模型工厂函数（默认开启双模型容灾）：
    首选 小米 MiMo（45 秒超时 / 失败）→ 自动 with_fallbacks 回退到 备选 火山方舟 DeepSeek。
    基于 LangChain with_fallbacks() 实现，返回 Runnable，可直接用于各类 LCEL 链 / invoke / stream / batch。
    若需要真实模型对象（bind_tools / with_structured_output / create_agent），请改用 get_chat_model_primary()。
    """
    return get_chat_model_primary(temperature).with_fallbacks([get_chat_model_fallback(temperature)])

def get_chat_model_unified(temperature: float = 0.7):
    """
    LangChain 1.x 官方推荐的统一模型工厂：
    init_chat_model("厂商:模型") 一行初始化，自动路由到对应伙伴包。
    需先安装对应伙伴包（如 langchain-openai / langchain-deepseek）。
    """
    from langchain.chat_models import init_chat_model

    model_name = os.getenv("MIMO_MODEL", "mimo-v2.5-pro")
    # 使用 openai: 前缀路由到 langchain-openai（本项目已安装），可连接任意 OpenAI 兼容端点
    return init_chat_model(
        model=f"openai:{model_name}",
        temperature=temperature,
        streaming=True,
        base_url=os.getenv("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1"),
        api_key=os.getenv("MIMO_API_KEY", "") or "sk-dummy-key",
    )

def demo_sync_invoke():
    """演示 1：基础同步调用 invoke()"""
    console.print(Panel("[bold cyan]1. 基础同步调用 invoke()[/bold cyan]", expand=False))
    llm = get_chat_model()
    
    prompt = "请用一句话解释什么是 LangChain？"
    console.print(f"[bold green]用户提问：[/bold green]{prompt}")
    
    try:
        response = llm.invoke(prompt)
        console.print(f"[bold blue]模型回答：[/bold blue]{response.content}\n")
        
        # 查看元数据 (Token 统计等)
        metadata = response.response_metadata
        console.print(f"[dim]响应元数据：{metadata}[/dim]")
    except Exception as e:
        console.print(f"[red]调用出错（可能 API Key 未配置或网络异常）：{e}[/red]")

def demo_streaming_invoke():
    """演示 2：实时流式输出 stream()"""
    console.print(Panel("[bold cyan]2. 实时流式输出 stream()[/bold cyan]", expand=False))
    llm = get_chat_model()
    
    prompt = "写一首赞美程序员深夜敲代码的四句幽默打油诗。"
    console.print(f"[bold green]用户提问：[/bold green]{prompt}")
    console.print("[bold blue]模型流式输出：[/bold blue]", end="")
    
    try:
        for chunk in llm.stream(prompt):
            # chunk 是 AIMessageChunk 对象
            content = chunk.content
            sys.stdout.write(content)
            sys.stdout.flush()
        print("\n")
    except Exception as e:
        console.print(f"\n[red]流式输出出错：{e}[/red]")

def demo_batch_invoke():
    """演示 3：高效批量并发调用 batch()"""
    console.print(Panel("[bold cyan]3. 批量并发调用 batch()[/bold cyan]", expand=False))
    
    llm = get_chat_model()
    
    prompts = [
        "用三个词形容 Python",
        "用三个词形容 Rust",
        "用三个词形容 JavaScript"
    ]
    console.print(f"[bold green]批量提问：[/bold green]{prompts}")
    
    try:
        responses = llm.batch(prompts)
        table = Table(title="批量响应结果矩阵")
        table.add_column("序号", style="cyan")
        table.add_column("输入 Prompt", style="green")
        table.add_column("模型输出", style="blue")
        
        for idx, (p, r) in enumerate(zip(prompts, responses), 1):
            table.add_row(str(idx), p, r.content.strip())
            
        console.print(table)
    except Exception as e:
        console.print(f"[red]批量调用出错：{e}[/red]")

def demo_model_profiles():
    """演示 4：模型能力档案 .profile（1.1 新特性，无需发请求即可查能力）"""
    console.print(Panel("[bold cyan]4. 模型能力档案 llm.profile[/bold cyan]", expand=False))

    from langchain.chat_models import init_chat_model

    console.print("[dim]数据来自开源项目 models.dev，读取的是模型出厂能力档案，不消耗 Token。[/dim]")

    llm = get_chat_model_unified(temperature=0)
    profile = getattr(llm, "profile", None)
    if not profile:
        # 自有/小众模型未收录于 models.dev 时 profile 为 None，用官方已知档案兜底演示
        console.print("[yellow]⚠️ 当前模型未收录于 models.dev（profile 为空），改用官方档案 gpt-4o-mini 演示：[/yellow]")
        llm = init_chat_model("openai:gpt-4o-mini", temperature=0, api_key="sk-dummy")
        profile = llm.profile

    try:
        console.print(f"[bold green]模型：[/bold green]{profile.get('name', llm.model)}")
        table = Table(title="能力档案关键指标")
        table.add_column("能力项", style="cyan")
        table.add_column("是否支持", style="green")
        for key, label in [
            ("tool_calling", "Tool Calling（工具调用）"),
            ("structured_output", "结构化输出（JSON Schema）"),
            ("text_inputs", "文本输入"),
            ("image_inputs", "图片输入（多模态）"),
            ("temperature", "支持 temperature 调节"),
        ]:
            table.add_row(label, "✅ 支持" if profile.get(key) else "❌ 不支持")
        table.add_row("上下文窗口", f"{profile.get('max_input_tokens', 'N/A')} tokens")
        console.print(table)
    except Exception as e:
        console.print(f"[red]读取能力档案出错：{e}[/red]")

if __name__ == "__main__":
    console.print("[bold magenta]🚀 LangChain 1.x 模型 I/O 与流式调用演示[/bold magenta]\n")
    demo_sync_invoke()
    console.print("-" * 50)
    demo_streaming_invoke()
    console.print("-" * 50)
    demo_batch_invoke()
    console.print("-" * 50)
    demo_model_profiles()
