from __future__ import annotations

from datetime import datetime, timezone
import re

from bs4 import BeautifulSoup

from adapters.base import BaseAdapter, SourceItem
from cscec import parse_cscec_organization


class CSCECNewsAdapter(BaseAdapter):
    """Public CSCEC site-group list adapter with resumable numbered archives."""

    def _page_url(self, page: int) -> str:
        if page <= 1:
            return self.config.get("endpoint", self.source_url)
        pattern = self.config.get("page_pattern")
        if not pattern:
            return self.config.get("endpoint", self.source_url)
        return pattern.format(page=page, index=page - 1)

    def fetch_list(self, page: int = 1) -> list[SourceItem]:
        if page > int(self.config.get("max_pages", 1)):
            return []
        response = self._get(self._page_url(page))
        soup = BeautifulSoup(response.text, "html.parser")
        selectors = self.config.get("item_selector", ".list li, .news-list li, .zqydt li, ul li")
        rows: list[SourceItem] = []
        for node in soup.select(selectors):
            anchor = node.select_one("a[href]")
            if not anchor:
                continue
            title = anchor.get("title") or anchor.get_text(" ", strip=True)
            date_node = node.select_one("time, .date, .time, span")
            published = _parse_cscec_date(date_node.get_text(" ", strip=True) if date_node else None)
            excerpt_node = node.select_one("p, .summary, .intro")
            rows.append(self.normalize(SourceItem(
                title=title,
                url=anchor.get("href", ""),
                published_at=published,
                excerpt=excerpt_node.get_text(" ", strip=True) if excerpt_node else "",
                language="zh",
            )))
        unique: dict[str, SourceItem] = {}
        for item in rows:
            if self.validate(item):
                unique[item.url] = item
        return list(unique.values())[: int(self.config.get("limit", 50))]

    def fetch_detail(self, item: SourceItem) -> SourceItem:
        response = self._get(item.url)
        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.select_one("h1, .article-title, .title")
        if title:
            item.title = title.get_text(" ", strip=True)
        date_node = soup.select_one("time, .article-date, .date, .time")
        if not item.published_at and date_node:
            item.published_at = _parse_cscec_date(date_node.get("datetime") or date_node.get_text(" ", strip=True))
        content = soup.select_one(self.config.get("content_selector", ".TRS_Editor, .article-content, article, main"))
        if content:
            item.excerpt = content.get_text(" ", strip=True)[:6000]
        return self.normalize(item)

    def capabilities(self) -> dict:
        return {"pagination": True, "backfill": int(self.config.get("max_pages", 1)) > 1, "method": self.__class__.__name__}


class CSCECOrganizationAdapter(BaseAdapter):
    """Organization discovery is isolated from news ingestion."""

    last_html: str = ""

    def fetch_list(self, page: int = 1) -> list[SourceItem]:
        if page != 1:
            return []
        response = self._get(self.config.get("endpoint", self.source_url))
        self.last_html = response.text
        rows = parse_cscec_organization(response.text, self.source_url)
        return [
            self.normalize(SourceItem(
                title=row["canonical_name"] or "",
                url=row["official_url"] or self.source_url,
                published_at=None,
                excerpt="中国建筑组织架构成员企业链接",
                language="zh",
                raw={"entity_discovery": True, **row},
            ))
            for row in rows
        ]

    def fetch_detail(self, item: SourceItem) -> SourceItem:
        return item

    def capabilities(self) -> dict:
        return {"pagination": False, "backfill": False, "entity_discovery": True, "method": self.__class__.__name__}


def _parse_cscec_date(value: str | None) -> datetime | None:
    if not value:
        return None
    match = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", value)
    if not match:
        return None
    year, month, day = map(int, match.groups())
    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None
