from adapters.feeds import RSSAdapter


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
