from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig

from agent.models import ToFlightBookingAssistant, ToBookCarRental, ToHotelBookingAssistant, \
    ToBookExcursion, ToMultiQuote
from agent.context import window
from infra.llm import tavily_tool, llm
from agent.state import State
from tools.preferences import save_preference, recall_preferences
from tools.flights import search_flights
from tools.policy import lookup_policy


class DeskAssistant:
    """助手节点的统一外壳：把「提示词 + 模型 + 工具」跑成图上的一个节点。

    主助理与四个专员都用它，区别只在构造时传进来的 runnable。

    为什么它是一个类而不是个函数：节点要能被 `add_node` 直接挂上，又要能持有
    自己那份 runnable——类实例正好两件事都装得下。

    :param runnable: 一个已经绑好提示词与工具的 Runnable（通常是 `prompt | llm.bind_tools(...)`）
    """

    def __init__(self, runnable: Runnable):
        """
        初始化助手的实例。
        :param runnable: 可以运行对象，通常是一个Runnable类型的
        """
        self.runnable = runnable

    def __call__(self, state: State, config: RunnableConfig):
        """
        调用节点，执行助手任务
        :param state: 当前工作流的状态
        :param config: 配置: 里面有旅客的信息
        :return:
        """
        while True:
            # 创建了一个无限循环，它将一直执行直到：从 self.runnable 获取的结果是有效的。
            # 如果结果无效（例如，没有工具调用且内容为空或内容不符合预期格式），循环将继续执行，
            # configuration = config.get('configurable', {})
            # user_id = configuration.get('passenger_id', None)
            # state = {**state, 'user_info': user_id}  # 从配置中得到旅客的ID，也追加到state
            # 只把最近一段历史送进模型：存档是全的，但上下文没必要那么长（见 agent/context.py）
            result = self.runnable.invoke({**state, "messages": window(state["messages"])})
            # 如果，runnable执行完后，没有得到一个实际的输出
            if not result.tool_calls and (  # 如果结果中没有工具调用，并且内容为空或内容列表的第一个元素没有"text"，则需要重新提示用户输入。
                    not result.content
                    or isinstance(result.content, list)
                    and not result.content[0].get("text")
            ):
                messages = state["messages"] + [("user", "请提供一个真实的输出作为回应。")]
                state = {**state, "messages": messages}
            else:  # 如果： runnable执行后已经得到，想要的输出，则退出循环
                break
        return {'messages': result}



# 主助理提示模板
primary_assistant_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "您是一家国内旅行平台的智能旅行管家，负责国内机票、酒店、租车和景点门票的咨询与代订。"
            "您的主要职责是查询航班信息、目的地攻略和平台政策，回答旅客的问题。"
            "如果旅客要改签或退票、订酒店、租车、订景点门票，请通过调用相应的工具把任务委派给对应的专员；这些变更您自己不能直接做。"
            "只有专员才有权限为用户执行这些操作。"
            "用户并不知道有不同专员存在，因此请不要提及他们，只需通过函数调用安静地委派任务。"
            "向旅客提供详细信息，并且在确认信息不可得之前先复查数据库。"
            "搜索时请换着词多试几次：第一次没结果就换个说法或放宽条件。"
            "如果确实查不到，如实说明，不要编造航班号、酒店名或价格。"
            "涉及价格、退改规则这类政策问题时，用 lookup_policy 查平台规则后再回答。"
            "\n\n当前用户的行程信息:\n<Flights>\n{user_info}\n</Flights>"
            "\n当前时间: {time}.",
        ),
        ("placeholder", "{messages}"),
    ]
).partial(time=datetime.now())

# 定义主助理使用的工具（tavily_tool 为可选：未配置 TAVILY_API_KEY 时为 None，不加入工具池）
primary_assistant_tools = [
    tool for tool in [
        tavily_tool,  # 全网搜索工具（可选）
        search_flights,  # 搜索航班的工具
        lookup_policy,  # 查找公司政策的工具
        save_preference,  # 记住用户长期偏好（Store，见第 10 节）
        recall_preferences,  # 回忆用户长期偏好（Store，见第 10 节）
    ] if tool is not None
]

# 创建可运行对象，绑定主助理提示模板和工具集，包括委派给专门助理的工具
assistant_runnable = primary_assistant_prompt | llm.bind_tools(
    primary_assistant_tools
    + [
        ToFlightBookingAssistant,  # 用于转交航班更新或取消的任务
        ToBookCarRental,  # 用于转交租车预订的任务
        ToHotelBookingAssistant,  # 用于转交酒店预订的任务
        ToBookExcursion,  # 用于转交旅行推荐和其他游览预订的任务
        ToMultiQuote,  # 用于进入多业务并行比价流程（Send，见第 04 节）
    ]
)

