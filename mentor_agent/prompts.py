"""Versioned extraction prompt, rules, and soft taxonomy."""

PROMPT_VERSION = "mentor-extraction-v1.1"
INDUSTRY_TAXONOMY_VERSION = "industry-soft-v1"


SOFT_INDUSTRY_TAXONOMY = (
    "互联网与平台经济",
    "软件与信息技术",
    "人工智能、大数据与云计算",
    "半导体、电子与通信",
    "银行、证券、基金与金融科技",
    "保险",
    "汽车与智能出行",
    "新能源与电力",
    "工业制造、机械与自动化",
    "化工与新材料",
    "医药与生物科技",
    "医疗与健康服务",
    "快速消费品与食品饮料",
    "零售与电子商务",
    "奢侈品、时尚与体育用品",
    "房地产",
    "建筑与工程",
    "家居与建材",
    "物流与供应链",
    "教育与培训",
    "咨询与专业服务",
    "人力资源服务与猎头",
    "法律、财税与审计",
    "媒体、广告与公共关系",
    "文化、娱乐与游戏",
    "酒店、餐饮与旅游",
    "交通运输与航空",
    "能源、矿业与资源",
    "政府、公共事业与社会组织",
    "其他",
)


CONFIDENCE_RULES = {
    "high": "原文明确表达实体及关系，且 evidence 可直接支持。",
    "medium": "实体明确，但关系边界或轻度归一存在一定歧义。",
    "low": "原文支持较弱但仍可定位；纯推测不能使用 low 保留。",
}


MAPPING_STATUS_RULES = {
    "mapped": "已通过安全规则映射到可信规范表达。",
    "unmapped": "未找到安全映射，必须保留原始表达。",
    "ambiguous": "存在多个合理映射或上下文不足，不能静默选一个。",
}


ORGANIZATION_RELATIONSHIP_RULES = {
    "employer": (
        "仅用于原文明确表达历任、曾任、任职、就职、曾在、加入或"
        "担任某组织岗位的雇佣关系。"
    ),
    "client": "用于客户、服务对象；服务过某组织不自动代表任职。",
    "project": "用于参与或交付的具体项目所涉及组织。",
    "partner": "用于合作方、生态伙伴或联合开展活动的组织。",
    "unknown": "组织被提及，但原文没有足够关系证据。",
}


CREDENTIAL_RULES = (
    "证书、资质、认证和奖项都可收录，但必须使用规定类别。",
    "只有持有、获得、通过、获评、荣获等明确表述才能确认归属。",
    "参加培训不等于取得证书。",
    "搭建认证体系不等于导师本人持有该认证。",
    "准认证或认证中必须标记为 candidate 或 in_progress，不能标为 held。",
    "普通讲师、导师、顾问身份不能包装成资格证。",
)


SKILL_EXTRACTION_RULES = (
    "raw_skill 允许自由抽取，不受固定技能词表限制。",
    "normalized_skill 只做轻度同义归一，不扩大能力范围。",
    "不能根据职位名称自动推导技能。",
    "技能必须有明确原文 evidence。",
    "无法安全归一时保留 raw_skill，并标记为 unmapped。",
)


EXTRACTION_EXAMPLES = (
    {
        "text": "曾任星河科技人才发展经理。",
        "expected": {"relationship": "employer"},
        "reason": "曾任和明确岗位共同支持雇佣关系。",
    },
    {
        "text": "为云帆零售提供招聘咨询服务。",
        "expected": {"relationship": "client"},
        "reason": "提供服务只能支持客户关系，不能支持 employer。",
    },
    {
        "text": "参与海岸研究院人才盘点项目。",
        "expected": {"relationship": "project"},
        "reason": "组织出现在明确项目语境中。",
    },
    {
        "text": "与远山公益基金会合作开展职业课程。",
        "expected": {"relationship": "partner"},
        "reason": "合作开展支持合作方关系。",
    },
    {
        "text": "介绍中提及启明协会，未说明具体关系。",
        "expected": {"relationship": "unknown"},
        "reason": "只有组织名称，没有可验证关系。",
    },
    {
        "text": "主导公司面试官认证体系建设。",
        "expected": {"credential": None},
        "reason": "建设认证体系不是本人获得认证。",
    },
    {
        "text": "正在申请 PCC，当前为准认证教练。",
        "expected": {"credential_status": "candidate"},
        "reason": "准认证不能标为 held。",
    },
    {
        "text": "担任招聘经理。",
        "expected": {"skills": []},
        "reason": "不能仅凭职位自动推导招聘、面试等技能。",
    },
    {
        "text": "行业标签为国央企、外企、世界 500 强。",
        "expected": {"industry_tags": []},
        "reason": "这些是组织属性，不是行业。",
    },
)


MENTOR_EXTRACTION_SYSTEM_PROMPT = """
你负责从单条导师资料中抽取结构化信息。严格遵守以下要求：
1. 只输出一个合法 JSON 对象，不要 Markdown，不要 ```json 代码块，不要解释过程。
2. 不编造、不补全原文不存在的信息。每个抽取项必须尽量提供 source_field 和连续原文 quote 作为 evidence。
3. confidence 只能是 high、medium、low。
4. relationship 只能是 employer、client、project、partner、unknown。
5. mapping_status 只能是 mapped、unmapped、ambiguous。
6. employer 仅用于明确任职关系；“服务过”“客户包括”“合作过”不能判为 employer。
7. 行业分类是 soft taxonomy。列表外行业保留 raw，使用 unmapped，不得硬塞到近似类别。
8. 技能允许自由抽取，不使用固定技能词表，也不能仅根据职位推导技能。
9. “搭建认证体系”不代表本人持有证书；“准 PCC”不能标为 held，应标为 candidate。
10. match_type 由程序计算；模型可以省略或设为 null，不得自行声称 evidence 已验证。

soft industry taxonomy：{json_taxonomy}
""".strip().format(
    json_taxonomy="、".join(SOFT_INDUSTRY_TAXONOMY)
)


__all__ = [
    "CONFIDENCE_RULES",
    "CREDENTIAL_RULES",
    "EXTRACTION_EXAMPLES",
    "INDUSTRY_TAXONOMY_VERSION",
    "MAPPING_STATUS_RULES",
    "MENTOR_EXTRACTION_SYSTEM_PROMPT",
    "ORGANIZATION_RELATIONSHIP_RULES",
    "PROMPT_VERSION",
    "SKILL_EXTRACTION_RULES",
    "SOFT_INDUSTRY_TAXONOMY",
]
