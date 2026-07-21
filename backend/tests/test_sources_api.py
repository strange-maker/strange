def test_sources_expose_explicit_adapter_states(client,admin_headers):
    sources=client.get("/api/sources",headers=admin_headers).json()
    assert len(sources) >= 150
    states={x["adapter_status"] for x in sources}
    assert {"active","pending_adapter","manual_only"}.issubset(states)
    assert all(x["latest_status"] != "success" for x in sources)
    wechat=[x for x in sources if x["source_type"] == "wechat_manual"]
    assert len(wechat) == 13 and all(x["crawl_method"] == "manual_import" for x in wechat)
    assert len([x for x in sources if x["adapter_status"] == "active"]) == 10
    dual=[x for x in sources if "许继" in x["source_name"] or "平高" in x["source_name"]]
    assert dual and all("competitor_subject" in x["source_tags"] for x in dual)


def test_manual_web_import_creates_traceable_source(client,admin_headers):
    response=client.post("/api/articles/manual-import",headers=admin_headers,json={"original_url":"https://example.com/project-saudi","title":"Saudi Arabia overseas solar project tender","content_text":"Saudi Arabia announces an overseas solar project tender with international EPC participation.","source_name":"Example manual web","import_type":"web"})
    assert response.status_code == 201
    assert response.json()["source_type"] == "media"
    assert response.json()["verification_notice"]
