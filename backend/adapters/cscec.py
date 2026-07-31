from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import requests

from adapters.base import BackfillPage, BaseAdapter, SourceItem, canonicalize_url
from cscec import extract_pdf_text, parse_cscec_organization


NEWS_SECTION_TERMS = (
    "公司要闻", "企业要闻", "集团要闻", "局要闻", "新闻中心",
    "中建要闻", "新闻动态", "最新动态", "媒体聚焦",
)
ARTICLE_PATH_RE = re.compile(
    r"(?:/20\d{2}(?:0[1-9]|1[0-2])?/|\d{6,}/|content|article|detail|news|xwzx|gsyw|wjyw).*\.s?html?$",
    re.I,
)
INDEX_WORDS = {"首页", "更多", "返回", "下一页", "上一页", "新闻中心", "公司要闻", "集团要闻"}
WECHAT_HOSTS = {"mp.weixin.qq.com", "weixin.qq.com"}
PDF_PATH_RE = re.compile(r"\.pdf(?:$|[?#])", re.I)
GOVERNANCE_ANNOUNCEMENT_TERMS = (
    "任免", "任命", "聘任", "离任", "辞任", "辞职", "退休", "免去",
    "选举", "董事候选人", "职工代表董事", "高级管理人员", "董事会决议",
    "组织架构", "机构调整", "名称变更", "更名", "股权划转", "设立", "注销",
    "法定代表人",
)


class CSCECNewsAdapter(BaseAdapter):
    """CSCEC site-family adapter with public news-section auto discovery.

    Some CSCEC subsidiaries publish article links on their official index page
    but host the body on WeChat. Those links are recorded as metadata-only
    leads; this adapter never downloads WeChat article bodies automatically.
    """

    def _page_url(self, page: int) -> str:
        endpoint = self.config.get("endpoint", self.source_url)
        if page <= 1:
            return endpoint
        pattern = self.config.get("page_pattern")
        return pattern.format(page=page, index=page - 1) if pattern else endpoint

    def fetch_list(self, page: int = 1) -> list[SourceItem]:
        if page > int(self.config.get("max_pages", 1)):
            return []
        endpoint = self._page_url(page)
        candidates = [endpoint]
        homepage_html = ""
        if page == 1 and self.config.get("auto_discover_news", False):
            response = self._get(endpoint)
            homepage_html = _response_text(response)
            candidates = self._discover_sections(homepage_html, response.url)

        rows: list[SourceItem] = []
        errors: list[Exception] = []
        for candidate in candidates:
            try:
                if candidate == endpoint and homepage_html:
                    html = homepage_html
                    page_url = endpoint
                else:
                    response = self._get(candidate)
                    html = _response_text(response)
                    page_url = response.url
                extracted = self._extract_items(html, page_url)
                if extracted:
                    rows.extend(extracted)
                    # A discovered, dated list is more reliable than navigation links.
                    if sum(item.published_at is not None for item in extracted) >= 3:
                        break
            except (requests.RequestException, PermissionError) as exc:
                errors.append(exc)

        unique: dict[str, SourceItem] = {}
        for item in rows:
            item = self.normalize(item)
            if self.validate(item):
                unique[item.url] = item
        if not unique and errors and len(errors) == len(candidates):
            raise errors[-1]
        return list(unique.values())[: int(self.config.get("limit", 50))]

    def _discover_sections(self, html: str, page_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        home_host = urlparse(page_url).hostname
        ranked: list[tuple[int, str]] = []
        for anchor in soup.select("a[href]"):
            label = _clean_text(anchor.get("title") or anchor.get_text(" ", strip=True))
            if not label:
                continue
            score = max((100 - index for index, term in enumerate(NEWS_SECTION_TERMS) if term in label), default=0)
            if not score:
                continue
            url = canonicalize_url(urljoin(page_url, anchor.get("href", "")))
            if urlparse(url).hostname != home_host:
                continue
            ranked.append((score, url))
        ranked.sort(key=lambda row: row[0], reverse=True)
        ordered = [url for _score, url in ranked]
        ordered.append(canonicalize_url(page_url))
        return list(dict.fromkeys(ordered))[: int(self.config.get("discovery_limit", 8))]

    def _extract_items(self, html: str, page_url: str) -> list[SourceItem]:
        soup = BeautifulSoup(html, "html.parser")
        selectors = self.config.get(
            "item_selector",
            ".list li, .news-list li, .zqydt li, .news li, .article-list li, article, ul li",
        )
        anchors = []
        for node in soup.select(selectors):
            anchor = node if node.name == "a" and node.get("href") else node.select_one("a[href]")
            if anchor:
                anchors.append((node, anchor))
        if not anchors:
            anchors = [(anchor.parent or anchor, anchor) for anchor in soup.select("a[href]")]

        host = urlparse(page_url).hostname
        rows: list[SourceItem] = []
        for node, anchor in anchors:
            title = _clean_text(anchor.get("title") or anchor.get_text(" ", strip=True))
            if len(title) < 4 or title in INDEX_WORDS:
                continue
            url = canonicalize_url(urljoin(page_url, anchor.get("href", "")))
            parsed = urlparse(url)
            is_wechat = parsed.hostname in WECHAT_HOSTS
            is_same_host = parsed.hostname == host
            context = _clean_text(node.get_text(" ", strip=True))
            date_node = node.select_one("time, .date, .time, [class*='date'], [class*='time']")
            date_text = (
                date_node.get("datetime") or date_node.get_text(" ", strip=True)
                if date_node
                else context
            )
            published = _parse_cscec_date(date_text)
            article_like = bool(ARTICLE_PATH_RE.search(parsed.path)) or published is not None
            if not is_wechat and (not is_same_host or not article_like):
                continue
            if is_wechat and not self.config.get("include_wechat_index_leads", True):
                continue
            excerpt_node = node.select_one("p, .summary, .intro, .desc")
            raw = {
                "list_page_url": page_url,
                "wechat_link_only": is_wechat,
                "manual_verification_required": is_wechat,
                "official_index_url": page_url if is_wechat else None,
            }
            rows.append(SourceItem(
                title=title,
                url=url,
                published_at=published,
                excerpt=_clean_text(excerpt_node.get_text(" ", strip=True)) if excerpt_node else "",
                language="zh",
                raw=raw,
            ))
        return rows

    def fetch_detail(self, item: SourceItem) -> SourceItem:
        if item.raw.get("wechat_link_only"):
            item.excerpt = item.excerpt or "中建官方网页列出的公众号文章线索；正文未自动抓取，建议核验官方来源。"
            return self.normalize(item)
        response = self._get(item.url)
        soup = BeautifulSoup(_response_text(response), "html.parser")
        title = soup.select_one("meta[property='og:title'], h1, .article-title, .title")
        if title:
            item.title = title.get("content") or title.get_text(" ", strip=True)
        if not item.published_at:
            date_node = soup.select_one(
                "meta[property='article:published_time'], meta[name='publishdate'], "
                "time, .article-date, .date, .time, [class*='publish']"
            )
            if date_node:
                item.published_at = _parse_cscec_date(
                    date_node.get("content") or date_node.get("datetime") or date_node.get_text(" ", strip=True)
                )
        for unwanted in soup.select("script, style, noscript, nav, footer, form"):
            unwanted.decompose()
        content = soup.select_one(
            self.config.get(
                "content_selector",
                ".TRS_Editor, .article-content, .article_content, .content-main, .detail-content, article, main",
            )
        )
        if content:
            item.excerpt = _clean_text(content.get_text(" ", strip=True))[:6000]
        return self.normalize(item)

    def capabilities(self) -> dict:
        return {
            "pagination": bool(self.config.get("page_pattern")),
            "backfill": int(self.config.get("max_pages", 1)) > 1,
            "auto_discovery": bool(self.config.get("auto_discover_news")),
            "wechat_link_discovery": bool(self.config.get("include_wechat_index_leads", True)),
            "method": self.__class__.__name__,
        }


class CSCECPDFAnnouncementAdapter(BaseAdapter):
    """Extract CSCEC stock disclosures whose detail pages are PDF files.

    The official announcement page renders every year in the initial HTML. A
    regular crawl therefore selects the newest disclosures plus governance
    disclosures, while archive backfill walks the full catalog in small
    batches. PDF links remain the article's original URL for auditability.
    """

    _catalog_cache: list[SourceItem] | None = None

    def fetch_list(self, page: int = 1) -> list[SourceItem]:
        if page != 1:
            return []
        catalog = self._load_catalog()
        recent_limit = max(1, int(self.config.get("recent_limit", 25)))
        priority_limit = max(0, int(self.config.get("priority_limit", 35)))
        priority_days = max(1, int(self.config.get("priority_lookback_days", 730)))
        cutoff = datetime.now(timezone.utc) - timedelta(days=priority_days)
        selected = list(catalog[:recent_limit])
        priority = [
            item
            for item in catalog
            if any(term in item.title for term in GOVERNANCE_ANNOUNCEMENT_TERMS)
            and (item.published_at is None or item.published_at >= cutoff)
        ][:priority_limit]
        return _unique_items([*selected, *priority])

    def fetch_backfill(self, page: int = 1, cursor: str | None = None) -> BackfillPage:
        catalog = self._load_catalog()
        offset = int(cursor) if cursor and cursor.isdigit() else max(0, page - 1) * int(
            self.config.get("backfill_batch_size", 10)
        )
        batch_size = max(1, min(25, int(self.config.get("backfill_batch_size", 10))))
        batch = catalog[offset:offset + batch_size]
        detailed: list[SourceItem] = []
        for item in batch:
            try:
                detailed.append(self.fetch_detail(item))
            except (requests.RequestException, PermissionError):
                detailed.append(item)
        next_offset = offset + len(batch)
        exhausted = not batch or next_offset >= len(catalog)
        return BackfillPage(
            items=detailed,
            next_cursor=None if exhausted else str(next_offset),
            exhausted=exhausted,
        )

    def _load_catalog(self) -> list[SourceItem]:
        if self._catalog_cache is not None:
            return self._catalog_cache
        endpoint = self.config.get("endpoint", self.source_url)
        response = self._get(endpoint)
        soup = BeautifulSoup(_response_text(response), "html.parser")
        selector = self.config.get("item_selector", "ul.yxj-list li")
        allowed_host = urlparse(response.url).hostname
        rows: list[SourceItem] = []
        for node in soup.select(selector):
            anchor = node.select_one("a[href]") if node.name != "a" else node
            if not anchor:
                continue
            href = (anchor.get("href") or "").strip()
            if not PDF_PATH_RE.search(href):
                continue
            url = canonicalize_url(urljoin(response.url, href))
            if urlparse(url).hostname != allowed_host:
                continue
            title = _clean_text(anchor.get("title") or anchor.get_text(" ", strip=True))
            if len(title) < 4:
                continue
            date_node = node.select_one("time, span, .date, .time, [class*='date'], [class*='time']")
            date_text = (
                date_node.get("datetime") or date_node.get_text(" ", strip=True)
                if date_node
                else node.get_text(" ", strip=True)
            )
            item = self.normalize(SourceItem(
                title=title,
                url=url,
                published_at=_parse_cscec_date(date_text),
                excerpt=f"中国建筑官方公司公告：{title}",
                language="zh",
                raw={
                    "list_page_url": response.url,
                    "official_index_url": response.url,
                    "document_format": "pdf",
                    "pdf_url": url,
                    "immutable_document": True,
                    "pdf_text_status": "pending",
                },
            ))
            if self.validate(item):
                rows.append(item)
        self._catalog_cache = sorted(
            _unique_items(rows),
            key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return self._catalog_cache

    def fetch_detail(self, item: SourceItem) -> SourceItem:
        response = self._get(item.url, stream=True)
        content_type = response.headers.get("content-type", "").lower()
        max_pdf_bytes = max(100_000, int(self.config.get("max_pdf_bytes", 15_000_000)))
        declared_length = int(response.headers.get("content-length") or 0)
        if declared_length > max_pdf_bytes:
            response.close()
            raise requests.RequestException(
                f"PDF exceeds configured limit ({declared_length} > {max_pdf_bytes} bytes)"
            )
        payload = bytearray()
        if isinstance(response._content, bytes):
            payload.extend(response.content)
        else:
            for chunk in response.iter_content(65_536):
                payload.extend(chunk)
                if len(payload) > max_pdf_bytes:
                    response.close()
                    raise requests.RequestException(
                        f"PDF exceeds configured limit ({max_pdf_bytes} bytes)"
                    )
        if len(payload) > max_pdf_bytes:
            response.close()
            raise requests.RequestException(
                f"PDF exceeds configured limit ({max_pdf_bytes} bytes)"
            )
        response.close()
        if "pdf" not in content_type and not bytes(payload).startswith(b"%PDF"):
            raise requests.RequestException(
                f"announcement link did not return a PDF ({content_type or 'unknown content type'})"
            )
        item.raw.update({
            "pdf_content_type": content_type or "application/pdf",
            "pdf_size_bytes": len(payload),
        })
        try:
            text = extract_pdf_text(
                bytes(payload),
                max_pages=max(1, int(self.config.get("max_pdf_pages", 100))),
            )
        except Exception as exc:
            item.raw.update({
                "pdf_text_status": "parse_failed",
                "pdf_text_error": f"{exc.__class__.__name__}: {str(exc)[:300]}",
            })
            item.excerpt = (
                f"中国建筑官方公司公告：{item.title}。PDF 已获取，但正文解析失败，"
                "需人工核验或 OCR。"
            )
            return self.normalize(item)
        if text:
            item.raw["pdf_text_status"] = "extracted"
            item.raw["pdf_text_length"] = len(text)
            item.excerpt = text
        else:
            item.raw["pdf_text_status"] = "requires_ocr"
            item.excerpt = (
                f"中国建筑官方公司公告：{item.title}。该 PDF 未包含可提取文本，"
                "可能为扫描件，需 OCR 或人工核验。"
            )
        return self.normalize(item)

    def capabilities(self) -> dict:
        return {
            "pagination": False,
            "backfill": True,
            "pdf_text_extraction": True,
            "scanned_pdf_detection": True,
            "method": self.__class__.__name__,
        }


class CSCECOrganizationAdapter(BaseAdapter):
    """Organization discovery is isolated from news ingestion."""

    last_html: str = ""

    def fetch_list(self, page: int = 1) -> list[SourceItem]:
        if page != 1:
            return []
        response = self._get(self.config.get("endpoint", self.source_url))
        self.last_html = _response_text(response)
        rows = parse_cscec_organization(self.last_html, self.source_url)
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


def _response_text(response: requests.Response) -> str:
    if not response.encoding or response.encoding.lower() in {"iso-8859-1", "ascii"}:
        response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _unique_items(items: list[SourceItem]) -> list[SourceItem]:
    unique: dict[str, SourceItem] = {}
    for item in items:
        unique[item.url] = item
    return list(unique.values())


def _parse_cscec_date(value: str | None) -> datetime | None:
    if not value:
        return None
    full = re.search(r"(20\d{2})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})\s*日?", value)
    if full:
        year, month, day = map(int, full.groups())
    else:
        short = re.search(r"(?<!\d)(\d{1,2})\s*[-/.月]\s*(\d{1,2})\s*日?(?!\d)", value)
        if not short:
            return None
        now = datetime.now(timezone.utc)
        year = now.year
        month, day = map(int, short.groups())
        try:
            candidate = datetime(year, month, day, tzinfo=timezone.utc)
            if candidate > now + timedelta(days=31):
                year -= 1
        except ValueError:
            return None
    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None
