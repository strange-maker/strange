from __future__ import annotations

from datetime import datetime, timezone
import re
from urllib.parse import unquote, urlparse

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


class SitemapAdapter(BaseAdapter):
    """Low-frequency public sitemap adapter with optional URL-scope filtering."""

    def _entries(self) -> list[tuple[str, datetime | None]]:
        response=self._get(self.config["endpoint"])
        documents=[response.text]
        if "<sitemapindex" in response.text[:4000].lower():
            child_urls=re.findall(r"<loc>\s*(.*?)\s*</loc>",response.text,re.I|re.S)
            child_pattern=self.config.get("sitemap_include_regex")
            if child_pattern:
                child_urls=[url for url in child_urls if re.search(child_pattern,url,re.I)]
            for url in child_urls[: self.config.get("max_sitemaps",4)]:
                documents.append(self._get(url.strip()).text)
        entries=[]
        for document in documents:
            for block in re.findall(r"<url\b.*?</url>",document,re.I|re.S):
                loc=re.search(r"<loc>\s*(.*?)\s*</loc>",block,re.I|re.S)
                if not loc: continue
                url=loc.group(1).strip().replace("&amp;","&")
                include=self.config.get("include_regex")
                exclude=self.config.get("exclude_regex")
                if include and not re.search(include,url,re.I): continue
                if exclude and re.search(exclude,url,re.I): continue
                lastmod=re.search(r"<lastmod>\s*(.*?)\s*</lastmod>",block,re.I|re.S)
                entries.append((url,_parse_date(lastmod.group(1)) if lastmod else None))
        entries.sort(key=lambda value:value[1] or datetime.min.replace(tzinfo=timezone.utc),reverse=True)
        return entries

    def fetch_list(self, page: int = 1) -> list[SourceItem]:
        limit=self.config.get("limit",40)
        entries=self._entries()[(page-1)*limit:page*limit]
        items=[]
        for url,published in entries:
            slug=unquote(urlparse(url).path.rstrip("/").split("/")[-1])
            title=re.sub(r"[-_]+"," ",slug).strip() or urlparse(url).netloc
            items.append(self.normalize(SourceItem(title=title,url=url,published_at=published,language=self.config.get("language","unknown"))))
        return [item for item in items if self.validate(item)]

    def fetch_detail(self, item: SourceItem) -> SourceItem:
        response=self._get(item.url)
        soup=BeautifulSoup(response.text,"html.parser")
        title=soup.select_one("meta[property='og:title'], meta[name='twitter:title']")
        heading=soup.select_one("h1, article h2, title")
        if title and title.get("content"): item.title=title["content"]
        elif heading: item.title=heading.get_text(" ",strip=True)
        published=soup.select_one("meta[property='article:published_time'], meta[name='date'], time[datetime]")
        if not item.published_at and published:
            item.published_at=_parse_date(published.get("content") or published.get("datetime") or published.get_text(" ",strip=True))
        content=soup.select_one(self.config.get("content_selector","article, main"))
        if content: item.excerpt=content.get_text(" ",strip=True)[:6000]
        return self.normalize(item)

    def capabilities(self) -> dict:
        return {"pagination":True,"backfill":True,"method":self.__class__.__name__}


def _parse_date(value: str | None) -> datetime | None:
    if not value: return None
    raw=value.strip().replace("Z", "+00:00")
    for candidate in [raw, raw[:10]]:
        try:
            result=datetime.fromisoformat(candidate)
            return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
        except ValueError: pass
    return None
