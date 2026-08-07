"""Safe parser for article exports created by a local Schinza workflow.

This module deliberately accepts article data only.  Authentication material
captured by Schinza must never be uploaded to the sales-intelligence service.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse


MAX_FILE_BYTES = 5_000_000
SENSITIVE_KEYS = {
    "uin",
    "key",
    "pass_ticket",
    "appmsg_token",
    "wxtoken",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "private_key",
    "privatekey",
}
WECHAT_PUBLIC_HOSTS = {"mp.weixin.qq.com", "weixin.qq.com"}
SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?:^|[\s,;?&])"
    r"(?:uin|pass_ticket|appmsg_token|wxtoken|cookie|credentials?|private_?key)"
    r"\s*[:=]",
    re.IGNORECASE,
)


class SensitiveExportError(ValueError):
    """Raised when an export contains credentials or private-key material."""


@dataclass(frozen=True)
class NormalizedSchinzaArticle:
    title: str
    original_url: str
    published_at: datetime | None
    summary: str
    content_text: str
    author: str
    source_name: str


@dataclass(frozen=True)
class SchinzaPreview:
    items: list[NormalizedSchinzaArticle]
    total_count: int
    missing_body_count: int
    invalid_rows: list[dict[str, object]]
    file_sha256: str


def _normalized_key(value: object) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _reject_sensitive(value: object, path: str = "$") -> None:
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = _normalized_key(raw_key)
            child_text = str(child).lower()
            if (
                key in SENSITIVE_KEYS
                or "private_key" in key
                or "begin_private_key" in child_text.replace(" ", "_")
                or "-----begin private key-----" in child_text
            ):
                raise SensitiveExportError(f"检测到敏感凭证字段：{path}.{raw_key}")
            _reject_sensitive(child, f"{path}.{raw_key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive(child, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        if (
            "-----begin private key-----" in lowered
            or SENSITIVE_TEXT_PATTERN.search(value)
        ):
            raise SensitiveExportError(f"检测到敏感凭证内容：{path}")
        try:
            parsed = urlparse(value)
        except ValueError:
            return
        if parsed.scheme in {"http", "https"}:
            for query_key, _ in parse_qsl(parsed.query, keep_blank_values=True):
                if _normalized_key(query_key) in SENSITIVE_KEYS:
                    raise SensitiveExportError(
                        f"检测到敏感凭证参数：{path}.{query_key}"
                    )


def _parse_json_or_csv(filename: str, content_text: str) -> object:
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        try:
            return list(csv.DictReader(io.StringIO(content_text.lstrip("\ufeff"))))
        except csv.Error as exc:
            raise ValueError(f"CSV 文件无法解析：{exc}") from exc
    if suffix != ".json":
        raise ValueError("仅支持 Schinza 导出的 JSON 或 CSV 文件")
    try:
        return json.loads(content_text.lstrip("\ufeff"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 文件无法解析：第 {exc.lineno} 行") from exc


def _article_rows(raw: object) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [row for row in raw if isinstance(row, dict)]
    if isinstance(raw, dict):
        for key in ("articles", "items", "list", "data"):
            rows = raw.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        if any(key in raw for key in ("title", "url", "link", "content_text")):
            return [raw]
    raise ValueError("导出文件中没有可识别的文章列表")


def _first_text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    candidate = value.strip().replace("Z", "+00:00")
    if candidate.isdigit():
        timestamp = int(candidate)
        if timestamp > 10_000_000_000:
            timestamp //= 1000
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        for pattern in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(candidate, pattern)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_public_wechat_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and (parsed.hostname or "").lower() in WECHAT_PUBLIC_HOSTS


def _normalize_rows(rows: list[dict[str, Any]], content_text: str) -> SchinzaPreview:
    items: list[NormalizedSchinzaArticle] = []
    invalid_rows: list[dict[str, object]] = []
    missing_body_count = 0
    for index, row in enumerate(rows, start=1):
        title = _first_text(row, "title", "name", "article_title", "msg_title")
        url = _first_text(row, "original_url", "url", "link", "content_url")
        if not title:
            invalid_rows.append({"row": index, "reason": "缺少标题"})
            continue
        if not _is_public_wechat_url(url):
            invalid_rows.append({"row": index, "reason": "仅支持微信公众平台公开文章链接"})
            continue
        content = _first_text(row, "content_text", "content", "body", "article_content")
        summary = _first_text(row, "summary", "digest", "description", "excerpt")
        if not content:
            missing_body_count += 1
        items.append(
            NormalizedSchinzaArticle(
                title=title,
                original_url=url,
                published_at=_parse_datetime(
                    _first_text(row, "published_at", "publish_at", "publish_time", "datetime", "date")
                ),
                summary=summary,
                content_text=content,
                author=_first_text(row, "author", "writer", "account_name"),
                source_name=_first_text(row, "source_name", "account_name", "nickname", "publisher"),
            )
        )
    return SchinzaPreview(
        items=items,
        total_count=len(items),
        missing_body_count=missing_body_count,
        invalid_rows=invalid_rows,
        file_sha256=hashlib.sha256(content_text.encode("utf-8")).hexdigest(),
    )


def parse_schinza_export(
    filename: str,
    content_text: str,
    max_records: int = 1000,
) -> SchinzaPreview:
    """Parse and validate a local Schinza article export.

    Credential scanning happens before any article preview is returned.
    """

    if len(content_text.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("批量导入文件不能超过 5 MB")
    raw = _parse_json_or_csv(filename, content_text)
    _reject_sensitive(raw)
    rows = _article_rows(raw)
    if len(rows) > max_records:
        raise ValueError(f"单批最多导入 {max_records} 条")
    return _normalize_rows(rows, content_text)
