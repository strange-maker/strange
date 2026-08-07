import json

from sqlalchemy import select

from database import SessionLocal
from models import Article, ManualImportBatch, Source


def _wechat_source_name() -> str:
    with SessionLocal() as db:
        source = db.scalar(
            select(Source).where(
                Source.source_type == "wechat_manual",
                Source.crawl_method == "manual_import",
            )
        )
        assert source is not None
        return source.source_name


def test_schinza_batch_preview_requires_auth_and_returns_diagnostics(
    client, admin_headers
):
    payload = {
        "filename": "history.json",
        "source_name": _wechat_source_name(),
        "content_text": json.dumps(
            [
                {
                    "title": "中建五局海外合作",
                    "link": "https://mp.weixin.qq.com/s/a",
                    "publish_at": "2026-08-01",
                    "digest": "吉尔吉斯斯坦交通基础设施合作线索",
                },
                {
                    "title": "中建与ABB在商会交流数据中心合作",
                    "link": "https://mp.weixin.qq.com/s/b",
                    "publish_at": "2026-08-02",
                    "content_text": "中国对外承包工程商会活动上，中建与ABB交流海外数据中心项目。",
                },
            ],
            ensure_ascii=False,
        ),
    }

    assert (
        client.post("/api/articles/manual-import/batch-preview", json=payload).status_code
        == 401
    )
    response = client.post(
        "/api/articles/manual-import/batch-preview",
        headers=admin_headers,
        json=payload,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_count"] == 2
    assert data["missing_body_count"] == 1
    assert data["items"][0]["source_type"] == "wechat_manual"
    assert data["items"][0]["reliability_level"] == "low"
    assert "file_sha256" in data
    assert {"ka_dynamic", "competitor_dynamic", "chamber_association"} <= set(
        data["items"][1]["topic_tags"]
    )


def test_schinza_batch_confirm_requires_preview_sha(client, admin_headers):
    payload = {
        "filename": "history.json",
        "source_name": _wechat_source_name(),
        "content_text": json.dumps(
            [
                {
                    "title": "中建五局海外合作",
                    "url": "https://mp.weixin.qq.com/s/requires-preview",
                }
            ],
            ensure_ascii=False,
        ),
    }

    response = client.post(
        "/api/articles/manual-import/batch",
        headers=admin_headers,
        json=payload,
    )

    assert response.status_code == 422
    assert "expected_file_sha256" in response.text


def test_schinza_batch_import_is_audited_idempotent_and_enriched(
    client, admin_headers
):
    payload = {
        "filename": "history.json",
        "source_name": _wechat_source_name(),
        "content_text": json.dumps(
            [
                {
                    "title": "吉尔吉斯斯坦交通和通信部到中建五局调研交流",
                    "url": "https://mp.weixin.qq.com/s/schinza-a",
                    "published_at": "2026-08-01",
                    "content_text": (
                        "吉尔吉斯斯坦交通和通信部代表团到访中建五局。"
                        "中建五局董事长田卫国参加。双方讨论基础设施拟合作项目后续推进计划。"
                        "中建五局海外事业部参加。"
                    ),
                }
            ],
            ensure_ascii=False,
        ),
    }
    preview_response = client.post(
        "/api/articles/manual-import/batch-preview",
        headers=admin_headers,
        json=payload,
    )
    assert preview_response.status_code == 200, preview_response.text
    payload["expected_file_sha256"] = preview_response.json()["file_sha256"]

    response = client.post(
        "/api/articles/manual-import/batch", headers=admin_headers, json=payload
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["success_count"] == 1
    assert data["status"] == "completed"

    repeated = client.post(
        "/api/articles/manual-import/batch", headers=admin_headers, json=payload
    )
    assert repeated.status_code == 200
    assert repeated.json()["id"] == data["id"]
    assert repeated.json()["idempotent_replay"] is True

    status_response = client.get(
        f"/api/articles/manual-import/batches/{data['id']}",
        headers=admin_headers,
    )
    assert status_response.status_code == 200
    assert status_response.json()["file_sha256"] == payload["expected_file_sha256"]

    with SessionLocal() as db:
        batch = db.get(ManualImportBatch, data["id"])
        article = db.scalar(
            select(Article).where(
                Article.original_url == "https://mp.weixin.qq.com/s/schinza-a"
            )
        )
        assert batch is not None
        assert article is not None
        assert article.manual_import_batch_id == batch.id
        assert article.source_type == "wechat_manual"
        assert article.reliability_level == "low"
        assert article.sales_relevance_score >= 50
        assert "ka_dynamic" in article.topic_tags
