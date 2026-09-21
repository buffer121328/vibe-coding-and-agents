"""llm.py —— Chat 客户端：一个延迟创建的共用实例。

对应教程：11.8 / 11.4（模型工厂的课堂版）。

**为什么单独一个模块**：全仓只有一处该知道"怎么建 ChatOpenAI"，而需要它的人分布在
好几层——编排层（``answer/agent.py``）用它生成与复检，数据层（``data/knowledge_graph.py``）
用它抽三元组。数据层本该在编排层下面，可客户端建在编排层，于是数据层要反过来依赖它，
`agent → retrieve → knowledge_graph → agent` 就成了一个环。

把客户端挪到叶子模块（它不依赖任何内部模块，谁都能依赖它），环就断了：
两层各自向 ``llm`` 取实例，互相不认识。这也是"分层解耦"最常见的收益——
**不是把代码拆小，是把不该碰面的东西隔开。**

调用方一律用模块级的 ``llm``（``from ..llm import llm``），别自己建 ``ChatOpenAI``：
建出第二个实例就有两份超时与重试配置，出问题时会以为是模型抽风。
"""

from __future__ import annotations

from . import config

_llm = None


def get_llm():
    """延迟创建 Chat 客户端：导入本模块不得触发网络（离线测试依赖这一条）。

    模型和端点走 config 里成对解析好的 CHAT_*：对话与嵌入可以来自不同厂商，
    但模型名和端点不能交叉——交叉了只会得到「模型不支持」这类误导性报错。
    思考模式走 ``config.thinking_extra_body()``：课堂默认关掉 MiMo 的隐性思考，
    和完整版 ``LLM_THINKING_MODE=disabled`` 同一刀。裁判也用这一截，别只关问答。
    """
    global _llm
    if _llm is None:
        from langchain_openai import ChatOpenAI

        _llm = ChatOpenAI(
            model=config.CHAT_MODEL,
            temperature=0,
            api_key=config.CHAT_API_KEY or "sk-dummy",
            base_url=config.CHAT_API_BASE or None,
            **config.thinking_extra_body(),
        )
    return _llm


# 模块级名字 llm 的替身
class _LazyLLM:
    """模块级名字 ``llm`` 的替身：把建客户端推迟到第一次真正用它的那一刻。

    调用方要的是"一个能直接用的客户端对象"，但真的 ``ChatOpenAI`` 一建就要读密钥、
    连端点——做成模块级的实例，离线测试和 ``import forge_lite`` 就会一起炸掉。
    所以这里挂个空壳，属性访问和方法调用都原样转发给 ``get_llm()``：
    行为与用真客户端毫无区别，差别只在"什么时候建"。
    """

    def __getattr__(self, name):
        """兜底转发：本类没定义的属性（流式、回调、token 计数等）都从这里落到真客户端。

        ``name`` 是想取的属性名。它只在常规查找失败后才会被调用，所以 ``_LazyLLM``
        自己已有的属性不会绕回来——这也正是必须把 ``invoke`` 显式写出来的原因。
        """
        return getattr(get_llm(), name)

    def invoke(self, *args, **kwargs):
        """转发一次同步调用，参数一个不改地交给真客户端。

        位置参数 ``args`` 与关键字参数 ``kwargs``（也就是签名里的 ``*args`` / ``**kwargs``）
        就是 ``ChatOpenAI.invoke`` 那一套（消息或 Prompt 值、``config`` 等）。本层刻意不做
        任何加工：一旦在这里"顺手"补个默认值，线上与测试走的就不是同一条路径了。
        返回真客户端的返回值（通常是带 ``.content`` 的 ``AIMessage``）。
        """
        return get_llm().invoke(*args, **kwargs)

    def with_structured_output(self, *args, **kwargs):
        """转发结构化输出绑定，拿到一个能按 Pydantic 模型取字段的 runnable。

        位置参数 ``args`` 与关键字参数 ``kwargs``（签名里的 ``*args`` / ``**kwargs``）
        原样透传（模型类、``method=``、``strict=`` 等）。写出来只为可读性与补全提示，
        行为与走 ``__getattr__`` 完全一致。
        """
        return get_llm().with_structured_output(*args, **kwargs)


llm = _LazyLLM()
