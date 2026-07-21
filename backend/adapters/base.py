from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import requests

from config import get_settings

settings = get_settings()
TRACKING_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}


@dataclass
class SourceItem:
    title: str
    url: str
    published_at: datetime | None = None
    author: str | None = None
    excerpt: str = ""
    language: str = "unknown"
    raw: dict = field(default_factory=dict)


class BaseAdapter(ABC):
    def __init__(self, source_url: str, config: dict | None = None):
        self.source_url = source_url
        self.config = config or {}
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": settings.crawl_user_agent, "Accept-Language": "en,zh-CN;q=0.8"})
        self.last_http_status: int | None = None

    @abstractmethod
    def fetch_list(self, page: int = 1) -> list[SourceItem]: ...

    def fetch_detail(self, item: SourceItem) -> SourceItem:
        return item

    def normalize(self, item: SourceItem) -> SourceItem:
        item.title = re.sub(r"\s+", " ", item.title).strip()
        item.excerpt = re.sub(r"\s+", " ", item.excerpt).strip()[:6000]
        item.url = canonicalize_url(urljoin(self.source_url, item.url))
        if item.published_at and item.published_at.tzinfo is None:
            item.published_at = item.published_at.replace(tzinfo=timezone.utc)
        return item

    def validate(self, item: SourceItem) -> bool:
        parsed = urlparse(item.url)
        return len(item.title) >= 4 and parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    def get_next_page(self, page: int) -> int | None:
        return page + 1 if self.config.get("max_pages", 1) > page else None

    def health_check(self) -> dict:
        self._assert_robots_allowed(self.config.get("endpoint", self.source_url))
        response = self.session.get(self.config.get("endpoint", self.source_url), timeout=settings.crawl_timeout_seconds)
        self.last_http_status = response.status_code
        return {"ok": response.ok, "http_status": response.status_code, "content_type": response.headers.get("content-type")}

    def _get(self, url: str, **kwargs) -> requests.Response:
        self._assert_robots_allowed(url)
        response = self.session.get(url, timeout=settings.crawl_timeout_seconds, **kwargs)
        self.last_http_status = response.status_code
        response.raise_for_status()
        return response

    def _assert_robots_allowed(self, url: str) -> None:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        response = self.session.get(robots_url, timeout=min(settings.crawl_timeout_seconds, 10))
        if response.status_code == 404:
            return
        response.raise_for_status()
        parser = RobotFileParser(); parser.set_url(robots_url); parser.parse(response.text.splitlines())
        if not parser.can_fetch(settings.crawl_user_agent, url):
            raise PermissionError(f"robots.txt disallows {url}")


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() not in TRACKING_KEYS])
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path.rstrip("/") or "/", "", query, ""))


def content_digest(title: str, excerpt: str) -> str:
    normalized = re.sub(r"\W+", "", f"{title}{excerpt}").lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
