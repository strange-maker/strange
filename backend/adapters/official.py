from __future__ import annotations

from datetime import datetime, timezone

from bs4 import BeautifulSoup

from adapters.base import BaseAdapter, SourceItem


class WorldBankDocumentsAdapter(BaseAdapter):
    """Official World Bank Documents API, restricted to recent procurement plans."""
    def fetch_list(self, page: int = 1) -> list[SourceItem]:
        params={"format":"json","rows":self.config.get("limit",50),"os":(page-1)*self.config.get("limit",50),"fl":"docdt,docty,count,display_title,abstracts,url,projectid","docty_exact":"Procurement Plan","sort":"docdt","order":"desc"}
        response=self._get(self.config["endpoint"], params=params)
        payload=response.json(); documents=payload.get("documents", {})
        rows=documents.values() if isinstance(documents, dict) else documents
        items=[]
        for row in rows:
            title=row.get("display_title") or row.get("docty") or ""
            url=row.get("url") or row.get("pdfurl") or ""
            date=_parse_date(row.get("docdt"))
            excerpt=row.get("abstracts") or row.get("count") or ""
            items.append(self.normalize(SourceItem(title=title,url=url,published_at=date,excerpt=excerpt,language="en",raw={"project_id":row.get("projectid")})))
        return [x for x in items if self.validate(x)]


class HTMLListAdapter(BaseAdapter):
    def fetch_list(self, page: int = 1) -> list[SourceItem]:
        if page > self.config.get("max_pages", 1): return []
        endpoint=self.config["endpoint"].format(page=page)
        response=self._get(endpoint)
        soup=BeautifulSoup(response.text,"html.parser")
        items=[]
        for node in soup.select(self.config["item_selector"])[: self.config.get("limit", 40)]:
            link=node if self.config.get("node_is_link") else node.select_one(self.config.get("link_selector", "a"))
            if not link: continue
            title_node=link if self.config.get("node_is_link") else node.select_one(self.config.get("title_selector", self.config.get("link_selector", "a"))) or link
            excerpt_node=node.select_one(self.config.get("excerpt_selector", ".summary, p"))
            date_node=node.select_one(self.config.get("date_selector", "time, .date"))
            items.append(self.normalize(SourceItem(title=title_node.get_text(" ",strip=True),url=link.get("href", ""),published_at=_parse_date(date_node.get_text(" ",strip=True) if date_node else None),excerpt=excerpt_node.get_text(" ",strip=True) if excerpt_node else "")))
        return [x for x in items if self.validate(x)]

    def fetch_detail(self, item: SourceItem) -> SourceItem:
        response=self._get(item.url); soup=BeautifulSoup(response.text,"html.parser")
        content=soup.select_one(self.config.get("content_selector", "article, main"))
        if content: item.excerpt=content.get_text(" ",strip=True)[:6000]
        return self.normalize(item)


def _parse_date(value: str | None) -> datetime | None:
    if not value: return None
    raw=value.strip().replace("Z", "+00:00")
    for candidate in [raw, raw[:10]]:
        try:
            result=datetime.fromisoformat(candidate)
            return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
        except ValueError: pass
    return None
