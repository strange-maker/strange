"""Evidence-bound rules for sales intelligence classification.

The rules intentionally prefer false negatives over upgrading a meeting into a
contract or a proposed project into an award.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


INTERNAL_EXCLUSIONS = (
    "党建",
    "主题教育",
    "工会",
    "慰问",
    "志愿活动",
    "文体活动",
    "内部培训",
    "安全检查",
)
STALE_EXCLUSIONS = ("竣工十周年", "回顾", "获奖", "表彰", "荣誉")
KA_TERMS = (
    "中国建筑",
    "中建",
    "中海集团",
    "中国海外",
)
COMPETITOR_TERMS = (
    "ABB",
    "西门子",
    "Siemens",
    "伊顿",
    "Eaton",
    "罗格朗",
    "Legrand",
    "维谛",
    "Vertiv",
    "台达",
    "Delta",
    "施耐德",
    "正泰",
    "良信",
    "特变电工",
)
CHAMBER_TERMS = ("商会", "协会", "贸促会", "联盟")

ENTITY_ALIASES = {
    "中建一局": "中国建筑一局（集团）有限公司",
    "中建二局": "中国建筑第二工程局有限公司",
    "中建三局": "中国建筑第三工程局有限公司",
    "中建四局": "中国建筑第四工程局有限公司",
    "中建五局": "中国建筑第五工程局有限公司",
    "中建六局": "中国建筑第六工程局有限公司",
    "中建七局": "中国建筑第七工程局有限公司",
    "中建八局": "中国建筑第八工程局有限公司",
    "中建股份": "中国建筑股份有限公司",
    "中国建筑": "中国建筑股份有限公司",
}
COUNTRIES = {
    "吉尔吉斯斯坦": ("吉尔吉斯斯坦", "中亚"),
    "哈萨克斯坦": ("哈萨克斯坦", "中亚"),
    "乌兹别克斯坦": ("乌兹别克斯坦", "中亚"),
    "沙特阿拉伯": ("沙特阿拉伯", "中东"),
    "沙特": ("沙特阿拉伯", "中东"),
    "阿联酋": ("阿联酋", "中东"),
    "越南": ("越南", "东南亚"),
    "印度尼西亚": ("印度尼西亚", "东南亚"),
    "印尼": ("印度尼西亚", "东南亚"),
    "马来西亚": ("马来西亚", "东南亚"),
    "泰国": ("泰国", "东南亚"),
    "菲律宾": ("菲律宾", "东南亚"),
    "埃及": ("埃及", "北非"),
    "墨西哥": ("墨西哥", "拉美"),
}
INDUSTRY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("数据中心", ("数据中心", "算力中心", "机房")),
    ("新建工厂", ("工厂", "制造基地", "生产基地")),
    ("电力和新能源", ("新能源", "光伏", "风电", "电站")),
    ("输配电", ("输电", "配电", "电网", "变电站")),
    ("储能", ("储能",)),
    ("轨道交通", ("轨道交通", "地铁", "铁路")),
    ("机场", ("机场", "航站楼")),
    ("医院", ("医院", "医疗中心")),
    ("港口", ("港口", "码头")),
    ("工业园区", ("工业园", "产业园", "园区")),
    ("道路", ("道路", "公路", "高速公路")),
    ("交通基础设施", ("交通基础设施", "道路", "公路", "铁路")),
    ("水务和环保", ("水务", "污水", "环保")),
    ("石油化工", ("石油", "化工", "炼化")),
    ("矿业", ("矿山", "矿业")),
    ("商业综合体", ("商业综合体", "综合体")),
]
PRODUCT_RULES = {
    "数据中心": ("中低压配电", "UPS", "数据中心基础设施", "能源管理", "电能质量", "数字化运维"),
    "电力和新能源": ("中低压配电", "开关设备", "变压器", "SCADA", "保护控制", "微电网"),
    "输配电": ("开关设备", "变压器", "SCADA", "电能质量", "保护控制"),
    "储能": ("中低压配电", "能源管理", "微电网", "数字化运维"),
    "交通基础设施": ("中低压配电", "能源管理", "基础设施自动化", "数字化运维"),
    "道路": ("中低压配电", "能源管理", "基础设施自动化", "数字化运维"),
    "轨道交通": ("中低压配电", "SCADA", "能源管理", "保护控制"),
    "机场": ("中低压配电", "能源管理", "楼宇自动化", "UPS"),
    "医院": ("中低压配电", "UPS", "能源管理", "楼宇自动化"),
    "新建工厂": ("中低压配电", "工业自动化", "能源管理", "数字化运维"),
    "工业园区": ("中低压配电", "能源管理", "楼宇自动化", "微电网"),
}
SENIOR_ROLES = ("董事长", "总经理", "党委书记", "副总经理", "助理总裁")
BUSINESS_DEPARTMENTS = (
    "海外事业部",
    "市场部",
    "市政公路设计院",
    "设计院",
    "土木公司",
    "项目公司",
    "国际部",
)


@dataclass(frozen=True)
class SalesIntelligenceResult:
    display_title: str
    ka_group_id: str | None
    ka_entity_id: str | None
    external_parties: list[str]
    event_types: list[str]
    involved_leaders: list[dict[str, str]]
    involved_departments: list[str]
    country: str | None
    region: str | None
    city: str | None
    industry_tags: list[str]
    product_opportunity_tags: list[str]
    project_name: str | None
    project_stage: str | None
    sales_relevance_score: int
    sales_score_evidence: dict[str, object]
    sales_signal: str
    sales_opportunity: str
    recommended_contact: str
    recommended_action: str
    exclusion_reason: str | None
    evidence_excerpt: str
    topic_tags: list[str]
    requires_review: bool


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value and value.strip()))


def _entity(text: str) -> tuple[str | None, str | None]:
    for alias in sorted(ENTITY_ALIASES, key=len, reverse=True):
        if alias in text:
            return alias, ENTITY_ALIASES[alias]
    return None, None


def _country(text: str) -> tuple[str | None, str | None]:
    for alias in sorted(COUNTRIES, key=len, reverse=True):
        if alias in text:
            return COUNTRIES[alias]
    return None, None


def _external_parties(title: str, text: str) -> list[str]:
    parties: list[str] = []
    match = re.search(
        r"^(.{2,45}?)(?:到访|到)(?:中国建筑|中建[一二三四五六七八九十]+局|中建)",
        title,
    )
    if match:
        parties.append(match.group(1).strip("与同赴在 "))
    match = re.search(
        r"(?:中国建筑|中建[一二三四五六七八九十]+局|中建).*?与(.{2,45}?)(?:签署|签约|会谈|交流|推进|开展)",
        title,
    )
    if match:
        parties.append(match.group(1).strip("与同赴在 "))
    for name in COMPETITOR_TERMS:
        if name in text and not any(name in item for item in parties):
            parties.append(name)
    known_parties = (
        "吉尔吉斯斯坦交通和通信部",
        "中国对外承包工程商会",
    )
    parties.extend(name for name in known_parties if name in text)
    return _unique(
        [
            party
            for party in parties
            if "\n" not in party and "中建" not in party and len(party) <= 45
        ]
    )


def _leaders(content: str) -> list[dict[str, str]]:
    leaders: list[dict[str, str]] = []
    seen: set[str] = set()
    for segment in re.split(r"[，。；\n]", content):
        match = re.search(
            r"(?P<title>(?:中国建筑|中建)[^。；\n]{2,70}?"
            r"(?:董事长|总经理|党委书记|副总经理|助理总裁))"
            r"(?P<name>[\u4e00-\u9fff]{2,4})(?:参加|出席|会见|表示|带队|一行)",
            segment,
        )
        if not match:
            continue
        name = match.group("name")
        if name in seen or any(word in name for word in ("公司", "项目", "部门", "领导")):
            continue
        seen.add(name)
        title = match.group("title").strip("，、 ")
        leaders.append(
            {
                "name": name,
                "title": title,
                "role_in_event": (
                    "中建方主要参与领导"
                    if any(role in title for role in ("董事长", "总经理", "党委书记"))
                    else "中建方参与领导"
                ),
            }
        )
    return leaders


def _departments(text: str) -> list[str]:
    entity_prefixes = re.findall(r"中建[一二三四五六七八九十]+局", text)
    values: list[str] = []
    for prefix in _unique(entity_prefixes):
        for department in BUSINESS_DEPARTMENTS:
            name = prefix + department
            if name in text:
                values.append(name)
    return _unique(values)


def _event_types(text: str, foreign_party: bool) -> list[str]:
    values: list[str] = []
    if foreign_party and any(word in text for word in ("到访", "调研", "交流", "会见", "会谈")):
        values.append("政府交流" if any(word in text for word in ("政府", "交通和通信部", "部长", "使节")) else "客户拜访")
    if "高层会见" in text or ("会见" in text and any(role in text for role in SENIOR_ROLES)):
        values.append("高层会见")
    if any(word in text for word in ("签署", "签约", "签订")):
        values.append("签约合作")
    if any(word in text for word in ("战略合作", "战略协议")):
        values.append("战略合作")
    if "EPC" in text.upper() and any(word in text for word in ("签署", "签约", "签订", "合同")):
        values.append("EPC签约")
    if any(word in text for word in ("招标", "招标公告")):
        values.append("项目招标")
    if any(word in text for word in ("中标", "中标通知")):
        values.append("项目中标")
    if any(word in text for word in ("规划", "拟建")):
        values.append("项目规划")
    if any(word in text for word in ("开工", "开建")):
        values.append("项目开工")
    if any(word in text for word in ("项目推进", "后续推进", "推进计划", "拟合作项目")):
        values.append("项目推进")
    if foreign_party and any(word in text for word in ("调研", "考察", "到访", "出访")):
        values.append("海外考察")
    if any(word in text for word in ("成立", "设立")) and any(
        word in text for word in ("公司", "总部", "事业部", "项目公司")
    ):
        values.append("新公司成立")
    if any(word in text for word in ("任命", "辞任", "调任", "退休", "兼任")):
        values.append("领导任免")
    return _unique(values)


def _project_stage(text: str) -> str | None:
    if any(word in text for word in ("拟合作", "后续推进", "调研交流", "前期交流")):
        return "前期交流/拟合作"
    if any(word in text for word in ("招标", "投标")):
        return "招标"
    if "中标" in text:
        return "中标"
    if any(word in text for word in ("签署", "签约", "签订")):
        return "签约"
    if "设计" in text:
        return "设计"
    if "开工" in text:
        return "开工"
    if "规划" in text:
        return "规划"
    return None


def _project_name(text: str) -> str | None:
    for match in re.finditer(r"([^，。；\n]{3,50}(?:项目|工程))", text):
        value = match.group(1).strip()
        if any(generic in value for generic in ("拟合作项目", "基础设施项目", "项目后续", "参与项目")):
            continue
        if len(value) <= 50:
            return value
    return None


def _industries(text: str) -> list[str]:
    return [label for label, terms in INDUSTRY_RULES if any(term in text for term in terms)]


def _products(industries: list[str]) -> list[str]:
    values: list[str] = []
    for industry in industries:
        values.extend(PRODUCT_RULES.get(industry, ()))
    return _unique(values)


def _topic_tags(text: str) -> list[str]:
    tags: list[str] = []
    if any(term in text for term in KA_TERMS):
        tags.append("ka_dynamic")
    if any(term.lower() in text.lower() for term in COMPETITOR_TERMS):
        tags.append("competitor_dynamic")
    if any(term in text for term in CHAMBER_TERMS):
        tags.append("chamber_association")
    return tags


def _display_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip(" -—|")


def analyze_text(
    *,
    title: str,
    content: str,
    source_type: str,
    reliability_level: str,
) -> SalesIntelligenceResult:
    display_title = _display_title(title)
    text = f"{display_title}\n{content}".strip()
    entity_alias, entity_id = _entity(text)
    country, region = _country(text)
    parties = _external_parties(display_title, text)
    leaders = _leaders(content)
    departments = _departments(text)
    industries = _industries(text)
    products = _products(industries)
    foreign_party = bool(country and parties)
    event_types = _event_types(text, foreign_party)
    stage = _project_stage(text)
    project_name = _project_name(text)
    topics = _topic_tags(text)

    exclusion_reason: str | None = None
    internal_terms = [word for word in INTERNAL_EXCLUSIONS if word in text]
    stale_terms = [word for word in STALE_EXCLUSIONS if word in text]
    external_business_evidence = bool(
        parties
        or stage
        or any(word in text for word in ("项目", "合同", "签署", "中标", "招标"))
    )
    if internal_terms and not external_business_evidence:
        exclusion_reason = f"内部非销售资讯：{'、'.join(internal_terms)}"
    elif stale_terms and not any(
        word in text for word in ("新项目", "新签", "签署", "招标", "中标", "开工")
    ):
        exclusion_reason = f"竣工/荣誉回顾：{'、'.join(stale_terms)}"

    has_project = "项目" in text or bool(project_name)
    explicit_contract = any(word in text for word in ("签署", "签约", "签订", "中标"))
    if exclusion_reason:
        project_score = 3 if has_project else 0
    elif has_project:
        if project_name or (explicit_contract and country):
            project_base = 20
        elif country and any(word in text for word in ("基础设施", "建设需求", "拟合作")):
            project_base = 15
        else:
            project_base = 10
        stage_score = 10 if explicit_contract or stage in {"招标", "设计", "开工", "规划"} else (8 if stage else 0)
        project_score = min(30, project_base + stage_score)
    else:
        project_score = 0

    relationship_score = 0
    if parties:
        if foreign_party and any(word in text for word in ("政府", "部", "业主", "投资方", "开发商")):
            relationship_score += 15
        else:
            relationship_score += 10
    if parties and any(word in text for word in ("合作", "项目推进", "后续推进", "推进计划", "签署", "签约")):
        relationship_score += 10
    relationship_score = min(25, relationship_score)

    if exclusion_reason:
        business_score = 0
    elif "数据中心" in industries or len(industries) >= 3:
        business_score = 20
    elif industries:
        business_score = 15
    else:
        business_score = 0

    decision_score = 0
    if leaders:
        decision_score += 10 if any(
            any(role in row["title"] for role in SENIOR_ROLES) for row in leaders
        ) else 5
    if departments:
        decision_score += 5
    decision_score = min(15, decision_score)

    reliability_score = {
        "high": 10,
        "medium": 5,
        "low": 2,
    }.get(reliability_level, 0)
    score = min(
        100,
        project_score
        + relationship_score
        + business_score
        + decision_score
        + reliability_score,
    )
    if exclusion_reason:
        score = min(score, 29)

    evidence = {
        "project_opportunity": {
            "score": project_score,
            "matched": [value for value in (project_name, stage, country) if value],
        },
        "customer_relationship": {"score": relationship_score, "matched": parties},
        "schneider_relevance": {"score": business_score, "matched": industries + products},
        "decision_maker": {
            "score": decision_score,
            "matched": [row["name"] for row in leaders] + departments,
        },
        "source_reliability": {
            "score": reliability_score,
            "matched": [source_type, reliability_level],
        },
    }
    requires_review = source_type == "wechat_manual" or reliability_level == "low"
    evidence_excerpt = re.sub(r"\s+", " ", content).strip()[:500]

    if parties and country:
        fact = f"{parties[0]}与{entity_alias or '中建单位'}就{stage or '相关业务'}开展交流。"
    elif event_types:
        fact = f"{entity_alias or '中建单位'}发生{'、'.join(event_types[:2])}动态。"
    else:
        fact = f"{entity_alias or '中建单位'}发布相关信息。"
    if requires_review:
        fact += " 该信息为公众号线索，建议核验官方来源。"
    opportunity = (
        f"可能形成{'、'.join(products[:4])}机会，建议结合项目阶段进一步核验。"
        if products
        else "暂未识别明确电气产品机会，需结合项目范围进一步核验。"
    )
    contacts = departments or ([entity_id] if entity_id else [])
    recommended_contact = "、".join(contacts) if contacts else "相关中建单位海外或市场业务部门"
    recommended_action = (
        f"建议联系{recommended_contact}，确认项目名称、资金来源、设计阶段和采购节点"
        + (f"，并向{country}施耐德团队同步。" if country else "。")
    )

    return SalesIntelligenceResult(
        display_title=display_title,
        ka_group_id="中国建筑" if entity_alias else None,
        ka_entity_id=entity_id,
        external_parties=parties,
        event_types=event_types,
        involved_leaders=leaders,
        involved_departments=departments,
        country=country,
        region=region,
        city="利雅得" if "利雅得" in text else None,
        industry_tags=industries,
        product_opportunity_tags=products,
        project_name=project_name,
        project_stage=stage,
        sales_relevance_score=score,
        sales_score_evidence=evidence,
        sales_signal=fact[:180],
        sales_opportunity=opportunity[:220],
        recommended_contact=recommended_contact,
        recommended_action=recommended_action[:260],
        exclusion_reason=exclusion_reason,
        evidence_excerpt=evidence_excerpt,
        topic_tags=topics,
        requires_review=requires_review,
    )


def analyze_sales_intelligence(article: Any, source: Any) -> SalesIntelligenceResult:
    return analyze_text(
        title=getattr(article, "original_title", None) or getattr(article, "title", ""),
        content=getattr(article, "content_excerpt", "") or getattr(article, "summary", ""),
        source_type=getattr(source, "source_type", getattr(article, "source_type", "media")),
        reliability_level=getattr(
            source, "reliability_level", getattr(article, "reliability_level", "low")
        ),
    )


def build_event_fingerprint(
    result: SalesIntelligenceResult,
    published_at: datetime | date | str | None,
) -> str:
    if isinstance(published_at, (datetime, date)):
        date_value = published_at.isoformat()[:10]
    else:
        date_value = str(published_at or "")[:10]
    payload = {
        "entity": result.ka_entity_id or result.ka_group_id or "",
        "parties": sorted(result.external_parties),
        "types": sorted(result.event_types),
        "date": date_value,
        "project": result.project_name or "",
        "country": result.country or "",
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
