from __future__ import annotations

from datetime import datetime, timezone
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
import requests

from config import get_settings


MAX_BYTES = 2_000_000
MAX_REDIRECTS = 4
WECHAT_HOSTS = {"mp.weixin.qq.com", "weixin.qq.com"}
settings = get_settings()


def extract_public_article(url: str, import_type: str) -> dict:
    current = _validate_public_url(url)
    if import_type == "wechat" and urlparse(current).hostname not in WECHAT_HOSTS:
        raise ValueError("公众号提取仅支持公开的 mp.weixin.qq.com 文章链接")

    session = requests.Session()
    session.headers.update({
        "User-Agent": settings.crawl_user_agent,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
    })
    _assert_robots_allowed(session, current)
    response = None
    for _ in range(MAX_REDIRECTS + 1):
        response = session.get(
            current,
            timeout=settings.crawl_timeout_seconds,
            allow_redirects=False,
            stream=True,
        )
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("location")
            response.close()
            if not location:
                raise ValueError("目标网页返回了无地址的跳转")
            current = _validate_public_url(urljoin(current, location))
            if import_type == "wechat" and urlparse(current).hostname not in WECHAT_HOSTS:
                raise ValueError("公众号链接跳转到了非微信域名，已停止提取")
            _assert_robots_allowed(session, current)
            continue
        break
    else:
        raise ValueError("目标网页跳转次数过多")

    if response is None:
        raise ValueError("未取得目标网页响应")
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "html" not in content_type and "text/" not in content_type:
        raise ValueError("链接不是可提取的公开 HTML 网页")
    payload = bytearray()
    for chunk in response.iter_content(65536):
        payload.extend(chunk)
        if len(payload) > MAX_BYTES:
            response.close()
            raise ValueError("网页正文超过 2 MB，请改为手动粘贴正文")
    encoding = response.encoding
    if not encoding or encoding.lower() in {"iso-8859-1", "ascii"}:
        encoding = response.apparent_encoding or "utf-8"
    html = bytes(payload).decode(encoding, errors="replace")
    response.close()
    lowered = html.lower()
    if any(marker in lowered for marker in ("captcha", "recaptcha", "hcaptcha", "验证您是真人")):
        raise PermissionError("网页要求验证码，系统不会绕过；请手动粘贴正文")
    return _parse_article_html(html, current, import_type)


def _parse_article_html(html: str, final_url: str, import_type: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.select_one(
        "#activity-name, meta[property='og:title'], meta[name='twitter:title'], h1, .article-title, .title"
    )
    title = ""
    if title_node:
        title = title_node.get("content") or title_node.get_text(" ", strip=True)
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)

    published_at = None
    date_node = soup.select_one(
        "#publish_time, meta[property='article:published_time'], meta[name='publishdate'], "
        "meta[name='PubDate'], time, .publish-time, .article-date"
    )
    if date_node:
        published_at = _parse_datetime(
            date_node.get("content") or date_node.get("datetime") or date_node.get_text(" ", strip=True)
        )

    for unwanted in soup.select("script, style, noscript, nav, footer, form, iframe"):
        unwanted.decompose()
    content = soup.select_one(
        "#js_content, .rich_media_content, .TRS_Editor, .article-content, "
        ".article_content, .detail-content, article, main"
    )
    if not content:
        content = soup.body
    text = re.sub(r"\s+", " ", content.get_text(" ", strip=True) if content else "").strip()
    title = re.sub(r"\s+", " ", title).strip()
    if len(title) < 2:
        raise ValueError("未识别到文章标题，请手动填写")
    if len(text) < 20:
        raise ValueError("未识别到公开正文，页面可能依赖登录或脚本；请手动粘贴正文")
    return {
        "original_url": final_url,
        "title": title[:500],
        "content_text": text[:50000],
        "published_at": published_at.isoformat() if published_at else None,
        "source_hint": "公众号公开文章" if import_type == "wechat" else (urlparse(final_url).hostname or ""),
        "verification_notice": "媒体线索，建议核验官方公告",
    }


def _validate_public_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("只支持完整的 http/https 公开链接")
    if parsed.username or parsed.password:
        raise ValueError("链接中不得包含用户名或密码")
    try:
        addresses = {
            row[4][0]
            for row in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
        }
    except socket.gaierror as exc:
        raise ValueError("无法解析链接域名") from exc
    if not addresses:
        raise ValueError("无法解析链接域名")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("不允许访问内网、本机或保留地址")
    return value.strip()


def _assert_robots_allowed(session: requests.Session, url: str) -> None:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    response = session.get(
        robots_url,
        timeout=min(settings.crawl_timeout_seconds, 10),
        allow_redirects=False,
    )
    if response.status_code in {404, 410}:
        return
    if response.status_code in {401, 403}:
        raise PermissionError("来源站不允许自动读取；请手动粘贴正文")
    if not response.ok:
        return
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())
    if not parser.can_fetch(settings.crawl_user_agent, url):
        raise PermissionError("robots.txt 不允许自动读取；请手动粘贴正文")


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip().replace("年", "-").replace("月", "-").replace("日", "")
    normalized = re.sub(r"\s+", " ", normalized)
    match = re.search(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?", normalized)
    if not match:
        return None
    year, month, day, hour, minute, second = match.groups()
    try:
        return datetime(
            int(year), int(month), int(day), int(hour or 0), int(minute or 0), int(second or 0),
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None
