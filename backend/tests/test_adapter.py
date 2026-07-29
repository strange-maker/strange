from adapters.feeds import RSSAdapter
from adapters.official import SitemapAdapter


class Response:
    status_code=200
    content=b'''<rss version="2.0"><channel><item><title>Saudi solar project tender</title><link>https://example.com/a?utm_source=x</link><description>New 500MW EPC opportunity</description><pubDate>Mon, 20 Jul 2026 08:00:00 GMT</pubDate></item></channel></rss>'''
    def raise_for_status(self): pass


def test_rss_adapter_normalizes_and_validates(monkeypatch):
    adapter=RSSAdapter("https://example.com",{"endpoint":"https://example.com/feed"})
    monkeypatch.setattr(adapter,"_get",lambda *args,**kwargs:Response())
    items=adapter.fetch_list()
    assert len(items) == 1
    assert items[0].url == "https://example.com/a"
    assert items[0].published_at.tzinfo is not None


def test_sitemap_adapter_filters_paginates_and_extracts_detail(monkeypatch):
    sitemap=type("SitemapResponse",(),{
        "status_code":200,
        "text":"""<urlset>
          <url><loc>https://example.com/news/solar-project</loc><lastmod>2026-07-20</lastmod></url>
          <url><loc>https://example.com/products/switch</loc><lastmod>2026-07-19</lastmod></url>
        </urlset>""",
    })()
    detail=type("DetailResponse",(),{
        "status_code":200,
        "text":"""<html><head><meta property="og:title" content="Saudi solar project award">
          <meta property="article:published_time" content="2026-07-20T08:00:00Z"></head>
          <body><article>Saudi Arabia awarded a solar EPC project.</article></body></html>""",
    })()
    adapter=SitemapAdapter("https://example.com",{
        "endpoint":"https://example.com/sitemap.xml","include_regex":r"/news/",
        "limit":1,"max_pages":10,"fetch_detail":True,
    })
    monkeypatch.setattr(adapter,"_get",lambda url,**_kwargs:detail if "/news/" in url else sitemap)
    items=adapter.fetch_list(1)
    assert len(items) == 1 and items[0].title == "solar project"
    assert adapter.fetch_list(2) == []
    enriched=adapter.fetch_detail(items[0])
    assert enriched.title == "Saudi solar project award"
    assert enriched.published_at.tzinfo is not None
    assert "Saudi Arabia" in enriched.excerpt
