import manual_extract


def test_manual_html_parser_extracts_wechat_article():
    html="""<html><head>
      <meta property="og:title" content="中建海外项目公开动态">
      <meta property="article:published_time" content="2026-07-30 10:20:00">
    </head><body><div id="js_content"><p>这是公众号公开文章正文，内容用于人工导入预览。</p></div></body></html>"""
    result=manual_extract._parse_article_html(html,"https://mp.weixin.qq.com/s/example","wechat")
    assert result["title"] == "中建海外项目公开动态"
    assert "人工导入预览" in result["content_text"]
    assert result["published_at"].startswith("2026-07-30")
    assert result["verification_notice"] == "媒体线索，建议核验官方公告"


def test_manual_preview_api_is_explicit_and_authenticated(client,admin_headers,monkeypatch):
    monkeypatch.setattr(manual_extract,"extract_public_article",lambda url,kind:{
        "original_url":url,
        "title":"中建公开文章",
        "content_text":"这是长度足够的中建公开文章正文内容，用于人工确认后再导入。",
        "published_at":"2026-07-30T00:00:00+00:00",
        "source_hint":"公众号公开文章",
        "verification_notice":"媒体线索，建议核验官方公告",
    })
    unauthenticated=client.post("/api/articles/manual-import/preview",json={
        "original_url":"https://mp.weixin.qq.com/s/example",
        "import_type":"wechat",
    })
    assert unauthenticated.status_code == 401
    response=client.post("/api/articles/manual-import/preview",headers=admin_headers,json={
        "original_url":"https://mp.weixin.qq.com/s/example",
        "import_type":"wechat",
    })
    assert response.status_code == 200
    assert response.json()["title"] == "中建公开文章"
