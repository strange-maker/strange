from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.registry import ADAPTER_CONFIGS
from models import Role, Source, utcnow

SOURCES_PATH = Path(__file__).resolve().parents[1] / "public" / "sources.yaml"


def schedule_for(item: dict) -> int | None:
    if item["crawl_method"] == "manual_import": return None
    if item["source_type"] in {"media", "competitor"}: return 30
    if item["source_type"] == "official": return 180
    if item["source_type"] == "procurement": return 240
    if item["source_type"] in {"chamber", "policy"}: return 720
    return 1440


def adapter_status_for(item: dict) -> str:
    if item["crawl_method"] == "manual_import" or item["source_type"] == "wechat_manual": return "manual_only"
    if not item["enabled"]: return "disabled"
    notes=item.get("notes", "").lower()
    if any(word in notes for word in ["订阅制", "付费", "授权"]): return "blocked"
    if item["source_name"] in ADAPTER_CONFIGS: return ADAPTER_CONFIGS[item["source_name"]].get("initial_status","active")
    return "pending_adapter"


def source_tags_for(item: dict) -> list[str]:
    tags=[]
    if item["source_type"] == "competitor": tags.append("competitor")
    if item["source_type"] == "official": tags.append("official_owner")
    if any(name in item["source_name"] for name in ["许继","平高"]):
        tags.extend(["ka_subsidiary","competitor_subject"])
    return sorted(set(tags))


def sync_sources(db: Session) -> int:
    payload=json.loads(SOURCES_PATH.read_text(encoding="utf-8")); count=0
    for item in payload:
        source=db.scalar(select(Source).where(Source.source_name == item["source_name"]))
        definition=ADAPTER_CONFIGS.get(item["source_name"], {})
        values={
            "source_url":item["source_url"], "source_type":item["source_type"], "reliability_level":item["reliability_level"],
            "region_focus":item["region_focus"], "country_focus":item["country_focus"], "industry_focus":item["industry_focus"],
            "source_tags":source_tags_for(item),
            "crawl_method":item["crawl_method"], "adapter_key":item["source_name"] if definition else None,
            "adapter_status":adapter_status_for(item), "adapter_config":{k:v for k,v in definition.items() if k not in {"class","schedule_minutes","initial_status"}},
            "schedule_minutes":definition.get("schedule_minutes", schedule_for(item)),
            "enabled":bool(item["enabled"] and adapter_status_for(item) in {"active","manual_only"}), "notes":item["notes"],
        }
        if source:
            persisted_enabled=source.enabled
            persisted_schedule=source.schedule_minutes
            paused=source.adapter_status == "paused" and source.consecutive_failures >= 5 and values["adapter_status"] == "active"
            for key,value in values.items():
                if key not in {"enabled","schedule_minutes","adapter_status"}: setattr(source,key,value)
            source.enabled=persisted_enabled
            source.schedule_minutes=persisted_schedule or values["schedule_minutes"]
            source.adapter_status="paused" if paused else values["adapter_status"]
            if source.adapter_status == "active" and source.enabled and source.next_run_at is None: source.next_run_at=utcnow()
            if source.adapter_status not in {"active","paused"}: source.next_run_at=None
        else:
            source=Source(source_name=item["source_name"],next_run_at=utcnow() if values["adapter_status"] == "active" else None,**values); db.add(source)
        count += 1
    db.commit(); return count


def ensure_roles(db: Session) -> None:
    descriptions={"admin":"系统管理","analyst":"审核与编辑","sales":"销售使用","viewer":"只读访问"}
    for name,description in descriptions.items():
        if not db.scalar(select(Role).where(Role.name == name)): db.add(Role(name=name,description=description))
    db.commit()


def next_run(source: Source):
    return utcnow() + timedelta(minutes=source.schedule_minutes or 1440)
