import json

import pytest


def test_rejects_schinza_credentials_before_preview():
    from schinza_import import SensitiveExportError, parse_schinza_export

    payload = '{"accounts":[{"uin":"123","pass_ticket":"secret"}],"articles":[]}'

    with pytest.raises(SensitiveExportError, match="敏感凭证"):
        parse_schinza_export("history.json", payload)


def test_rejects_credentials_embedded_in_article_url():
    from schinza_import import SensitiveExportError, parse_schinza_export

    payload = json.dumps(
        [
            {
                "title": "含凭证链接",
                "url": (
                    "https://mp.weixin.qq.com/s/a?"
                    "pass_ticket=secret&appmsg_token=also-secret"
                ),
            }
        ],
        ensure_ascii=False,
    )

    with pytest.raises(SensitiveExportError, match="敏感凭证"):
        parse_schinza_export("history.json", payload)


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        (
            "history.json",
            json.dumps(
                [
                    {
                        "title": "中建五局海外合作",
                        "link": "https://mp.weixin.qq.com/s/a",
                        "publish_at": "2026-08-01",
                        "digest": "摘要",
                    }
                ],
                ensure_ascii=False,
            ),
        ),
        (
            "history.csv",
            "title,link,publish_at,digest\n"
            "中建五局海外合作,https://mp.weixin.qq.com/s/a,2026-08-01,摘要\n",
        ),
        (
            "body.json",
            json.dumps(
                {
                    "articles": [
                        {
                            "title": "中建五局海外合作",
                            "url": "https://mp.weixin.qq.com/s/a",
                            "content_text": "这是足够长的公众号文章正文，用于批量导入销售情报。",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
        ),
    ],
)
def test_parses_supported_schinza_exports(filename, content):
    from schinza_import import parse_schinza_export

    preview = parse_schinza_export(filename, content)

    assert preview.items[0].title == "中建五局海外合作"
    assert preview.items[0].original_url == "https://mp.weixin.qq.com/s/a"


def test_rejects_non_wechat_urls_and_reports_invalid_rows():
    from schinza_import import parse_schinza_export

    payload = json.dumps(
        [
            {"title": "合法文章", "url": "https://mp.weixin.qq.com/s/a"},
            {"title": "错误来源", "url": "https://example.com/article"},
            {"title": "", "url": "https://mp.weixin.qq.com/s/b"},
        ],
        ensure_ascii=False,
    )

    preview = parse_schinza_export("history.json", payload)

    assert preview.total_count == 1
    assert len(preview.invalid_rows) == 2
    assert {row["reason"] for row in preview.invalid_rows} == {
        "仅支持微信公众平台公开文章链接",
        "缺少标题",
    }


def test_limits_file_size_and_record_count():
    from schinza_import import parse_schinza_export

    with pytest.raises(ValueError, match="5 MB"):
        parse_schinza_export("history.json", "x" * 5_000_001)

    payload = json.dumps(
        [
            {"title": f"文章 {index}", "url": f"https://mp.weixin.qq.com/s/{index}"}
            for index in range(2)
        ],
        ensure_ascii=False,
    )
    with pytest.raises(ValueError, match="最多导入 1 条"):
        parse_schinza_export("history.json", payload, max_records=1)
