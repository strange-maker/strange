from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


MAPPINGS_PATH = Path(__file__).with_name("ka_mappings.json")
KA_MAPPINGS: list[dict[str, Any]] = json.loads(MAPPINGS_PATH.read_text(encoding="utf-8"))

WEAK_ALIASES = {
    "中交", "交建", "冶", "水电", "电建", "电力建设", "电力工程",
    "保利", "轻工", "工艺", "中车", "振华", "能建", "西电",
}
STRONG_ALIASES = {
    "中国电气装备", "山东电工电气", "中国电力技术装备", "中工国际",
    "中国建筑", "中国电建", "中国能建", "中国中铁", "中国铁建",
    "中国土木", "中车国际", "中国港湾", "哈尔滨电气",
}
ENGLISH_ALIASES = {
    "powerchina": ("中国电建", "中国电建"),
    "energy china": ("中国能建", "中国能建"),
    "china energy engineering": ("中国能建", "中国能建"),
    "china state construction": ("中国建筑", "中国建筑"),
    "cscec": ("中国建筑", "中国建筑"),
    "crcc": ("中国铁建", "中国铁建"),
    "china railway group": ("中国中铁", "中国中铁"),
    "crrc": ("中车国际", "中车国际"),
    "cccc": ("中交集团", "中交集团"),
    "china harbour": ("中国港湾", "中国港湾"),
}

INTELLIGENCE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("new_factory", ("新建工厂", "扩建工厂", "产能扩建", "投产", "production plant", "new factory", "capacity expansion")),
    ("data_center", ("数据中心", "算力中心", "机房", "data center", "datacenter")),
    ("rail_transit", ("轨道交通", "铁路", "地铁", "轻轨", "railway", "metro", "rail transit")),
    ("power_grid", ("电网", "输电", "配电", "变电站", "substation", "transmission", "power grid")),
    ("renewable_energy", ("光伏", "风电", "新能源", "solar", "wind power", "renewable")),
    ("energy_storage", ("储能", "电池储能", "battery storage", "energy storage")),
    ("industrial_park", ("工业园", "产业园", "industrial park", "economic zone")),
    ("manufacturing", ("制造业", "制造基地", "manufacturing", "production line")),
    ("building_infrastructure", ("医院", "机场", "港口", "建筑", "hospital", "airport", "port", "infrastructure")),
    ("oil_gas_chemical", ("石油", "天然气", "炼化", "化工", "oil", "gas", "petrochemical")),
    ("mining_metals", ("矿业", "矿山", "冶金", "钢铁", "mining", "metals", "smelter")),
    ("tax_policy", ("税收", "税率", "增值税", "企业所得税", "tax", "vat", "corporate income tax")),
    ("investment_policy", ("投资政策", "投资门槛", "投资促进", "investment policy", "investment threshold")),
    ("foreign_access", ("外资准入", "外资持股", "foreign ownership", "foreign investment access")),
    ("localization_policy", ("本地化", "本地采购", "local content", "local procurement")),
    ("trade_tariff", ("关税", "进出口", "出口管制", "tariff", "customs", "export control")),
    ("standards_compliance", ("技术标准", "认证要求", "合规", "certification", "technical standard", "compliance")),
    ("outbound_china_policy", ("境外投资备案", "对外承包", "出口退税", "跨境融资", "外汇政策", "出口信用保险", "一带一路")),
    ("ka_leader", ("调研", "访问", "会见", "讲话", "任免", "履新", "考察", "met with", "appointed", "visited")),
    ("ka_company", ("企业战略", "经营动态", "签约", "中标", "开工", "并购", "融资", "新设机构", "海外办公室")),
    ("competitor", ("siemens", "abb", "eaton", "legrand", "vertiv", "rockwell", "honeywell", "正泰", "良信", "特变电工")),
    ("chamber_association", ("商会", "协会", "贸促会", "chamber", "association")),
]

POLICY_TYPES = {
    "tax_policy", "investment_policy", "foreign_access", "localization_policy",
    "trade_tariff", "standards_compliance", "outbound_china_policy", "international_policy",
}
PROJECT_TYPES = {
    "new_factory", "data_center", "rail_transit", "power_grid", "renewable_energy",
    "energy_storage", "industrial_park", "manufacturing", "building_infrastructure",
    "oil_gas_chemical", "mining_metals",
}
ACTION_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("award", ("中标", "授标", "awarded", "wins contract")),
    ("contract", ("签约", "合同", "contract", "agreement signed")),
    ("construction", ("开工", "动工", "construction begins", "groundbreaking")),
    ("commissioning", ("投产", "并网", "commissioned", "commercial operation")),
    ("investment", ("投资", "investment")),
    ("meeting", ("会见", "调研", "访问", "meeting", "visited")),
    ("appointment", ("任免", "履新", "appointed", "named as")),
]


def classify_intelligence(text: str, source_type: str | None = None) -> list[str]:
    lowered = text.lower()
    result = [kind for kind, words in INTELLIGENCE_RULES if any(word.lower() in lowered for word in words)]
    if source_type == "policy" and not any(x in POLICY_TYPES for x in result):
        result.append("international_policy")
    if source_type == "competitor" and "competitor" not in result:
        result.append("competitor")
    if source_type == "chamber" and "chamber_association" not in result:
        result.append("chamber_association")
    if any(x in PROJECT_TYPES for x in result):
        result.append("market_project")
    return list(dict.fromkeys(result))


def _alias_strength(alias: str) -> str:
    if alias in WEAK_ALIASES:
        return "weak"
    if alias in STRONG_ALIASES or len(alias) >= 6:
        return "strong"
    return "medium"


def match_ka_candidates(title: str, content: str, source_name: str = "", source_url: str = "") -> list[dict[str, Any]]:
    text = f"{title}\n{content}\n{source_name}"
    lowered = text.lower()
    company_context = any(x in text for x in ("集团", "公司", "股份", "工程", "项目", "董事长", "总经理", "党委"))
    overseas_context = any(x in lowered for x in ("海外", "国际", "境外", "epc", "project", "contract"))
    results: list[dict[str, Any]] = []
    for mapping in KA_MAPPINGS:
        evidence = []
        score = 0.0
        for alias in mapping["entities"]:
            if alias not in text:
                continue
            strength = _alias_strength(alias)
            if strength == "weak" and not (company_context and (overseas_context or len(alias) >= 3)):
                continue
            evidence.append({"alias": alias, "strength": strength, "context": "public_article_text"})
            score += {"strong": 0.78, "medium": 0.54, "weak": 0.24}[strength]
        for alias, (group, entity) in ENGLISH_ALIASES.items():
            if group == mapping["ka_group"] and alias in lowered:
                evidence.append({"alias": alias, "strength": "strong", "context": "english_alias"})
                score += 0.78
        if evidence:
            results.append({
                "ka_group": mapping["ka_group"],
                "matched_entity": evidence[0]["alias"],
                "entity_relation": "business_mapping",
                "confidence": round(min(0.98, score), 2),
                "evidence": evidence,
                "needs_review": score < 0.65,
            })
    results.sort(key=lambda x: (-x["confidence"], x["ka_group"]))
    if "中国电工" in text:
        for candidate in results:
            if candidate["ka_group"] in {"国机", "中国能建"}:
                candidate["needs_review"] = True
                candidate["confidence"] = min(candidate["confidence"], 0.68)
    return results


def detect_action_type(text: str) -> str | None:
    lowered = text.lower()
    return next((name for name, words in ACTION_RULES if any(word.lower() in lowered for word in words)), None)


def _money_tokens(text: str) -> list[str]:
    return re.findall(r"(?:usd|eur|rmb|cny|sar|aed|美元|欧元|人民币)?\s*\d+(?:[.,]\d+)?\s*(?:亿|万|million|billion)?", text.lower())[:2]


def _stable_text(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.lower())


def canonical_event_fingerprint(
    title: str,
    published_at: datetime | None,
    country: str | None,
    candidates: list[dict[str, Any]],
    intelligence_types: list[str],
) -> str:
    day_bucket = published_at.strftime("%Y-%m") if published_at else "date-unverified"
    groups = ",".join(sorted({x["ka_group"] for x in candidates if x["confidence"] >= 0.5}))
    project_types = ",".join(sorted(set(intelligence_types) & PROJECT_TYPES))
    action = detect_action_type(title) or "event"
    if action in {"award", "contract"}:
        action = "award_contract"
    money = ",".join(_money_tokens(title))
    if groups and country and project_types:
        basis = f"{groups}|{country}|{project_types}|{action}|{money}|{day_bucket}"
    else:
        basis = f"{_stable_text(title)}|{country or ''}|{action}|{day_bucket}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def canonical_project_fingerprint(country: str | None, candidates: list[dict[str, Any]], intelligence_types: list[str], title: str) -> str:
    groups = ",".join(sorted({x["ka_group"] for x in candidates if x["confidence"] >= 0.5}))
    project_types = ",".join(sorted(set(intelligence_types) & PROJECT_TYPES))
    basis = f"{country or ''}|{groups}|{project_types}|{','.join(_money_tokens(title))}"
    if not groups:
        basis += f"|{_stable_text(title)[:160]}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def policy_dimensions(text: str, country: str | None, intelligence_types: list[str], industries: list[str]) -> dict[str, Any] | None:
    types = [x for x in intelligence_types if x in POLICY_TYPES]
    if not types:
        return None
    percentages = re.findall(r"\d+(?:\.\d+)?%", text)
    return {
        "publishing_country": country,
        "affected_countries": [country] if country else [],
        "issuing_body": None,
        "policy_types": types,
        "applicable_industries": industries,
        "tax_type": next((x for x in ("企业所得税", "增值税", "进口关税", "corporate income tax", "VAT") if x.lower() in text.lower()), None),
        "tax_rate_change": percentages[0] if percentages and "tax_policy" in types else None,
        "foreign_ownership_ratio": percentages[0] if percentages and "foreign_access" in types else None,
        "local_procurement_ratio": percentages[0] if percentages and "localization_policy" in types else None,
        "localization_requirements": "原文存在本地化要求，具体比例待核验。" if "localization_policy" in types else None,
        "import_tariff": percentages[0] if percentages and "trade_tariff" in types else None,
        "china_company_impact": "需结合企业投资路径和项目所在地规则评估。",
        "schneider_sales_impact": "需核验政策生效范围后评估准入、交付和本地化方案。",
        "verification_items": ["生效日期", "适用范围", "官方原文"] if not country else ["生效日期", "适用范围"],
    }


def source_role(source_type: str, source_name: str, language: str) -> str:
    if source_type in {"official", "procurement", "stock_disclosure", "policy"}:
        return "official"
    if source_type == "wechat_manual":
        return "manual"
    if language == "zh" or re.search(r"[\u4e00-\u9fff]", source_name):
        return "china_media"
    return "overseas_media"


def extract_leader_event(text: str, article_data: dict[str, Any]) -> dict[str, Any] | None:
    action = detect_action_type(text)
    if "ka_leader" not in article_data.get("intelligence_types", []) or action not in {"meeting", "appointment"}:
        return None
    person_after_title = re.search(r"(?:董事长|总经理|党委书记|副总经理)([\u4e00-\u9fff]{2,4})(?=访问|会见|调研|讲话|任免|履新|考察|在|赴|$)", text)
    person_before_title = re.search(r"([\u4e00-\u9fff]{2,4})(?:董事长|总经理|党委书记|副总经理)", text)
    person = person_after_title or person_before_title
    title = re.search(r"([\u4e00-\u9fff]{2,20}(?:董事长|总经理|党委书记|副总经理))", text)
    candidates = article_data.get("ka_candidates") or []
    return {
        "person_name": person.group(1) if person else None,
        "person_title": title.group(1) if title else None,
        "organization": candidates[0]["ka_group"] if candidates else None,
        "ka_group": candidates[0]["ka_group"] if candidates else None,
        "matched_entity": candidates[0]["matched_entity"] if candidates else None,
        "action_type": action,
        "meeting_party": None,
        "country": article_data.get("country"),
        "city": None,
        "event_date": article_data.get("published_at"),
        "factual_summary": article_data.get("summary", ""),
        "source_url": article_data["original_url"],
        "source_name": article_data["source_name"],
        "published_at": article_data.get("published_at"),
        "confidence": candidates[0]["confidence"] if candidates else 0.45,
        "evidence_excerpt": text[:600],
    }
