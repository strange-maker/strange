from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from adapters import build_adapter
from adapters.registry import get_adapter_definition
from config import get_settings


ROOT=Path(__file__).resolve().parents[1]
SOURCES_PATH=ROOT/"public"/"sources.yaml"
REPORT_JSON=ROOT/"docs"/"source-expansion-report.json"
REPORT_MD=ROOT/"docs"/"source-expansion-report.md"
settings=get_settings()


def skipped(item: dict) -> str | None:
    notes=(item.get("notes") or "").lower()
    if item["crawl_method"] == "manual_import" or item["source_type"] == "wechat_manual": return "manual_only"
    if any(x in notes for x in ("付费","订阅制","登录","授权","禁止自动","验证码")): return "restricted_by_source_notes"
    return None


def check(item: dict,timeout: int) -> dict:
    checked_at=datetime.now(timezone.utc).isoformat()
    result={"source_name":item["source_name"],"source_url":item["source_url"],"checked_at":checked_at,"test_method":[],"http_status":None,"status":"timeout","crawlable":False,"one_year_backfill":False,"extracted_fields":[],"test_count":0,"failure_reason":None,"compliance_limits":[],"recommendation":"","details":{}}
    reason=skipped(item)
    if reason:
        result.update(status="manual_recommended" if reason == "manual_only" else "login_required",failure_reason=reason,compliance_limits=[reason],recommendation="保持人工导入或获得明确授权后再测试")
        return result
    session=requests.Session()
    session.headers.update({"User-Agent":settings.crawl_user_agent,"Accept":"text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.8"})
    parsed=urlparse(item["source_url"]); robots_url=f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        definition=get_adapter_definition(item["source_name"],item["source_url"],item)
        if definition and definition.get("initial_status") != "blocked":
            result["test_method"].append("registered_adapter")
            adapter=build_adapter(item["source_name"],item["source_url"],item.get("adapter_config") or {})
            adapter_items=adapter.fetch_list()
            if adapter_items and definition.get("fetch_detail"):
                detailed=[]
                for candidate in adapter_items[:5]:
                    try:
                        detailed.append(adapter.fetch_detail(candidate))
                    except requests.RequestException:
                        continue
                if detailed:
                    adapter_items=detailed
            result["http_status"]=adapter.last_http_status
            result["details"]["registered_adapter"]=adapter.__class__.__name__
            if adapter_items:
                dated=sum(x.published_at is not None for x in adapter_items)
                result.update(
                    status="adapter_working",crawlable=True,test_count=len(adapter_items),
                    extracted_fields=["title","original_url"]+(["published_at"] if dated else []),
                    one_year_backfill=bool(adapter.capabilities().get("backfill")),
                    recommendation="保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。",
                )
                result["details"]["dated_items"]=dated
                return result
        result["test_method"].append("robots.txt")
        robots=session.get(robots_url,timeout=timeout,allow_redirects=True)
        robots_text=robots.text if robots.status_code < 400 else ""
        if robots.status_code < 400:
            parser=RobotFileParser(); parser.set_url(robots_url); parser.parse(robots.text.splitlines())
            if not parser.can_fetch(settings.crawl_user_agent,item["source_url"]):
                result.update(status="robots_blocked",http_status=robots.status_code,failure_reason="robots.txt disallows this URL",compliance_limits=["robots.txt"],recommendation="不自动抓取；寻找官方API/RSS或人工导入")
                return result
        result["test_method"].append("https_get")
        response=session.get(item["source_url"],timeout=timeout,allow_redirects=True)
        result["http_status"]=response.status_code
        if response.status_code == 429:
            result.update(status="rate_limited",failure_reason="HTTP 429",compliance_limits=["rate_limit"],recommendation="降低频率并遵守 Retry-After")
            return result
        if response.status_code in {401,403}:
            result.update(status="login_required",failure_reason=f"HTTP {response.status_code}",compliance_limits=["access_control"],recommendation="不绕过访问控制；改用公开官方源")
            return result
        response.raise_for_status()
        content_type=response.headers.get("content-type","").lower()
        text=response.text[:2_000_000]
        lowered=text.lower()
        if any(x in lowered for x in ("captcha","recaptcha","hcaptcha","验证您是真人")):
            result.update(status="javascript_required",failure_reason="captcha or browser verification detected",compliance_limits=["captcha"],recommendation="不绕过验证码；建议人工导入")
            return result
        if any(x in lowered for x in ("subscribe to continue","sign in to continue","paywall")):
            result.update(status="paywalled",failure_reason="paywall/login text detected",compliance_limits=["paywall"],recommendation="不绕过付费墙；保留线索或人工导入")
            return result
        if "xml" in content_type or "<rss" in lowered[:1000] or "<feed" in lowered[:1000]:
            entries=len(re.findall(r"<(?:item|entry)\b",text,re.I))
            result.update(status="rss_available",crawlable=entries > 0,test_count=entries,extracted_fields=["title","original_url","published_at"])
            result["one_year_backfill"]=entries > 0 and entries >= 100
            result["recommendation"]="配置RSS适配器；历史深度不足时补充sitemap/API"
            return result
        soup=BeautifulSoup(text,"html.parser")
        alternate=soup.select_one("link[type*='rss'], link[type*='atom']")
        if alternate and alternate.get("href"):
            result["test_method"].append("rss_discovery")
            discovered=urljoin(response.url,alternate["href"])
            result["details"]["discovered_feed"]=discovered
            feed_response=session.get(discovered,timeout=timeout,allow_redirects=True)
            entries=len(re.findall(r"<(?:item|entry)\b",feed_response.text,re.I)) if feed_response.ok else 0
            if entries == 1 and re.search(r"<title[^>]*>\s*(?:<!\[CDATA\[)?\s*test\s*(?:\]\]>)?\s*</title>",feed_response.text,re.I):
                entries=0
            result.update(
                status="rss_available",crawlable=entries > 0,test_count=entries,
                extracted_fields=["title","original_url","published_at"] if entries else [],
                failure_reason=None if entries else "RSS link was advertised but returned zero parseable entries",
                recommendation=(f"优先配置并验证公开RSS：{discovered}" if entries else "保留为候选；零条结果不启用自动抓取"),
            )
            return result
        sitemap_urls=re.findall(r"(?im)^sitemap:\s*(\S+)",robots_text)
        if not sitemap_urls:
            sitemap_urls=[urljoin(response.url,"/sitemap.xml")]
        for sitemap_url in sitemap_urls[:1]:
            try:
                result["test_method"].append("sitemap_discovery")
                sitemap=session.get(sitemap_url,timeout=timeout,allow_redirects=True)
                if sitemap.ok and ("<urlset" in sitemap.text[:2000].lower() or "<sitemapindex" in sitemap.text[:2000].lower()):
                    count=len(re.findall(r"<loc>",sitemap.text,re.I))
                    result["details"]["discovered_sitemap"]=sitemap.url
                    result.update(
                        status="sitemap_available",crawlable=count > 0,test_count=count,
                        one_year_backfill=count >= 100,
                        extracted_fields=["original_url"]+(["published_at"] if "<lastmod>" in sitemap.text.lower() else []),
                        recommendation="新增合规 sitemap 适配器，并在详情页提取标题与发布日期。",
                    )
                    return result
            except requests.RequestException:
                pass
        links=[a for a in soup.select("a[href]") if len(a.get_text(" ",strip=True)) >= 8]
        dates=soup.select("time, [class*='date'], [class*='time']")
        result["test_count"]=min(len(links),200)
        if links:
            result.update(status="reachable_no_content",crawlable=False,extracted_fields=["title","original_url"]+(["published_at"] if dates else []),recommendation="页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。")
            result["one_year_backfill"]=bool(re.search(r"(archive|page=|pagination|下一页|older)",lowered))
        elif re.search(r"<script[^>]+src=",lowered):
            result.update(status="javascript_required",failure_reason="no public article links in server HTML",recommendation="寻找官方API/RSS/sitemap；不绕过验证")
        else:
            result.update(status="reachable_no_content",failure_reason="reachable but no parseable public list content",recommendation="检查官方API、RSS或sitemap")
        return result
    except requests.exceptions.SSLError as exc:
        result.update(status="certificate_error",failure_reason=str(exc)[:500],recommendation="由来源站修复证书后再启用")
    except requests.exceptions.Timeout as exc:
        result.update(status="timeout",failure_reason=str(exc)[:500],recommendation="在联网环境低频重试一次")
    except requests.RequestException as exc:
        result.update(status="parsing_failed",failure_reason=str(exc)[:500],recommendation="检查DNS、HTTPS和来源可用性")
    except Exception as exc:
        result.update(status="parsing_failed",failure_reason=f"{type(exc).__name__}: {exc}"[:500],recommendation="人工检查页面结构")
    return result


def write_reports(rows: list[dict]) -> None:
    REPORT_JSON.parent.mkdir(parents=True,exist_ok=True)
    working=sum(x["crawlable"] for x in rows)
    verified_adapters=sum(x["status"] == "adapter_working" and x["test_count"] > 0 for x in rows)
    backfillable=sum(x["one_year_backfill"] for x in rows)
    generated_at=datetime.now(timezone.utc).isoformat()
    REPORT_JSON.write_text(json.dumps({
        "generated_at":generated_at,"count":len(rows),
        "summary":{"verified_working_adapters":verified_adapters,"crawlable_capabilities":working,"one_year_backfill_capabilities":backfillable},
        "results":rows,
    },ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# 数据源扩展与能力验证报告","",f"- 测试时间：{generated_at}",f"- 测试来源：{len(rows)}",f"- 已验证可工作适配器：{verified_adapters}",f"- 可抓取能力（含待接入RSS/sitemap）：{working}",f"- 支持一年回填能力：{backfillable}","","> 本报告记录真实联网结果；零条内容不计为适配器成功，网页仅可达也不计为适配器成功。","", "| 来源 | 状态 | HTTP | 可抓取 | 一年回填 | 条数 | 失败/限制 | 推荐下一步 |","|---|---|---:|:---:|:---:|---:|---|---|"]
    for x in rows:
        failure=(x["failure_reason"] or ", ".join(x["compliance_limits"]) or "-").replace("|","/").replace("\n"," ")
        recommendation=(x["recommendation"] or "-").replace("|","/").replace("\n"," ")
        lines.append(f"| {x['source_name']} | {x['status']} | {x['http_status'] or '-'} | {'是' if x['crawlable'] else '否'} | {'是' if x['one_year_backfill'] else '否'} | {x['test_count']} | {failure[:100]} | {recommendation[:120]} |")
    REPORT_MD.write_text("\n".join(lines)+"\n",encoding="utf-8")


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--limit",type=int,default=0,help="0 means all configured sources")
    parser.add_argument("--timeout",type=int,default=8)
    parser.add_argument("--workers",type=int,default=4)
    args=parser.parse_args()
    sources=json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    if args.limit: sources=sources[:args.limit]
    rows=[]
    with ThreadPoolExecutor(max_workers=max(1,min(args.workers,4))) as pool:
        futures={pool.submit(check,item,args.timeout):item for item in sources}
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda x:x["source_name"].lower())
    write_reports(rows)
    print(json.dumps({"tested":len(rows),"crawlable":sum(x["crawlable"] for x in rows),"one_year_backfill":sum(x["one_year_backfill"] for x in rows),"report_json":str(REPORT_JSON),"report_md":str(REPORT_MD)},ensure_ascii=False))


if __name__ == "__main__":
    main()
