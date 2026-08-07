import pytest

from sales_intelligence import analyze_text, build_event_fingerprint


KYRGYZSTAN_SAMPLE = """
吉尔吉斯斯坦交通和通信部代表团到访中建五局。
中建股份助理总裁、中建五局董事长田卫国参加，中建五局副总经理贾先国参加。
吉方介绍交通基础设施建设需求，希望中建五局参与吉尔吉斯斯坦基础设施项目。
双方讨论拟合作项目后续推进计划。
中建五局海外事业部、中建五局市政公路设计院、中建五局土木公司参加。
"""


def test_kyrgyzstan_cscec_visit_is_high_value_without_fact_upgrade():
    result = analyze_text(
        title="吉尔吉斯斯坦交通和通信部到中建五局调研交流",
        content=KYRGYZSTAN_SAMPLE,
        source_type="official",
        reliability_level="high",
    )

    assert result.display_title == "吉尔吉斯斯坦交通和通信部到中建五局调研交流"
    assert result.sales_relevance_score == 88
    assert {"政府交流", "项目推进", "海外考察"} <= set(result.event_types)
    assert result.country == "吉尔吉斯斯坦"
    assert result.region == "中亚"
    assert {"田卫国", "贾先国"} <= {row["name"] for row in result.involved_leaders}
    assert {
        "中建五局海外事业部",
        "中建五局市政公路设计院",
        "中建五局土木公司",
    } <= set(result.involved_departments)
    assert {"交通基础设施", "道路"} <= set(result.industry_tags)
    assert {"中低压配电", "能源管理", "基础设施自动化", "数字化运维"} <= set(
        result.product_opportunity_tags
    )
    assert "签约合作" not in result.event_types
    assert "项目中标" not in result.event_types
    assert "可能" in result.sales_opportunity
    assert "建议" in result.recommended_action
    assert result.evidence_excerpt


@pytest.mark.parametrize("title", ["中建五局开展主题教育", "中建五局举办内部培训"])
def test_internal_news_is_excluded(title):
    result = analyze_text(
        title=title,
        content=title + "，会议圆满结束。",
        source_type="official",
        reliability_level="high",
    )

    assert result.sales_relevance_score < 30
    assert result.exclusion_reason


def test_completion_award_does_not_score_as_new_project():
    result = analyze_text(
        title="某项目竣工十周年获奖回顾",
        content="项目已于十年前竣工，本次获得荣誉。",
        source_type="official",
        reliability_level="high",
    )

    assert result.sales_relevance_score < 50
    assert "项目规划" not in result.event_types
    assert "项目开工" not in result.event_types


def test_explicit_overseas_contract_is_high_value():
    result = analyze_text(
        title="中建八局与沙特某数据中心业主签署EPC合作协议",
        content=(
            "中建八局与沙特某数据中心业主签署EPC合作协议，项目位于利雅得，"
            "目前进入设计和开工准备阶段。中建八局海外事业部负责人参加。"
        ),
        source_type="official",
        reliability_level="high",
    )

    assert result.sales_relevance_score >= 70
    assert {"签约合作", "EPC签约"} <= set(result.event_types)
    assert result.country == "沙特阿拉伯"
    assert "数据中心" in result.industry_tags
    assert "UPS" in result.product_opportunity_tags


def test_wechat_article_routes_to_multiple_topics_without_duplication():
    result = analyze_text(
        title="中建与ABB在商会活动中交流海外数据中心合作",
        content="中国对外承包工程商会活动上，中建与ABB交流海外数据中心项目。",
        source_type="wechat_manual",
        reliability_level="low",
    )

    assert {"ka_dynamic", "competitor_dynamic", "chamber_association"} <= set(
        result.topic_tags
    )
    assert result.requires_review is True
    assert "建议核验官方来源" in result.sales_signal


def test_event_fingerprint_reuses_one_event_across_sources():
    first = analyze_text(
        title="吉尔吉斯斯坦交通和通信部到中建五局调研交流",
        content=KYRGYZSTAN_SAMPLE,
        source_type="official",
        reliability_level="high",
    )
    second = analyze_text(
        title="中建五局与吉尔吉斯斯坦交通和通信部推进基础设施合作",
        content=KYRGYZSTAN_SAMPLE,
        source_type="wechat_manual",
        reliability_level="low",
    )

    assert build_event_fingerprint(first, "2026-08-01") == build_event_fingerprint(
        second, "2026-08-01"
    )

