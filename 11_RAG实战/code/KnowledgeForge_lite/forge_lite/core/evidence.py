"""evidence.py —— 课堂版证据资格：资料够不够答、该部分答还是拒答。

蒸馏来源：完整版 ``EvidenceQualifier`` + ``EvidenceQualificationPolicy``。
对应教程：11.8 / 11.12（分级之后、生成之前，先给证据打资格，而不是生成完再找补）。

完整版用一套校准过的阈值，把每块资料分成直接证据 / 部分证据 / 背景 / 无关，
再决定 ``answered / partially_answered / insufficient_evidence / conflicting_evidence``。
Lite 用同一套状态名和同一条纪律，阈值写死、覆盖率用词面重合——课堂能手算，
读完整版时不用重新学状态机。

纪律：

- 空候选不是故障，是 ``insufficient_evidence``；三路全挂才是 ``source_unavailable``。
- 两份资料数字对不上，且问题在问这个数字 → ``conflicting_evidence``，不要和稀泥。
- 高风险词（薪酬、密码、身份证）撞上冲突 → ``human_review_required``。
- 资格不够就不要进入生成。生成模型最会把『有点像』写成『就是这样』。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping, Sequence


POLICY_VERSION = "lite-evidence-v1"
CALIBRATION_VERSION = "classroom-boundaries-v1"

# 与完整版阈值同形状：背景 < 灰区下沿 < 灰区上沿 < 直接证据。
BACKGROUND_THRESHOLD = 0.35
GRAY_ZONE_LOWER = 0.45
GRAY_ZONE_UPPER = 0.65
DIRECT_THRESHOLD = 0.75
CANDIDATE_LIMIT = 8

STATUS_ANSWERED = "answered"
STATUS_PARTIAL = "partially_answered"
STATUS_INSUFFICIENT = "insufficient_evidence"
STATUS_CLARIFY = "needs_clarification"
STATUS_CONFLICT = "conflicting_evidence"
STATUS_REVIEW = "human_review_required"
STATUS_UNAVAILABLE = "source_unavailable"

STATE_DIRECT = "direct_evidence"
STATE_PARTIAL = "partial_evidence"
STATE_BACKGROUND = "relevant_background"
STATE_IRRELEVANT = "irrelevant"
STATE_CONFLICT = "conflicting_evidence"
STATE_INSUFFICIENT = "insufficient_evidence"
STATE_INVALID = "invalid_provenance"

REASON_ZERO = "zero_results"
REASON_DIRECT = "direct_support"
REASON_PARTIAL = "partial_support"
REASON_BACKGROUND = "background_only"
REASON_IRRELEVANT = "irrelevant_context"
REASON_CONFLICT = "material_conflict"
REASON_REVIEW = "high_risk_review"
REASON_UNAVAILABLE = "all_dependencies_unavailable"
REASON_PARTIAL_OUTAGE = "partial_dependency_unavailable"
REASON_INVALID = "invalid_context_provenance"
REASON_MISSING = "missing_question_detail"

HIGH_RISK_MARKERS = ("薪酬", "工资", "密码", "身份证", "银行卡", "密级", "带宽")
CONFLICT_MARKERS = ("冲突", "不一致", "哪份为准", "互相矛盾", "两个版本")
VERSION_MARKERS = ("哪一版", "版本", "现行", "仍然生效")
# 问的是钱，资料里却没有金额，才把覆盖率压到背景区。FAQ 的「额度」是次数，不算钱。
MONEY_MARKERS = ("多少钱", "万元", "年薪", "住宿费", "薪酬", "元")
DATE_MARKERS = ("几天", "何时", "日期", "工作日")

_LATIN = re.compile(r"[A-Za-z0-9_.-]+")
_AMOUNT = re.compile(r"(\d+(?:\.\d+)?)\s*(万)?\s*元")
_DAYS = re.compile(r"(\d+)\s*个?工作日")
_STOP_GRAMS = {
    "多少", "是多", "是什", "什么", "怎么", "如何", "有哪", "哪些", "可以",
    "一般", "能否", "是否", "一下", "请问", "这个", "那个", "我们", "他们",
}
# 问法对制度用词：课堂版不调模型，用这张对照表把口语对齐到条文。
# 触发词要收口语说法（「住一晚」「能报多少」「到手」），否则问句和条文各说各话，
# 覆盖率会低到把「资料明明有答案」误判成背景/无关。
_ALIASES = {
    "住宿": ("住宿", "住宿费", "住宿标准", "住一晚", "住一宿", "过夜", "酒店"),
    "上限": ("上限", "不超过", "标准", "封顶", "最多", "能报多少", "报多少", "多少钱"),
    "报销": ("报销", "提交", "工作日", "能报", "到手", "打款", "发放"),
    "额度": ("额度", "问答", "每月", "多少次", "多少次问答"),
    "薪酬": ("薪酬", "年薪", "带宽", "P6", "薪资"),
    "打印机": ("打印机", "卡纸", "E3", "报错", "故障"),
}

# 主题核对表：（主题名，问句触发词，资料侧"该出现的词"，资料侧"特征词"）。
#
# 三列各管一件事，别混用：
# - 触发词：问句里点到这个主题就算"问了它"（含口语说法）；
# - 该出现的词：算覆盖率用，可以宽（「不超过」「元」这类量词也算证据）；
# - **特征词**：判断"这块资料在讲这个主题"，必须窄——只用名词性特征。
#   拿「元」当住宿的特征词，会让 FAQ 里的 999 元和办公用品制度的 200 元
#   都被算成住宿资料，两篇不相干的文件互相判成「证据冲突」（评测区抓出来的）。
_TOPIC_RULES = (
    ("住宿", ("住宿", "住一晚", "住一宿", "住宿费", "过夜", "酒店"),
     ("住宿", "不超过", "元"),
     ("住宿", "住宿费", "过夜", "每晚", "酒店")),
    ("额度", ("额度", "次数", "多少次", "每月"),
     ("问答", "额度", "每月", "次"),
     ("额度", "问答")),
    ("故障", ("E3", "打印机", "卡纸", "报错", "故障"),
     ("E3", "卡纸", "打印机", "报错"),
     ("E3", "卡纸", "打印机")),
    ("薪酬", ("薪酬", "P6", "带宽", "年薪", "薪资"),
     ("薪酬", "年薪", "P6", "带宽"),
     ("薪酬", "年薪", "带宽", "P6")),
    ("报销", ("报销", "提交", "到手", "工作日", "发放"),
     ("报销", "工作日", "提交", "发放"),
     ("报销",)),
    ("安全", ("密码", "账号", "红线", "客户名单", "邮箱"),
     ("密码", "账号", "红线", "私人邮箱", "邮箱"),
     ("密码", "账号", "红线", "客户名单")),
)


@dataclass(frozen=True)
class EvidencePolicy:
    """课堂阈值。改数字必须同步改测试，避免『感觉调一下』造成静默放水。

    四个覆盖度阈值从低到高卡出四档证据：``background_threshold`` 是背景区下沿
    （低于它的资料算无关），``gray_zone_lower`` 是灰区下沿（到这儿算部分证据），
    ``gray_zone_upper`` 是灰区上沿，``direct_threshold`` 是直接证据线。
    ``candidate_limit`` 是参与资格判断的资料条数上限，防止几十块一起算覆盖率把延迟拉爆。
    ``policy_version`` / ``calibration_version`` 是这两套数字的版本戳，会跟着结论一起
    写进 ``EvidenceAssessment``——评测集对不上时，先看版本戳就能分清是"判定变了"还是
    "阈值被谁改过"，不用去翻 git blame。
    """

    background_threshold: float = BACKGROUND_THRESHOLD
    gray_zone_lower: float = GRAY_ZONE_LOWER
    gray_zone_upper: float = GRAY_ZONE_UPPER
    direct_threshold: float = DIRECT_THRESHOLD
    candidate_limit: int = CANDIDATE_LIMIT
    policy_version: str = POLICY_VERSION
    calibration_version: str = CALIBRATION_VERSION

    def __post_init__(self) -> None:
        """构造时自检，把"阈值写反"这类错误拦在建对象那一刻。

        检查三件事：四个阈值都在 0 到 1 之间、它们从低到高有序（背景 ≤ 灰区下沿 ≤
        灰区上沿 ≤ 直接）、``candidate_limit`` 在 1 到 50 之间。不满足就抛 ``ValueError``。

        直接写死在 ``__init__`` 里而不是靠测试守：阈值写反不会报错，只会让所有问题
        静默走同一档结论——这种故障从输出上看不出来，必须在源头拦住。
        """
        values = (
            self.background_threshold,
            self.gray_zone_lower,
            self.gray_zone_upper,
            self.direct_threshold,
        )
        if any(value < 0 or value > 1 for value in values):
            raise ValueError("证据阈值必须在 0 到 1 之间")
        if values != tuple(sorted(values)):
            raise ValueError("证据阈值必须满足 背景 ≤ 灰区下沿 ≤ 灰区上沿 ≤ 直接")
        if self.candidate_limit <= 0 or self.candidate_limit > 50:
            raise ValueError("candidate_limit 必须在 1 到 50 之间")


@dataclass
class MissingSlot:
    """缺了哪一块信息，以及人话补充说明。

    它回答的不是"资料不够"（那是 ``state`` 的活），而是"到底缺什么"——
    ``field`` 是机器认的槽位名（如 ``unsupported_question_parts``），
    ``description`` 是给用户看的一句中文解释。分开两列是因为产品上要做两件事：
    前端按 ``field`` 决定往哪个表单项标黄，按 ``description`` 决定气泡里说什么。
    """

    field: str
    description: str

    def as_dict(self) -> dict[str, str]:
        """转成 ``{"field": ..., "description": ...}`` 的扁平字典，给前端直接吃。"""
        return asdict(self)


@dataclass
class EvidenceAssessment:
    """一次资格判断。前端证据抽屉读这些字段，不另算一遍。

    两套词各管一件事，别混着看：``state`` 说**资料**处于什么状态（直接证据 / 部分证据 /
    背景 / 无关 / 冲突），``response_status`` 说**这题该怎么办**（照答 / 部分答 / 拒答 /
    追问 / 转人工 / 来源不可用）。一份背景资料（state）完全可以对应"证据不足"而不是
    "无关"，分开记才说得清。

    ``reason_codes`` 是判定依据的机器码（``direct_support``、``material_conflict`` 等），
    给评测和埋点用；``evaluated_ids`` 是这次真正参与判断的资料 id，``supporting_ids``
    是其中够格当证据的那些；``missing`` 是 ``MissingSlot`` 列表，列清缺什么；
    ``coverage`` 是算出来的覆盖度分数；``policy_version`` / ``calibration_version``
    是当时用的阈值版本戳，让这份结论日后还能被复盘。
    """

    state: str
    response_status: str
    reason_codes: list[str]
    evaluated_ids: list[str] = field(default_factory=list)
    supporting_ids: list[str] = field(default_factory=list)
    missing: list[MissingSlot] = field(default_factory=list)
    coverage: float = 0.0
    policy_version: str = POLICY_VERSION
    calibration_version: str = CALIBRATION_VERSION

    def allows_generation(self) -> bool:
        """直接证据或部分证据才许生成；背景/冲突/不足都该停。

        返回 True 表示可以进生成环节（``response_status`` 是已回答或部分回答），
        False 表示调用方应当直接走拒答/追问话术。把它做成方法而不是让调用方自己比对
        状态名，是为了让"什么状态能生成"只有一处定义——加一个新状态时不会漏改某个分支。
        """
        return self.response_status in {STATUS_ANSWERED, STATUS_PARTIAL}

    def as_dict(self) -> dict[str, Any]:
        """转成给前端的字典：原本的字段，外加算出来的 ``allows_generation``。

        ``missing`` 里的 ``MissingSlot`` 会被摊平成一串小字典，前端不用再认一层对象。
        """
        return {
            "state": self.state,
            "response_status": self.response_status,
            "reason_codes": list(self.reason_codes),
            "evaluated_ids": list(self.evaluated_ids),
            "supporting_ids": list(self.supporting_ids),
            "missing_information": [item.as_dict() for item in self.missing],
            "coverage": self.coverage,
            "policy_version": self.policy_version,
            "calibration_version": self.calibration_version,
            "allows_generation": self.allows_generation(),
        }


def tokenize(text: str) -> set[str]:
    """中文按二字 / 三字切，英文按单词。单字重合率对中文问句太苛刻，课堂算不准。

    ``text`` 是问句或资料正文，None 与空串都当空文本处理。中文切成二元组和三元组，
    是为了让"住宿标准"和"住宿费标准"能靠"住宿"这个共有的二字片段对上——按单字切
    分母太大，覆盖率会被常见的"的、是、了"稀释到看不出差别。
    ``_STOP_GRAMS`` 里的口水词先滤掉，它们出现在任何一段文本里都不代表相关。

    返回去重后的 token 集合（英文已转小写）。
    """
    latin = {token.lower() for token in _LATIN.findall(text or "") if token.strip()}
    han = re.sub(r"[^\u4e00-\u9fff]", "", text or "")
    grams: set[str] = set()
    for size in (2, 3):
        grams.update(han[index:index + size] for index in range(len(han) - size + 1))
    return latin | {gram for gram in grams if gram not in _STOP_GRAMS}


def expand_aliases(tokens: set[str]) -> set[str]:
    """把口语词扩成制度里的说法，例如「上限」也认「不超过」。

    ``tokens`` 是 ``tokenize`` 切出来的词袋，问句和资料两侧都要过这一趟，才能在同一
    套词汇上比重合。拿着放大镜找同义词的做法不行——问"住宿能报多少"、条文写"不超过
    500 元"，字面一个词都不重合，覆盖率会低到把明明有答案的资料判成无关。

    命中任一组别名就把整组词都加进结果（``_ALIASES`` 里一组词视为等价），返回扩充后的
    新集合，入参 ``tokens`` 不动。
    """
    expanded = set(tokens)
    blob = "".join(tokens)
    for key, aliases in _ALIASES.items():
        if key in blob or any(alias in tokens or alias in blob for alias in aliases):
            expanded.update(aliases)
    return expanded


def coverage(question: str, content: str) -> float:
    """问句要点有没有落在资料里。用别名对齐后再算重合，避免单字分母把分数打穿。

    ``question`` 是用户问句，``content`` 是一块资料的正文。返回 0 到 1 的覆盖度，
    取三个口径里最高的那个：``recall``（问句的词有多少出现在资料里）、
    ``grounded``（资料里的词有多少踩在问句上，防止长资料靠体量刷分）、
    ``dimension``（主题核对，见 ``_dimension_hit``）。

    取最大值而不是加权平均，是因为这三种口径各有盲区：问句短的时候 recall 虚高、
    资料长的时候 grounded 虚高，而某个主题明确命中时前两者反而可能都很低。
    任一侧为空（问句没词或资料为空）直接返回 0.0。
    """
    query_tokens = expand_aliases(tokenize(question))
    content_tokens = expand_aliases(tokenize(content))
    if not query_tokens or not content_tokens:
        return 0.0
    overlap = query_tokens & content_tokens
    recall = len(overlap) / len(query_tokens)
    # 资料里那些也出现在问句中的词越多，越像「这块就是在答这题」
    anchored = {token for token in content_tokens if token in query_tokens or token in question}
    grounded = len(anchored) / max(len(content_tokens), 1)
    dimension = _dimension_hit(question, content)
    return max(recall, grounded, dimension)


def asked_topics(question: str) -> list[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    """问句点了哪些主题：返回 (主题名, 该出现的词, 特征词)。别名扩过的问句也算。

    ``question`` 是用户问句。匹配前先把别名扩写拼进同一个大字符串再逐个主题比对——
    正是为了让"住一晚"这种口语触发词也能认出「住宿」这个主题。返回命中的主题元组列表，
    没点名任何主题时返回空列表（调用方据此决定"不做主题判定、一律算相关"）。
    """
    blob = question + " " + " ".join(sorted(expand_aliases(tokenize(question))))
    found: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
    for name, triggers, markers, anchors in _TOPIC_RULES:
        if any(trigger in blob for trigger in triggers):
            found.append((name, markers, anchors))
    return found


def _dimension_hit(question: str, content: str) -> float:
    """按问句里点名的主题核对资料。主题对上了，比硬算字面重合更接近课堂直觉。

    ``question`` 是用户问句，``content`` 是一块资料正文。返回命中主题占全部主题的比例
    （0 到 1）；问句没点名任何主题时返回 0.0，表示"这条口径用不上"，由 ``coverage``
    取最大值时自然忽略它。
    """
    topics = asked_topics(question)
    if not topics:
        return 0.0
    hits = sum(1 for _name, markers, _anchors in topics if any(marker in content for marker in markers))
    return hits / len(topics)


def _context_id(chunk: Mapping[str, Any], index: int) -> str:
    """给一块资料起身份钥匙：``文件名#切块号``；缺切块号就用文件名兜底。

    ``chunk`` 是检索命中或语料里的一条字典，``index`` 是它在本次候选里的下标——
    只有连 ``source`` 都没有的坏数据才用得上它，拼成 ``chunk-{index}`` 至少能让人
    在日志里指着说"是第几条"。返回 id 字符串；索引缺失时给纯文件名，不拼 ``#None``。
    """
    source = str(chunk.get("source") or chunk.get("doc_id") or f"chunk-{index}")
    chunk_index = chunk.get("chunk_index")
    if chunk_index is None:
        return source
    return f"{source}#{chunk_index}"


def _text_of(chunk: Mapping[str, Any]) -> str:
    """取一块资料的正文：认 ``text`` 也认 ``content``，都没有就返回空串。

    ``chunk`` 是语料或检索命中的一条字典。中间隔着这一层，是因为入库脚本写 ``text``、
    评测夹具可能写 ``content``，散落的 ``chunk["text"]`` 会让两种来源之一静默变空。
    """
    return str(chunk.get("text") or chunk.get("content") or "")


def _amounts(text: str) -> set[str]:
    """抽出文中所有金额，统一换算成"元"的字符串集合（``"45万"`` → ``"450000"``）。

    ``text`` 是要扫的正文。换算成同一单位再比，才能让"45 万"和"450000 元"被判成同一个数——
    不换算的话，两篇写着同一件事实的文件会被算成"数字打架"。返回值是字符串集合，
    整数值不带小数点，便于直接进日志和断言。
    """
    found = set()
    for number, wan in _AMOUNT.findall(text or ""):
        value = float(number)
        if wan:
            value *= 10000
        found.add(f"{int(value)}" if value.is_integer() else f"{value}")
    return found


def _days(text: str) -> set[str]:
    """抽出文中所有"X 个工作日"的天数，返回数字字符串集合。

    ``text`` 是要扫的正文。只认带"工作日"的量词，是因为"3 天"在制度文里可能指自然日、
    也可能指审批时长，混进来只会制造假冲突。返回空集表示这段没提工作日，调用方据此
    把覆盖率压到背景区——问题在问"几天"而资料一个天数都没有，答案不可能在里头。
    """
    return set(_DAYS.findall(text or ""))


def _on_topic(question: str, chunk: Mapping[str, Any]) -> bool:
    """这块资料是不是在讲问句点名的主题——用**特征词**判定，不用通用量词。

    没有可识别的主题时一律算相关（宁可多想一层，也别把该比的对漏掉）。

    ``question`` 是用户问句，``chunk`` 是待判的那块资料。返回 True 表示这块资料在讲
    问句点名的主题，可以进冲突比对；问句没点名主题时也返回 True。
    """
    topics = asked_topics(question)
    if not topics:
        return True
    text = _text_of(chunk)
    return any(anchor in text for _name, _markers, anchors in topics for anchor in anchors)


def _values_by_source(chunks: Sequence[Mapping[str, Any]], extract) -> dict[str, set[str]]:
    """按来源汇总数值。同一篇文件里的多个数字是**分档**，不是打架。

    ``chunks`` 是待汇总的资料块序列，``extract`` 是从一段文本里抽数值的函数
    （``_amounts`` 或 ``_days``，两个都能直接当它用）。先按来源归并再返回
    ``{来源: 数值集合}``，正是因为判断冲突的单位是文件而不是块：一线 500、二线 350
    出自同一篇差旅制度，那是分档；只有两篇文件各说各的才算矛盾。
    某一块抽不出数值就不进结果——"没提数字"和"提了别的数字"是两码事。
    """
    grouped: dict[str, set[str]] = {}
    for chunk in chunks:
        source = str(chunk.get("source") or chunk.get("doc_id") or "")
        found = extract(_text_of(chunk))
        if found:
            grouped.setdefault(source, set()).update(found)
    return grouped


def _sources_disagree(grouped: dict[str, set[str]]) -> bool:
    """两份以上来源各自给了数字，且两份之间没有任何共同值——这才叫证据冲突。

    ``grouped`` 是 ``_values_by_source`` 的产物，形如 ``{来源: 数值集合}``。判据是
    "**两两之间**一个共同值都没有"：只要存在一对来源数值完全不交叠就算冲突。
    但凡有一处重合，就说明两份文件讲的是同一件事的不同侧面，不该拉警报。

    少于两份有数字的来源时返回 False——一份文件自己内部写几个数，那是分档不是打架。
    """
    sources = [values for values in grouped.values() if values]
    if len(sources) < 2:
        return False
    for index, left in enumerate(sources):
        for right in sources[index + 1:]:
            if not (left & right):
                return True
    return False


def has_material_conflict(question: str, chunks: Sequence[Mapping[str, Any]]) -> bool:
    """两份**不同来源**的资料对同一个数字各说各话，且问题在问这个数字。

    两道筛子缺一不可：

    1. **主题筛**：问薪酬时，差旅文档里的「500 元」和薪酬文档里的「45 万」
       不是打架，是两回事；
    2. **来源筛**：《员工差旅管理制度》里一线 500、二线 350 是正常分档，
       同一篇文件内的多个数字从来不是证据冲突——只有两份文件互相矛盾才算。

    这两条都是被评测区抓出来的：前者让「P6 薪酬带宽」误判成冲突，后者让
    「住宿费上限」误判成冲突。闸门误杀的代价是"该答的题拒答"，比漏判更伤。

    ``question`` 是用户问句，``chunks`` 是这次通过授权的候选资料块。返回 True 表示
    判为证据冲突，上游应当转人工或向用户澄清；块数少于两块时直接返回 False。
    """
    if len(chunks) < 2:
        return False
    relevant = [chunk for chunk in chunks if _on_topic(question, chunk)]
    if len(relevant) < 2:
        return False
    if any(marker in question for marker in CONFLICT_MARKERS):
        sources = {str(chunk.get("source") or "") for chunk in relevant}
        if len(sources) >= 2:
            return True
    if any(marker in question for marker in MONEY_MARKERS):
        if _sources_disagree(_values_by_source(relevant, _amounts)):
            return True
    if any(marker in question for marker in DATE_MARKERS):
        if _sources_disagree(_values_by_source(relevant, _days)):
            return True
    return False


def is_high_risk(question: str) -> bool:
    """问的是不是高风险话题（``HIGH_RISK_MARKERS``：薪酬、密码、身份证、密级……）。

    ``question`` 是用户问句。返回 True 时结论会额外挂 ``REASON_REVIEW``——高风险话题上
    的"部分证据"不该让模型自由发挥，宁可转人工。判断只看问句、不看资料：
    问得敏感就是敏感，有资料也不改变这一点。
    """
    return any(marker in question for marker in HIGH_RISK_MARKERS)


def needs_clarification(question: str, content: str) -> bool:
    """问的是"哪一版/现不现行"，而资料里看不出是哪一版——这时该追问，不该硬答。

    ``question`` 是用户问句，``content`` 是拼起来的资料正文。只有问题明确在问版本
    （``VERSION_MARKERS`` 命中）**且**资料里既没有"版本"字样、也没有四位年份时才返回
    True：资料里带着版本线索就照答，缺了才追问，避免把每个问题都拦下来先问一句。
    """
    asks_version = any(marker in question for marker in VERSION_MARKERS)
    if not asks_version:
        return False
    has_version = "版本" in content or "V" in content or "v" in content
    has_date = bool(re.search(r"\d{4}", content))
    return not (has_version or has_date)


def _cap_coverage(question: str, content: str, raw: float, policy: EvidencePolicy) -> float:
    """问题在问金额/天数，资料里完全没数字，覆盖率再高也只能算背景。

    ``question`` 是用户问句，``content`` 是资料正文，``raw`` 是 ``coverage`` 算出的原始
    覆盖度，``policy`` 是当前阈值（用来取封顶值）。返回封顶后的覆盖度，不改动 ``raw``。

    问"住一晚最多报多少"时，一段讲住宿标准却没写金额的文字词面重合可能很高——因为
    "住宿"两个字都在。可它答不了这个问题，让模型拿到就会编个数字。金额缺失压到背景线、
    天数缺失压到灰区上沿（稍有回旋余地，因为"日"字还可能是自然日的线索）。
    """
    score = raw
    if any(marker in question for marker in MONEY_MARKERS) and not _amounts(content):
        score = min(score, policy.background_threshold)
    if any(marker in question for marker in DATE_MARKERS) and not _days(content) and "日" not in content:
        score = min(score, policy.gray_zone_upper)
    return score


class EvidenceQualifier:
    """给当前授权切块打资格。不调模型，结果可复现。"""

    def __init__(self, policy: EvidencePolicy | None = None) -> None:
        """``policy`` 是本次要用的阈值组，不传就取 ``EvidencePolicy()`` 的课堂缺省。

        做成可注入而不是直接读模块常量：评测要试不同阈值时只需新建一个 qualifier，
        不用改全局状态，也就不会出现"上一条用例把阈值改了、下一条跟着飘"的串味。
        """
        self.policy = policy or EvidencePolicy()

    def assess(
        self,
        question: str,
        chunks: Sequence[Mapping[str, Any]],
        branch_status: Mapping[str, str] | None = None,
    ) -> EvidenceAssessment:
        """对一次检索结果做完整资格判断，返回 ``EvidenceAssessment``。

        ``question`` 是用户问句。``chunks`` 是**已过授权**的候选块（顺序按相关度，
        只取前 ``policy.candidate_limit`` 条参与判断）——传没裁过权限的进来等于把
        不可见的资料也算进覆盖率，这一步的输入必须已经是 ``authorize_chunks`` 的产物。
        ``branch_status`` 是三路召回的可用性映射（``{"bm25": "ok", "graph": "unavailable"}``），
        不传就当三路都正常。

        判定次序是刻意的：先看有没有块、再看块本身是否有效（缺正文或来源→
        ``invalid_provenance``），然后是版本澄清、材料冲突，最后才落到覆盖率分档。
        冲突必须排在覆盖度前面——两份文件数字打架时覆盖率往往都很高，先算分就会
        顺顺当当答出一个数字，那正是最坏的结果。全程不调模型，同一输入永远同一结论。
        """
        policy = self.policy
        statuses = list((branch_status or {}).values())
        unavailable = sum(status == "unavailable" for status in statuses)
        if not chunks:
            if statuses and unavailable == len(statuses):
                return self._build(
                    STATE_INSUFFICIENT, STATUS_UNAVAILABLE, [REASON_UNAVAILABLE],
                )
            return self._build(
                STATE_INSUFFICIENT, STATUS_INSUFFICIENT, [REASON_ZERO],
            )

        bounded = list(chunks[: policy.candidate_limit])
        valid: list[tuple[str, Mapping[str, Any]]] = []
        for index, chunk in enumerate(bounded):
            text = _text_of(chunk)
            source = str(chunk.get("source") or chunk.get("doc_id") or "")
            if text.strip() and source.strip():
                valid.append((_context_id(chunk, index), chunk))
        evaluated = [item[0] for item in valid]
        if not valid:
            return self._build(
                STATE_INVALID, STATUS_INSUFFICIENT, [REASON_INVALID],
            )

        combined = "\n".join(_text_of(chunk) for _, chunk in valid)
        valid_chunks = [chunk for _, chunk in valid]
        partial_outage = bool(unavailable and unavailable < max(len(statuses), 1))
        extra = [REASON_PARTIAL_OUTAGE] if partial_outage else []

        if needs_clarification(question, combined):
            return self._build(
                STATE_BACKGROUND, STATUS_CLARIFY, [REASON_MISSING, *extra],
                evaluated_ids=evaluated,
            )
        if has_material_conflict(question, valid_chunks):
            reasons = [REASON_CONFLICT, *extra]
            status = STATUS_CONFLICT
            if is_high_risk(question):
                reasons.append(REASON_REVIEW)
                status = STATUS_REVIEW
            return self._build(
                STATE_CONFLICT, status, reasons,
                evaluated_ids=evaluated, supporting_ids=evaluated,
            )

        scored = [
            (_cap_coverage(question, _text_of(chunk), coverage(question, _text_of(chunk)), policy), context_id)
            for context_id, chunk in valid
        ]
        scored.sort(reverse=True)
        best = scored[0][0]
        aggregate = _cap_coverage(question, combined, coverage(question, combined), policy)
        score = max(best, aggregate)
        supporting = [context_id for value, context_id in scored if value >= policy.background_threshold]

        if score >= policy.direct_threshold:
            return self._build(
                STATE_DIRECT, STATUS_ANSWERED, [REASON_DIRECT, *extra],
                evaluated_ids=evaluated,
                supporting_ids=supporting or [scored[0][1]],
                coverage=score,
            )
        if score >= policy.gray_zone_lower:
            reasons = [REASON_PARTIAL, *extra]
            status = STATUS_PARTIAL
            if is_high_risk(question):
                status = STATUS_REVIEW
                reasons.append(REASON_REVIEW)
            return self._build(
                STATE_PARTIAL, status, reasons,
                evaluated_ids=evaluated,
                supporting_ids=supporting or [scored[0][1]],
                coverage=score,
                missing=[MissingSlot(
                    field="unsupported_question_parts",
                    description="当前资料只能支持问题的一部分，需要更直接的记录。",
                )],
            )
        if score >= policy.background_threshold:
            return self._build(
                STATE_BACKGROUND, STATUS_INSUFFICIENT, [REASON_BACKGROUND, *extra],
                evaluated_ids=evaluated, coverage=score,
            )
        return self._build(
            STATE_IRRELEVANT, STATUS_INSUFFICIENT, [REASON_IRRELEVANT, *extra],
            evaluated_ids=evaluated, coverage=score,
        )

    def _build(
        self,
        state: str,
        response_status: str,
        reasons: Iterable[str],
        *,
        evaluated_ids: list[str] | None = None,
        supporting_ids: list[str] | None = None,
        missing: list[MissingSlot] | None = None,
        coverage: float = 0.0,
    ) -> EvidenceAssessment:
        """把散装结论装配成 ``EvidenceAssessment``，顺手补上当前的政策版本戳。

        ``state`` 是资料状态（``STATE_*`` 之一），``response_status`` 是该怎么答
        （``STATUS_*`` 之一），``reasons`` 是判定依据的机器码（可给多个，例如
        冲突之外还叠加了"来源部分不可用"）。其余都是关键字参数、按需给：
        ``evaluated_ids`` 参与判断的资料 id、``supporting_ids`` 够格当证据的那些、
        ``missing`` 缺什么信息、``coverage`` 覆盖度分数。

        单独抽这一层，是为了让每个分支只需交代"结论是什么"，版本戳和列表拷贝统一在这里
        补齐——否则十几处 return 里总有一两处忘了带 ``policy_version``，规则就追溯不回去了。
        """
        return EvidenceAssessment(
            state=state,
            response_status=response_status,
            reason_codes=list(reasons),
            evaluated_ids=list(evaluated_ids or []),
            supporting_ids=list(supporting_ids or []),
            missing=list(missing or []),
            coverage=coverage,
            policy_version=self.policy.policy_version,
            calibration_version=self.policy.calibration_version,
        )


DEFAULT_QUALIFIER = EvidenceQualifier()


def qualify(
    question: str,
    chunks: Sequence[Mapping[str, Any]],
    branch_status: Mapping[str, str] | None = None,
) -> EvidenceAssessment:
    """模块级入口，给 agent / 评测共用同一把尺子。

    ``question`` 是用户问句，``chunks`` 是已过授权的候选块，``branch_status`` 是三路
    召回的可用性映射（不传按全可用处理）。返回 ``EvidenceAssessment``。

    走 ``DEFAULT_QUALIFIER`` 而不是让调用方自己 new 一个：评测和线上问答必须用同一套
    阈值，否则会出现"评测说证据充足、线上却拒答"这种对不上的账。
    """
    return DEFAULT_QUALIFIER.assess(question, chunks, branch_status)


def status_label(status: str) -> str:
    """状态码翻成给用户看的中文：``insufficient_evidence`` → 「证据不足」。

    ``status`` 是 ``STATUS_*`` 之一，另外也认若干老接口用的短码（``ok`` / ``refuse`` /
    ``regen``）——前端和 trace 里两种写法都出现过，翻译表统一收在这里。
    查不到的码原样返回，方便在页面上直接看出"有个状态没登记"，而不是显示成空白。
    """
    labels = {
        STATUS_ANSWERED: "已回答",
        STATUS_PARTIAL: "部分回答",
        STATUS_INSUFFICIENT: "证据不足",
        STATUS_CLARIFY: "需要补充",
        STATUS_CONFLICT: "证据冲突",
        STATUS_REVIEW: "转人工",
        STATUS_UNAVAILABLE: "来源暂不可用",
        "ok": "已回答",
        "refuse": "已拒答",
        "regen": "重试中",
    }
    return labels.get(status, status)


def route_chip(route: str) -> dict[str, str]:
    """三路路由拆成徽章。``bm25+dense+graph`` → 三枚芯片。

    ``route`` 是单条路由名（``"dense"``、``"graph"`` 等），返回
    ``{"id": route, "label": 中文名}`` 的小字典。``id`` 保留英文原样：它是前端的
    CSS class 和埋点键，跟着页面走；``label`` 只负责显示。没登记的路由原样当标签，
    这样新加一路召回时页面不会因为没翻译就少显示一枚芯片。
    """
    mapping = {
        "bm25": "关键词",
        "dense": "向量",
        "vector": "向量",
        "graph": "图谱",
        "hybrid": "融合",
    }
    return {"id": route, "label": mapping.get(route, route)}


def split_routes(routes: str) -> list[dict[str, str]]:
    """把 ``"bm25+dense+graph"`` 这类拼接串拆成徽章列表，交给 ``route_chip`` 翻译。

    ``routes`` 是检索命中的 ``route`` 字段（用 ``+``、逗号或空白分隔都认），空串返回
    空列表。按首次出现去重并保持原序：融合后的路由串往往是 ``"bm25+bm25+dense"``
    这种带重复的样子，不去重页面上会挂出两枚一样的芯片。
    """
    chips = []
    seen = set()
    for part in re.split(r"[+|,\s]+", routes or ""):
        key = part.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        chips.append(route_chip(key))
    return chips
