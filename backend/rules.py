from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime

KA_DICTIONARY = [
    {"ka_name":"中航","keywords":["中航","中国航空"]},
    {"ka_name":"中国电气装备","keywords":["中国电气装备","山东电工电气","西电","许继电气","平高电气","宝光股份","西高院","宏盛华源","保变电气"]},
    {"ka_name":"中电装备","keywords":["国家电网","中电装备","中国电力技术装备"]},
    {"ka_name":"中交集团","keywords":["中交集团","振华","中国路桥","中国水利电力对外","中国水利水电对外","中水电","中国交通"]},
    {"ka_name":"中国港湾","keywords":["中国港湾"]},
    {"ka_name":"哈尔滨电气","keywords":["哈电","哈尔滨电气"]},
    {"ka_name":"国机","keywords":["中国机械工业","重型机械","国机","中工国际","中汽","设备工程","苏美达","中国电工"]},
    {"ka_name":"中机","keywords":["中国机械设备","通用技术","中机"]},
    {"ka_name":"中国建筑","keywords":["中国建筑","中建"]},
    {"ka_name":"中国冶金","keywords":["中冶","宝冶","恩菲","中国冶金"]},
    {"ka_name":"中国电建","keywords":["中国电建","水利水电","山东电力建设"]},
    {"ka_name":"中国能建","keywords":["中国能建","能源建设","葛洲坝","中电工程","中国电工"]},
    {"ka_name":"中国中铁","keywords":["中国海外工程","中铁一局","中铁二局","中铁三局","中铁四局","中铁五局","中铁六局","中铁七局","中铁八局","中铁九局","中铁十局","中海外","中国中铁","中国铁路"]},
    {"ka_name":"中国铁建","keywords":["中铁十一","中铁十二","中铁十三","中铁十四","中铁十五","中铁十六","中铁十七","中铁十八","中铁十九","中铁二十","中铁建设","中国铁建","中国土木"]},
    {"ka_name":"保利科技","keywords":["保利","轻工","工艺"]},
    {"ka_name":"中车国际","keywords":["中车","中车国际"]},
]

COUNTRIES = {
    "沙特阿拉伯": ("中东", ["沙特", "Saudi Arabia", "Riyadh", "NEOM"]), "阿联酋": ("中东", ["阿联酋", "UAE", "Dubai", "Abu Dhabi"]),
    "卡塔尔": ("中东", ["卡塔尔", "Qatar"]), "埃及": ("非洲", ["埃及", "Egypt"]), "越南": ("东南亚", ["越南", "Vietnam"]),
    "印度尼西亚": ("东南亚", ["印尼", "印度尼西亚", "Indonesia"]), "马来西亚": ("东南亚", ["马来西亚", "Malaysia"]),
    "泰国": ("东南亚", ["泰国", "Thailand"]), "菲律宾": ("东南亚", ["菲律宾", "Philippines"]), "墨西哥": ("拉美", ["墨西哥", "Mexico"]),
    "尼日利亚": ("非洲", ["尼日利亚", "Nigeria"]), "肯尼亚": ("非洲", ["肯尼亚", "Kenya"]), "坦桑尼亚": ("非洲", ["坦桑尼亚", "Tanzania"]),
    "乌兹别克斯坦": ("中亚", ["乌兹别克斯坦", "Uzbekistan"]), "土耳其": ("欧洲", ["土耳其", "Turkey", "Türkiye"]),
}
OVERSEAS_SIGNALS = ["海外", "境外", "国际", "出海", "一带一路", "对外承包", "EPC合同", "EPC 合同", "海外签约", "国际工程", "World Bank", "ADB", "AfDB", "EBRD", "USD", "EUR", "AED", "SAR"]
SHORT_AMBIGUOUS = ["中交", "电建", "水电", "能建"]


def detect_ka(title: str, content: str, source_name: str = "") -> tuple[list[str], list[str], float]:
    text = f"{title}\n{content}\n{source_name}"
    names, matched = [], []
    for item in KA_DICTIONARY:
        hits = [k for k in item["keywords"] if k in text]
        if hits:
            names.append(item["ka_name"]); matched.extend(hits)
    # Ambiguous short words count only when another overseas/company signal is nearby.
    for word in SHORT_AMBIGUOUS:
        if word in text and not any(k in text for k in ["集团", "公司", "项目", "工程", "海外", "国际"]):
            matched = [m for m in matched if m != word]
    names = [n for n in names if any(k in matched for k in next(x["keywords"] for x in KA_DICTIONARY if x["ka_name"] == n))]
    confidence = min(0.97, 0.62 + 0.09 * len(set(matched))) if names else 0.35
    if "中国电工" in matched and {"国机", "中国能建"}.issubset(names): confidence = 0.68
    return list(dict.fromkeys(names)), list(dict.fromkeys(matched)), confidence


def detect_overseas(title: str, content: str) -> dict:
    text = f"{title}\n{content}"
    evidence, country, region = [], None, None
    for name, (candidate_region, aliases) in COUNTRIES.items():
        hits = [alias for alias in aliases if alias.lower() in text.lower()]
        if hits:
            country, region = name, candidate_region; evidence.extend(hits); break
    evidence.extend(signal for signal in OVERSEAS_SIGNALS if signal.lower() in text.lower())
    evidence = list(dict.fromkeys(evidence))
    score = min(0.99, (0.48 if country else 0) + 0.14 * min(3, len(evidence)))
    return {"is_overseas": score >= 0.55, "overseas_confidence": round(score, 2), "country": country, "region": region or ("其他" if score >= .55 else None), "city_or_project_location": None, "overseas_evidence": evidence[:8]}


def rule_summary(text: str, limit: int = 180) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[。！？.!?])\s*", clean)
    chosen = "".join(sentences[:3]).strip()
    return (chosen[:limit].rstrip("，,；; ") + "…") if len(chosen) > limit else chosen


def product_opportunities(industry: str | None, text: str) -> list[str]:
    joined = f"{industry or ''} {text}"
    rules = [
        (["数据中心", "云"], ["UPS","中低压配电","能效管理","楼宇管理","微电网"]),
        (["电力", "新能源", "光伏", "储能", "电网"], ["中压","低压","变压器","环网柜","保护控制","SCADA","微电网"]),
        (["工业园", "工厂", "制造"], ["配电","自动化","能效管理","工业软件"]),
        (["轨交", "机场", "医院"], ["配电","楼宇自控","能源管理","UPS"]),
        (["石化", "矿业", "重工业"], ["中低压配电","自动化","过程控制","能效改造"]),
    ]
    for keys, products in rules:
        if any(k in joined for k in keys): return products
    return ["中低压配电", "能源管理"]


def dedupe_hash(title: str, published_at: datetime | None, source_name: str) -> str:
    day = published_at.date().isoformat() if published_at else "unknown"
    normalized = re.sub(r"\W+", "", title).lower()
    return hashlib.sha256(f"{normalized}|{day}|{source_name}".encode()).hexdigest()


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)
