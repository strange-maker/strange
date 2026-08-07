from __future__ import annotations

import hashlib
import io
import re
from datetime import timedelta
from difflib import unified_diff
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import yaml
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import (
    Article,
    CSCECEntity,
    CSCECLeadershipEvent,
    CSCECOrgEvent,
    PageDiff,
    PageSnapshot,
    Source,
    utcnow,
)


ENTITIES_PATH = Path(__file__).with_name("data") / "cscec_entities.yaml"
ORGANIZATION_AUTHORITY_URL = "https://www.cscec.com/fzlm_new/zjwzq/"
ENTITY_FIELDS = {
    "entity_id",
    "canonical_name",
    "short_name",
    "aliases",
    "parent_entity_id",
    "entity_level",
    "entity_type",
    "stock_code",
    "official_url",
    "country",
    "region",
    "overseas",
    "verification_status",
    "verification_source",
    "active",
    "notes",
}
ROLE_WORDS = (
    "党委书记",
    "党委副书记",
    "独立董事",
    "职工代表董事",
    "董事会秘书",
    "高级管理人员",
    "董事长",
    "副董事长",
    "总经理",
    "副总经理",
    "总工程师",
    "总会计师",
    "董事",
    "监事",
    "领导班子",
)
APPOINTMENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("resignation", ("辞任", "辞职")),
    ("retirement", ("退休",)),
    ("removal", ("免去", "不再担任")),
    ("transfer", ("调任", "履新")),
    ("concurrent_role", ("兼任", "主持工作")),
    ("board_change", ("当选", "增补董事", "增补监事")),
    ("appointment", ("任命", "聘任", "任免", "增补")),
]
ACTIVITY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("overseas_visit", ("出访", "访问", "赴海外", "赴境外")),
    ("inspection", ("调研", "考察")),
    ("meeting", ("会见", "出席", "参加会议")),
    ("signing", ("签约", "签署")),
    ("strategy_activity", ("战略", "年度工作会议", "经营部署")),
]
COMMON_CHINESE_SURNAMES = frozenset(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻"
    "柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪汤"
    "滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛"
    "禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危"
    "江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯管卢莫房裘缪干解应宗"
    "丁宣贲邓郁单杭洪包诸左石崔吉龚程嵇邢裴陆荣翁荀羊甄曲封芮储靳汲邴糜松"
    "井段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘厉戎祖武符"
    "刘景詹束龙叶幸司韶黎乔苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍郤璩桑桂濮"
    "牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习艾鱼容向古易慎戈廖庾终"
    "暨居衡步都耿满弘匡国文寇广禄阙东欧利蔚越隆师巩厍聂晁勾敖融冷訾辛阚那"
    "简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公"
)
COMPOUND_CHINESE_SURNAMES = (
    "欧阳",
    "司马",
    "上官",
    "诸葛",
    "东方",
    "皇甫",
    "尉迟",
    "公孙",
    "慕容",
    "长孙",
    "宇文",
    "司徒",
    "司空",
    "夏侯",
)
PERSON_NAME_STOPWORDS = (
    "的",
    "股东",
    "如有",
    "任何",
    "内容",
    "不存在",
    "不得",
    "公司",
    "本次",
    "会议",
    "董事",
    "监事",
    "人员",
    "职务",
    "候选",
    "委员",
    "管理",
    "高级",
    "独立",
    "相关",
    "以上",
    "以下",
    "中国",
    "建筑",
    "集团",
    "有限",
)
ORG_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("equity_transfer", ("股权划转", "股权转让")),
    ("parent_changed", ("划入", "划转至", "隶属关系调整")),
    ("department_restructured", ("组织架构调整", "部门调整", "事业部调整", "机构调整")),
    ("overseas_office_opened", ("海外机构成立", "海外办公室成立", "海外分公司成立")),
    ("overseas_office_closed", ("海外机构撤销", "海外办公室关闭", "海外分公司注销")),
    ("established", ("成立", "设立")),
    ("renamed", ("更名", "名称变更")),
    ("merged", ("合并", "重组")),
    ("split", ("分立", "拆分")),
    ("dissolved", ("注销", "撤销", "解散")),
]
SALES_RELEVANT_KEYWORDS = (
    "签约",
    "签署",
    "签订",
    "合作",
    "会见",
    "拜会",
    "座谈",
    "交流",
    "调研",
    "考察",
    "访问",
    "出访",
    "中标",
    "联合体",
    "开工",
    "竣工",
    "封顶",
    "投运",
    "承建",
    "项目",
    "合同",
    "战略协议",
    "战略合作",
)
PURE_GOVERNANCE_DOC_KEYWORDS = (
    "股东会会议资料",
    "股东大会会议资料",
    "临时股东会",
    "临时股东大会",
    "会议通知",
    "会议议程",
    "董事会会议决议",
    "监事会会议决议",
    "薪酬方案",
    "表决结果",
    "关联交易管理制度",
)
PROJECT_INTELLIGENCE_TYPES = {
    "market_project",
    "new_factory",
    "data_center",
    "rail_transit",
    "power_grid",
    "renewable_energy",
    "energy_storage",
    "industrial_park",
    "building_infrastructure",
}
ORG_CHANGE_LABELS = {
    "equity_transfer": "股权变动",
    "parent_changed": "隶属调整",
    "department_restructured": "组织调整",
    "overseas_office_opened": "海外机构设立",
    "overseas_office_closed": "海外机构关闭",
    "established": "设立",
    "renamed": "更名",
    "merged": "合并",
    "split": "拆分",
    "dissolved": "注销",
}


def clean_entity_name(value: str) -> str:
    value = value.replace("&nsp;", " ").replace("&nbsp;", " ").replace("\u00a0", " ")
    return re.sub(r"\s+", " ", value).strip(" \t\r\n。、，；")


def is_plausible_person_name(value: str | None) -> bool:
    """Return whether an extracted token is a plausible Chinese personal name.

    The leadership parser previously treated the ``任`` in words such as
    ``任何`` as an appointment verb and captured the preceding prose
    (for example ``股东如有``) as a person's name.  Keep this validator
    deliberately conservative because uncertain tokens must not be promoted
    to verified leadership facts.
    """

    if value is None:
        return False
    name = re.sub(r"\s+", "", value).strip("·")
    if not re.fullmatch(r"[\u4e00-\u9fff]{2,4}(?:·[\u4e00-\u9fff]{1,4})?", name):
        return False
    if any(word in name for word in PERSON_NAME_STOPWORDS):
        return False
    first_part = name.split("·", 1)[0]
    return first_part.startswith(COMPOUND_CHINESE_SURNAMES) or first_part[0] in COMMON_CHINESE_SURNAMES


def _name_key(value: str) -> str:
    return re.sub(r"[\s，（）()·•—/_-]+", "", clean_entity_name(value).lower())


def load_cscec_entities() -> list[dict[str, Any]]:
    payload = yaml.safe_load(ENTITIES_PATH.read_text(encoding="utf-8")) or {}
    rows = payload.get("entities", [])
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rows:
        missing = ENTITY_FIELDS - raw.keys()
        if missing:
            raise ValueError(f"{raw.get('entity_id', 'unknown')} missing fields: {sorted(missing)}")
        row = {key: raw.get(key) for key in ENTITY_FIELDS}
        row["canonical_name"] = clean_entity_name(row["canonical_name"])
        row["short_name"] = clean_entity_name(row["short_name"] or "") or None
        row["aliases"] = [clean_entity_name(value) for value in row.get("aliases", []) if clean_entity_name(value)]
        if row["entity_id"] in seen:
            raise ValueError(f"duplicate CSCEC entity_id: {row['entity_id']}")
        seen.add(row["entity_id"])
        normalized.append(row)
    return normalized


def sync_cscec_entities(db: Session) -> int:
    rows = load_cscec_entities()
    existing = db.scalars(select(CSCECEntity)).all()
    by_id = {entity.entity_id: entity for entity in existing}
    by_name = {_name_key(entity.canonical_name): entity for entity in existing}
    for row in rows:
        entity = by_id.get(row["entity_id"]) or by_name.get(_name_key(row["canonical_name"]))
        if entity is None:
            entity = CSCECEntity(**row)
            db.add(entity)
        else:
            for key, value in row.items():
                setattr(entity, key, value)
        by_id[entity.entity_id] = entity
        by_name[_name_key(entity.canonical_name)] = entity
    db.commit()
    return len(rows)


def normalize_cscec_entity_name(
    value: str,
    entities: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Normalize only an exact canonical name or declared alias.

    Fuzzy matching is deliberately excluded so 中建港航局、中建筑港 and
    中建港务 remain three independent entities.
    """
    key = _name_key(value)
    if not key:
        return None
    matches: list[dict[str, Any]] = []
    for row in entities or load_cscec_entities():
        candidates = [row["canonical_name"], row.get("short_name") or "", *(row.get("aliases") or [])]
        if any(_name_key(candidate) == key for candidate in candidates if candidate):
            matches.append(row)
    return matches[0] if len(matches) == 1 else None


def parse_cscec_organization(
    html: str,
    base_url: str = ORGANIZATION_AUTHORITY_URL,
) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, str | None]] = []
    seen: set[tuple[str, str | None]] = set()
    name_markers = ("中国建筑", "中建", "中海", "设计研究院", "工程局")
    for anchor in soup.select("a"):
        name = clean_entity_name(anchor.get_text(" ", strip=True))
        if len(name) < 4 or not any(marker in name for marker in name_markers):
            continue
        href = (anchor.get("href") or "").strip()
        official_url = (
            urljoin(base_url, href)
            if href and not href.lower().startswith(("javascript:", "#"))
            else None
        )
        key = (name, official_url)
        if key not in seen:
            rows.append({"canonical_name": name, "official_url": official_url})
            seen.add(key)
    return rows


def clean_snapshot_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select("script,style,noscript,iframe,.visit-count,.view-count,.share,.tools"):
        node.decompose()
    lines: list[str] = []
    for raw in soup.get_text("\n", strip=True).splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        if re.fullmatch(r"(?:访问量|浏览量|点击量)[:：]?\s*\d+", line):
            continue
        if re.fullmatch(r"\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?", line):
            continue
        lines.append(line)
    return "\n".join(lines)


def _detected_changes(before: str, after: str) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    for value in sorted(set(after.splitlines()) - set(before.splitlines())):
        if any(role in value for role in ROLE_WORDS):
            changes.append({"kind": "leadership_or_title", "value": value[:500]})
        elif any(word in value for word in ("有限公司", "集团", "研究院", "工程局", "事业部")):
            changes.append({"kind": "organization_or_relation", "value": value[:500]})
    return changes[:100]


def capture_page_snapshot(
    db: Session,
    page_url: str,
    raw_html: str,
    page_type: str,
    entity_id: str | None = None,
    source_id: str | None = None,
) -> tuple[PageSnapshot, PageDiff | None]:
    cleaned = clean_snapshot_html(raw_html)
    digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
    previous = db.scalar(
        select(PageSnapshot)
        .where(PageSnapshot.page_url == page_url)
        .order_by(PageSnapshot.captured_at.desc())
        .limit(1)
    )
    if previous and previous.content_sha256 == digest:
        return previous, None
    snapshot = PageSnapshot(
        entity_id=entity_id,
        source_id=source_id,
        page_type=page_type,
        page_url=page_url,
        raw_html=raw_html,
        cleaned_text=cleaned,
        content_sha256=digest,
        retain_until=utcnow() + timedelta(days=366),
    )
    db.add(snapshot)
    db.flush()
    page_diff = None
    if previous:
        diff_text = "\n".join(
            unified_diff(
                previous.cleaned_text.splitlines(),
                cleaned.splitlines(),
                fromfile="before",
                tofile="after",
                lineterm="",
            )
        )
        page_diff = PageDiff(
            entity_id=entity_id,
            page_type=page_type,
            page_url=page_url,
            before_snapshot_id=previous.id,
            after_snapshot_id=snapshot.id,
            before_text=previous.cleaned_text,
            after_text=cleaned,
            diff_text=diff_text,
            detected_changes=_detected_changes(previous.cleaned_text, cleaned),
            confidence=0.7 if diff_text else 0.2,
            verification_status="pending_review",
        )
        db.add(page_diff)
        db.flush()
    return snapshot, page_diff


def classify_leadership_event(text: str) -> dict[str, Any] | None:
    compact = re.sub(r"\s+", " ", text)
    if not any(role in compact for role in ROLE_WORDS):
        return None
    appointment_type = next(
        (kind for kind, words in APPOINTMENT_RULES if any(word in compact for word in words)),
        None,
    )
    if appointment_type is None:
        appointment_type = next(
            (kind for kind, words in ACTIVITY_RULES if any(word in compact for word in words)),
            None,
        )
    if appointment_type is None:
        return None
    person_patterns = (
        r"(?:独立董事|职工代表董事|董事|监事|高级管理人员|副总经理|总经理)"
        r"\s*([\u4e00-\u9fff·]{2,4})(?:先生|女士|同志)?"
        r"(?:提交.{0,30}?(?:辞职报告|辞任申请)|申请辞去|辞任|辞去|离任)",
        r"([\u4e00-\u9fff·]{2,4})(?:先生|女士|同志)?"
        r"(?:提交.{0,30}?(?:辞职报告|辞任申请)|申请辞去|辞任|辞去|离任)",
        r"(?:任命|聘任|免去|调任|当选|增补)\s*([\u4e00-\u9fff]{2,4})(?:为|任|担任)",
        r"([\u4e00-\u9fff]{2,4})(?:先生|女士|同志)?(?:现任|曾任|出任|就任|担任|辞任|辞去|不再担任)",
        r"(?:董事长|总经理|党委书记|党委副书记|副总经理|总工程师|总会计师)"
        r"([\u4e00-\u9fff]{2,4})(?:先生|女士|同志)?(?=主持|调研|考察|会见|出席|参加|访问|赴|签约|签署|$)",
        r"([\u4e00-\u9fff]{2,4})(?:董事长|总经理|党委书记|党委副书记|副总经理|总工程师|总会计师)",
    )
    person_name = next(
        (
            match.group(1)
            for pattern in person_patterns
            if (match := re.search(pattern, compact))
            and is_plausible_person_name(match.group(1))
        ),
        None,
    )
    if person_name is None:
        return None
    role_pattern = "|".join(sorted(ROLE_WORDS, key=len, reverse=True))
    title = None
    if person_name:
        escaped_name = re.escape(person_name)
        nearby_role = re.search(
            rf"({role_pattern}).{{0,12}}{escaped_name}|{escaped_name}.{{0,12}}({role_pattern})",
            compact,
        )
        if nearby_role:
            title = nearby_role.group(1) or nearby_role.group(2)
    if title is None:
        title_match = re.search(role_pattern, compact)
        title = title_match.group(0) if title_match else None
    role_change = appointment_type in {kind for kind, _ in APPOINTMENT_RULES}
    return {
        "person_name": person_name,
        "appointment_type": appointment_type,
        "title_before": title if appointment_type in {"resignation", "retirement", "removal", "transfer"} else None,
        "title_after": title if role_change and appointment_type not in {"resignation", "retirement", "removal"} else None,
        "confidence": 0.86 if role_change and person_name else (0.72 if person_name else 0.5),
        "role_change": role_change,
        "evidence_excerpt": compact[:1200],
    }


def classify_org_change(text: str) -> str | None:
    compact = re.sub(r"\s+", " ", text)
    return next((kind for kind, words in ORG_RULES if any(word in compact for word in words)), None)


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def extract_cscec_counterparty(text: str) -> str | None:
    compact = _compact_text(text)
    patterns = (
        r"会见([^，。；、]{2,50}?)(?:负责人|董事长|总经理|代表|一行)",
        r"与([^，。；、]{2,50}?)(?:签署|签订|签约|举行|开展|深化|达成|会谈|座谈|交流|合作)",
        r"同([^，。；、]{2,50}?)(?:签署|签订|举行|开展|深化|达成|会谈|座谈|交流|合作)",
    )
    for pattern in patterns:
        match = re.search(pattern, compact)
        if not match:
            continue
        value = clean_entity_name(match.group(1))
        value = re.sub(r"^(?:中国建筑|中建\w*|公司|集团|党委书记|董事长|总经理)+", "", value)
        value = re.sub(r"(?:就|围绕|关于).*$", "", value).strip()
        if 2 <= len(value) <= 40:
            return value
    return None


def cscec_article_sales_metadata(article: Article) -> dict[str, Any]:
    title = article.original_title or article.title
    text = _compact_text(f"{title} {article.summary or ''} {article.content_excerpt or ''}")
    has_sales_keyword = any(word in text for word in SALES_RELEVANT_KEYWORDS)
    has_project_type = bool(set(article.intelligence_types or []) & PROJECT_INTELLIGENCE_TYPES)
    pure_governance_doc = any(word in title for word in PURE_GOVERNANCE_DOC_KEYWORDS) and not has_sales_keyword
    country = article.country or ("中国" if not article.is_overseas else None)
    region = article.region or ("中国" if country == "中国" else None)
    overseas_rank = 0 if article.is_overseas or (country and country != "中国") or (region and region != "中国") else 1
    return {
        "is_sales_relevant": (has_sales_keyword or has_project_type) and not pure_governance_doc,
        "country": country,
        "region": region,
        "counterparty": extract_cscec_counterparty(text),
        "overseas_rank": overseas_rank,
    }


def cscec_org_display_title(row: CSCECOrgEvent) -> str:
    if row.display_title and row.display_title.strip():
        return row.display_title.strip()
    label = ORG_CHANGE_LABELS.get(row.change_type, row.change_type)
    evidence = _compact_text(row.evidence_excerpt or "")
    if row.entity_before and row.entity_after and row.entity_before != row.entity_after:
        return f"{label}：{row.entity_before} → {row.entity_after}"
    established = re.search(r"在([^，。；、]{2,20})设立([^，。；、]{4,60})", evidence)
    if established:
        return f"{label}：{clean_entity_name(established.group(1) + established.group(2))}"
    subject = re.search(r"(?:设立|成立|组建|合并|重组|更名为|注销|撤销)([^，。；、]{4,60})", evidence)
    if subject:
        return f"{label}：{clean_entity_name(subject.group(1))}"
    fallback = clean_entity_name((row.entity_after or row.entity_before or evidence[:32]).strip())
    return f"{label}：{fallback or '组织变化待核验'}"


def _event_key(*parts: Any) -> str:
    value = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def record_cscec_article_events(db: Session, article: Article, source: Source) -> None:
    if "cscec" not in (source.source_tags or []) and "ka_dynamic" not in (
        article.topic_tags or []
    ):
        return
    from sales_intelligence import analyze_text

    text = f"{article.original_title or article.title}\n{article.content_excerpt or ''}"
    analysis = analyze_text(
        title=article.original_title or article.title,
        content=article.content_excerpt or article.summary or "",
        source_type=article.source_type,
        reliability_level=article.reliability_level,
    )
    entity = db.get(CSCECEntity, source.entity_id) if source.entity_id else None
    entity_id = entity.entity_id if entity else source.entity_id
    parent_entity_id = entity.parent_entity_id if entity else None
    leadership = classify_leadership_event(text)
    if leadership and leadership.get("role_change"):
        key = _event_key(
            entity_id,
            leadership["person_name"],
            leadership["appointment_type"],
            article.published_at.date() if article.published_at else "date-unverified",
            article.canonical_event_id or article.id,
        )
        if not db.scalar(select(CSCECLeadershipEvent).where(CSCECLeadershipEvent.event_key == key)):
            db.add(
                CSCECLeadershipEvent(
                    event_key=key,
                    article_id=article.id,
                    person_name=leadership["person_name"],
                    entity_id=entity_id,
                    parent_entity_id=parent_entity_id,
                    title_before=leadership["title_before"],
                    title_after=leadership["title_after"],
                    appointment_type=leadership["appointment_type"],
                    event_category="personnel_change",
                    activity_type="",
                    external_party="",
                    country=analysis.country or "",
                    project_or_business=analysis.project_name or "",
                    sales_impact="领导职责或决策链发生变化，建议更新KA联系人关系。",
                    recommended_action="核验任免公告和最新分工，更新对应中建单位的决策人关系图。",
                    effective_date=article.published_at,
                    published_at=article.published_at,
                    source_url=article.original_url,
                    source_name=article.source_name,
                    evidence_excerpt=leadership["evidence_excerpt"],
                    confidence=leadership["confidence"],
                    verification_status="source_verified" if article.is_primary_source else "pending_review",
                )
            )
            db.flush()

    business_activity = next(
        (
            value
            for event_type, value in (
                ("签约合作", "signing"),
                ("EPC签约", "signing"),
                ("政府交流", "government_exchange"),
                ("客户拜访", "client_meeting"),
                ("高层会见", "executive_meeting"),
                ("海外考察", "overseas_visit"),
                ("项目推进", "project_advancement"),
            )
            if event_type in analysis.event_types
        ),
        None,
    )
    if business_activity and analysis.sales_relevance_score >= 30:
        for leader in analysis.involved_leaders:
            key = _event_key(
                entity_id,
                leader["name"],
                "business_activity",
                business_activity,
                article.published_at.date() if article.published_at else "date-unverified",
                article.canonical_event_id or article.id,
            )
            existing = db.scalar(
                select(CSCECLeadershipEvent).where(
                    CSCECLeadershipEvent.event_key == key
                )
            )
            if existing:
                continue
            db.add(
                CSCECLeadershipEvent(
                    event_key=key,
                    article_id=article.id,
                    person_name=leader["name"],
                    entity_id=entity_id,
                    parent_entity_id=parent_entity_id,
                    title_before=None,
                    title_after=None,
                    appointment_type=(
                        "signing"
                        if business_activity == "signing"
                        else (
                            "overseas_visit"
                            if business_activity == "overseas_visit"
                            else "meeting"
                        )
                    ),
                    event_category="business_activity",
                    activity_type=business_activity,
                    external_party=(analysis.external_parties or [""])[0],
                    country=analysis.country or "",
                    project_or_business=analysis.project_name
                    or "、".join(analysis.industry_tags),
                    sales_impact=analysis.sales_signal,
                    recommended_action=analysis.recommended_action,
                    effective_date=article.published_at,
                    published_at=article.published_at,
                    source_url=article.original_url,
                    source_name=article.source_name,
                    evidence_excerpt=analysis.evidence_excerpt,
                    confidence=article.confidence_score,
                    verification_status=(
                        "source_verified"
                        if article.is_primary_source
                        else "pending_review"
                    ),
                )
            )
            db.flush()

    change_type = classify_org_change(text)
    if change_type is None:
        clean_org_rules = (
            ("overseas_office_opened", ("成立海外区域总部", "成立区域总部", "设立国别公司")),
            ("department_restructured", ("海外事业部调整", "事业部调整", "组织架构调整")),
            ("renamed", ("更名", "名称变更")),
            ("merged", ("合并", "重组")),
            ("dissolved", ("注销", "撤销")),
            ("established", ("成立", "设立", "组建")),
        )
        change_type = next(
            (
                kind
                for kind, words in clean_org_rules
                if any(word in text for word in words)
                and any(
                    subject in text
                    for subject in (
                        "总部",
                        "公司",
                        "事业部",
                        "设计院",
                        "投资平台",
                        "专业公司",
                    )
                )
            ),
            None,
        )
    if change_type:
        key = _event_key(
            entity_id,
            change_type,
            article.published_at.date() if article.published_at else "date-unverified",
            article.canonical_event_id or article.id,
        )
        if not db.scalar(select(CSCECOrgEvent).where(CSCECOrgEvent.event_key == key)):
            new_entity = None
            if change_type in {"established", "overseas_office_opened"}:
                match = re.search(
                    r"((?:中国建筑|中建)[^，。；\n]{0,40}?"
                    r"(?:区域总部|国别公司|项目公司|事业部|设计院|投资平台|专业公司))",
                    text,
                )
                new_entity = clean_entity_name(match.group(1)) if match else None
            display_title = article.display_title or article.original_title or article.title
            db.add(
                CSCECOrgEvent(
                    event_key=key,
                    article_id=article.id,
                    change_type=change_type,
                    entity_before=(
                        None
                        if change_type in {"established", "overseas_office_opened"}
                        else (entity.canonical_name if entity else None)
                    ),
                    entity_after=new_entity or (entity.canonical_name if entity else None),
                    parent_before=parent_entity_id,
                    parent_after=parent_entity_id,
                    display_title=display_title,
                    region_or_industry="、".join(
                        [value for value in (analysis.region, *analysis.industry_tags) if value]
                    ),
                    sales_impact=(
                        "可能改变海外市场覆盖、客户归属或项目决策链，建议更新KA覆盖关系。"
                    ),
                    recommended_contact=analysis.recommended_contact,
                    manual_confirmed=False,
                    effective_date=article.published_at,
                    published_at=article.published_at,
                    source_urls=[article.original_url],
                    source_count=1,
                    evidence_excerpt=text[:1200],
                    confidence=0.8 if article.is_primary_source else 0.55,
                    verification_status="source_verified" if article.is_primary_source else "pending_review",
                )
            )
            db.flush()


def reconcile_discovered_entities(
    db: Session,
    discovered: list[dict[str, str | None]],
) -> dict[str, int]:
    stats = {"matched": 0, "new_pending": 0, "url_changes": 0, "missing_from_page": 0}
    master = load_cscec_entities()
    discovered_ids: set[str] = set()
    for item in discovered:
        matched = normalize_cscec_entity_name(item["canonical_name"] or "", master)
        if matched:
            discovered_ids.add(matched["entity_id"])
            stats["matched"] += 1
            entity = db.get(CSCECEntity, matched["entity_id"])
            new_url = item.get("official_url")
            if entity and new_url and entity.official_url != new_url:
                entity.notes = f"{entity.notes}\n组织架构页发现候选新链接：{new_url}".strip()
                entity.verification_status = "pending_verification"
                stats["url_changes"] += 1
            continue
        name = clean_entity_name(item["canonical_name"] or "")
        if not name:
            continue
        generated_id = "discovered-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
        if not db.get(CSCECEntity, generated_id):
            db.add(
                CSCECEntity(
                    entity_id=generated_id,
                    canonical_name=name,
                    short_name=None,
                    aliases=[],
                    parent_entity_id="cscec-listed",
                    entity_level="discovered",
                    entity_type="unknown",
                    stock_code=None,
                    official_url=item.get("official_url"),
                    country="中国",
                    region="中国",
                    overseas=False,
                    verification_status="pending_verification",
                    verification_source=ORGANIZATION_AUTHORITY_URL,
                    active=False,
                    notes="由组织架构页面自动发现，需人工核验后启用。",
                )
            )
            stats["new_pending"] += 1
    stats["missing_from_page"] = sum(
        row["verification_status"] in {"verified", "renamed"} and row["entity_id"] not in discovered_ids
        for row in master
    )
    db.commit()
    return stats


def is_safe_official_link(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def extract_pdf_text(content: bytes, max_pages: int = 100) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            return ""
    pages = reader.pages[:max_pages]
    text = "\n".join((page.extract_text() or "").strip() for page in pages).strip()
    return re.sub(r"[ \t]+", " ", text)
