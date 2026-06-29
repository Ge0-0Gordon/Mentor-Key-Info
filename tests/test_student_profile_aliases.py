from mentor_agent.matching.aliases import AliasIndex, DEFAULT_ALIAS_PATH
from mentor_agent.matching.student_profile import extract_student_profile


def test_student_profile_parses_ev_and_consulting_aliases():
    aliases = AliasIndex.from_path(DEFAULT_ALIAS_PATH)

    ev_profile = extract_student_profile(
        "我在职想转行做新能源车企产品经理，目标蔚来理想小鹏，希望导师帮我改简历",
        aliases,
    )
    assert ev_profile.target_companies == ["蔚来汽车", "理想汽车", "小鹏汽车"]
    assert "产品经理" in ev_profile.target_roles
    assert "简历优化" in ev_profile.needed_help
    assert "职场人" in ev_profile.current_stage
    assert "汽车/机械/制造" in ev_profile.target_industries

    consulting_profile = extract_student_profile(
        "我是海归硕士，想做咨询或战略岗，目标 MBB 或互联网战略，需要 case 面试辅导",
        aliases,
    )
    assert consulting_profile.target_companies == ["麦肯锡", "贝恩", "波士顿咨询"]
    assert "咨询" in consulting_profile.target_roles
    assert "战略" in consulting_profile.target_roles
    assert "模拟面试" in consulting_profile.needed_help


def test_student_profile_parses_finance_ai_and_operations_aliases():
    aliases = AliasIndex.from_path(DEFAULT_ALIAS_PATH)

    finance_profile = extract_student_profile(
        "我想找金融行业投行或券商实习，需要简历优化和面试训练",
        aliases,
    )
    assert "金融" in finance_profile.target_industries
    assert "投融资" in finance_profile.target_roles
    assert "证券/基金/期货" in finance_profile.target_roles
    assert "简历优化" in finance_profile.needed_help
    assert "模拟面试" in finance_profile.needed_help

    ai_profile = extract_student_profile(
        "我想找AI大模型相关岗位，希望导师有互联网或人工智能行业背景",
        aliases,
    )
    assert ai_profile.target_roles == ["人工智能"]
    assert ai_profile.target_industries == ["AI/互联网/IT"]

    role_only_profile = extract_student_profile(
        "我想找AI大模型岗位，需要简历优化",
        aliases,
    )
    assert role_only_profile.target_roles == ["人工智能"]
    assert role_only_profile.target_industries == []

    ops_profile = extract_student_profile(
        "我是职场人想跳槽到小红书或B站，方向是内容运营和增长运营",
        aliases,
    )
    assert ops_profile.target_companies == ["哔哩哔哩", "小红书"]
    assert "运营" in ops_profile.target_roles
    assert "职场人" in ops_profile.current_stage
