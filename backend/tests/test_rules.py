from datetime import datetime

from rules import dedupe_hash, detect_ka, detect_overseas, rule_summary


def test_overseas_country_detection():
    result = detect_overseas("中国电建签署沙特 EPC 合同", "项目金额为 2 亿 USD")
    assert result["is_overseas"] is True
    assert result["country"] == "沙特阿拉伯"
    assert result["region"] == "中东"


def test_domestic_without_overseas_signal_is_excluded():
    result = detect_overseas("某市产业园开工", "项目位于江苏省南京市")
    assert result["is_overseas"] is False


def test_ambiguous_ka_keeps_multiple_candidates():
    names, matched, confidence = detect_ka("中国电工签署海外项目", "国际 EPC 工程", "中国电工")
    assert "国机" in names and "中国能建" in names
    assert "中国电工" in matched
    assert confidence < .8


def test_dedupe_hash_is_stable():
    dt = datetime(2026, 7, 17)
    assert dedupe_hash("同一标题", dt, "来源") == dedupe_hash("同一标题", dt, "来源")


def test_rule_summary_never_invents_text():
    source = "第一句事实。第二句事实。第三句事实。"
    summary = rule_summary(source)
    assert summary in source
