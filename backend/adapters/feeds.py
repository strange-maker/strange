from __future__ import annotations

from datetime import datetime, timezone

import feedparser
from bs4 import BeautifulSoup

from adapters.base import BaseAdapter, SourceItem


class RSSAdapter(BaseAdapter):
    def fetch_list(self, page: int = 1) -> list[SourceItem]:
        if page > 1: return []
        endpoint = self.config["endpoint"]
        response = self._get(endpoint)
        feed = feedparser.parse(response.content)
        if getattr(feed, "bozo", False) and not feed.entries:
            raise ValueError(f"invalid feed: {getattr(feed, 'bozo_exception', 'unknown')}")
        items=[]
        for entry in feed.entries[: self.config.get("limit", 50)]:
            published = _feed_date(entry)
            excerpt = BeautifulSoup(entry.get("summary", entry.get("description", "")), "html.parser").get_text(" ", strip=True)
            items.append(self.normalize(SourceItem(title=entry.get("title", ""), url=entry.get("link", ""), published_at=published, author=entry.get("author"), excerpt=excerpt, raw={"id":entry.get("id")})))
        return [x for x in items if self.validate(x)]


def _feed_date(entry) -> datetime | None:
    value = entry.get("published_parsed") or entry.get("updated_parsed")
    if not value: return None
    return datetime(*value[:6], tzinfo=timezone.utc)
