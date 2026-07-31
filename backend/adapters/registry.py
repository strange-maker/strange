from __future__ import annotations

from adapters.feeds import RSSAdapter
from adapters.official import HTMLListAdapter, SitemapAdapter, WorldBankDocumentsAdapter
from adapters.cscec import (
    CSCECNewsAdapter,
    CSCECOrganizationAdapter,
    CSCECPDFAnnouncementAdapter,
)


CSCEC_AUTO_NEWS_SOURCES = {
    "中国建筑官网",
    "中国建筑新闻中心",
    "中建国际新闻中心",
    "中国海外集团新闻",
    "中建一局新闻",
    "中建二局新闻",
    "中建三局新闻",
    "中建四局新闻",
    "中建五局新闻",
    "中建六局新闻",
    "中建七局新闻",
    "中建八局新闻",
    "中建新疆建工新闻",
    "中建设计研究院新闻",
    "中建西南院新闻",
    "中建西北院新闻",
    "中建安装新闻",
    "中建港航局新闻",
}


ADAPTER_CONFIGS: dict[str, dict] = {
    "中国建筑企业动态":{
        "class":CSCECNewsAdapter,
        "endpoint":"https://www.cscec.com/xwzx_new/zqydt_new/",
        "page_pattern":"https://www.cscec.com/xwzx_new/zqydt_new/index_{index}.html",
        "item_selector":".list li, .news-list li, ul li",
        "content_selector":".TRS_Editor, .article-content, article, main",
        "fetch_detail":True,
        "max_pages":50,
        "backfill_page_limit":50,
        "schedule_minutes":180,
        "initial_status":"active",
    },
    "中国建筑组织架构":{
        "class":CSCECOrganizationAdapter,
        "endpoint":"https://www.cscec.com/fzlm_new/zjwzq/",
        "schedule_minutes":1440,
        "initial_status":"active",
    },
    "中国建筑投资者服务":{
        "class":CSCECPDFAnnouncementAdapter,
        "endpoint":"https://www.cscec.com/tzzgxnew/tzgg_new/",
        "item_selector":"ul.yxj-list li",
        "fetch_detail":True,
        "recent_limit":25,
        "priority_limit":35,
        "priority_lookback_days":730,
        "backfill_batch_size":10,
        "max_pdf_bytes":15000000,
        "max_pdf_pages":100,
        "supports_backfill":True,
        "backfill_page_limit":200,
        "schedule_minutes":1440,
        "initial_status":"active",
    },
    "World Bank Projects & Procurement":{"class":WorldBankDocumentsAdapter,"endpoint":"https://search.worldbank.org/api/v3/wds","schedule_minutes":180,"max_pages":50,"supports_backfill":True,"backfill_page_limit":50},
    "Data Center Dynamics":{"class":RSSAdapter,"endpoint":"https://www.datacenterdynamics.com/en/rss/","schedule_minutes":30},
    "Data Center Knowledge":{"class":RSSAdapter,"endpoint":"https://www.datacenterknowledge.com/rss.xml","schedule_minutes":30},
    "Mexico News Daily":{"class":RSSAdapter,"endpoint":"https://mexiconewsdaily.com/feed/","schedule_minutes":30},
    "PV Tech":{"class":RSSAdapter,"endpoint":"https://www.pv-tech.org/feed/","schedule_minutes":30},
    "PV Magazine":{"class":RSSAdapter,"endpoint":"https://www.pv-magazine.com/feed/","schedule_minutes":30},
    "Energy Storage News":{"class":RSSAdapter,"endpoint":"https://www.energy-storage.news/feed/","schedule_minutes":30},
    "Offshore Energy":{"class":RSSAdapter,"endpoint":"https://www.offshore-energy.biz/feed/","schedule_minutes":30},
    "Engineering News":{"class":RSSAdapter,"endpoint":"https://www.engineeringnews.co.za/page/rss.html","schedule_minutes":30,"initial_status":"pending_adapter"},
    "Mining Weekly":{"class":RSSAdapter,"endpoint":"https://www.miningweekly.com/page/rss.html","schedule_minutes":30,"initial_status":"pending_adapter"},
    "Construction Week Saudi":{"class":RSSAdapter,"endpoint":"https://www.constructionweeksaudi.com/feed/","schedule_minutes":30,"initial_status":"blocked"},
    "Renewables Now":{"class":RSSAdapter,"endpoint":"https://renewablesnow.com/news/rss/","schedule_minutes":30,"initial_status":"pending_adapter"},
    "Vietnam Investment Review":{"class":HTMLListAdapter,"endpoint":"https://vir.com.vn/","item_selector":"a[href$='.html']","node_is_link":True,"schedule_minutes":30},
    "Asian Development Bank Projects & Tenders":{"class":HTMLListAdapter,"endpoint":"https://www.adb.org/projects/tenders","item_selector":".views-row, article","link_selector":"a","title_selector":"h2 a, h3 a, a","schedule_minutes":180,"initial_status":"blocked"},
    "AIIB Projects":{"class":HTMLListAdapter,"endpoint":"https://www.aiib.org/en/projects/list/index.html","item_selector":".project-list li, .list-news li, article","link_selector":"a","title_selector":"a","schedule_minutes":180,"initial_status":"blocked"},
    "中国一带一路网":{"class":HTMLListAdapter,"endpoint":"https://www.yidaiyilu.gov.cn/","item_selector":".news-list li, .list li, article","link_selector":"a","title_selector":"a","schedule_minutes":360,"initial_status":"pending_adapter"},
    "北极星太阳能光伏网":{"class":HTMLListAdapter,"endpoint":"https://guangfu.bjx.com.cn/","item_selector":".cc-list-content li, .list li","link_selector":"a","title_selector":"a","schedule_minutes":30,"initial_status":"pending_adapter"},
    "见道网海外项目":{"class":HTMLListAdapter,"endpoint":"https://www.seetao.com/list/220.html","item_selector":".list-item, .item, li","link_selector":"a","title_selector":"h3, h2, a","schedule_minutes":30},
    "36氪出海":{"class":SitemapAdapter,"endpoint":"https://letschuhai.com/sitemaps","include_regex":r"/(news|article|post|\d{4})","fetch_detail":True,"max_pages":25,"schedule_minutes":180},
    "Abu Dhabi Department of Energy":{"class":SitemapAdapter,"endpoint":"https://www.doe.gov.ae/sitemap.xml","include_regex":r"/(news|media|press|project)","fetch_detail":True,"max_pages":25,"schedule_minutes":360},
    "DataCentre Magazine":{"class":SitemapAdapter,"endpoint":"https://datacentremagazine.com/sitemap.xml","include_regex":r"/(news|articles|data-centres|critical-infrastructure)","fetch_detail":True,"max_pages":50,"schedule_minutes":60},
    "Delta Electronics News":{"class":SitemapAdapter,"endpoint":"https://www.deltaww.com/sitemap.xml","include_regex":r"/(news|press|event)","fetch_detail":True,"max_pages":50,"schedule_minutes":180},
    "Honeywell News":{"class":SitemapAdapter,"endpoint":"https://www.honeywell.com/sitemap.xml","include_regex":r"/(news|press|stories)","fetch_detail":True,"max_pages":50,"schedule_minutes":180},
    "IDC圈":{"class":SitemapAdapter,"endpoint":"https://www.idcquan.com/sitemap.xml","include_regex":r"/(news|article|\d{4})","fetch_detail":True,"language":"zh","max_pages":50,"schedule_minutes":60},
    "IKN Nusantara":{"class":SitemapAdapter,"endpoint":"https://ikn.go.id/sitemap.xml","include_regex":r"/(en|id)/posts/","fetch_detail":True,"max_pages":50,"schedule_minutes":360},
    "Mexico Business News":{"class":SitemapAdapter,"endpoint":"https://mexicobusiness.news/sitemap.xml","include_regex":r"/(news|article|energy|infrastructure|industry)","fetch_detail":True,"max_pages":50,"schedule_minutes":60},
    "PEA Thailand":{"class":SitemapAdapter,"endpoint":"https://www.pea.co.th/sitemap.xml","include_regex":r"/(news|project|procurement|article)","fetch_detail":True,"max_pages":25,"schedule_minutes":360},
    "Philippines Department of Energy":{"class":SitemapAdapter,"endpoint":"https://doe.gov.ph/sitemap.xml","include_regex":r"/(press|news|project|bid|procurement)","fetch_detail":True,"max_pages":25,"schedule_minutes":360},
    "QatarEnergy":{"class":SitemapAdapter,"endpoint":"https://www.qatarenergy.qa/sitemap.xml","include_regex":r"/(news|media|press|project)","fetch_detail":True,"max_pages":50,"schedule_minutes":360},
    "Rockwell Automation News":{"class":SitemapAdapter,"endpoint":"https://www.rockwellautomation.com/en-us/sitemapindex.xml","sitemap_include_regex":r"(news|press|blog|company)","include_regex":r"/(news|press|blog|company/news)","fetch_detail":True,"max_pages":50,"schedule_minutes":180},
    "Saudi PIF":{"class":SitemapAdapter,"endpoint":"https://www.pif.gov.sa/sitemap.xml","include_regex":r"/(news|press|projects|companies)","fetch_detail":True,"max_pages":50,"schedule_minutes":360},
    "Siemens Energy Press":{"class":SitemapAdapter,"endpoint":"https://www.siemens-energy.com/sitemap.xml","include_regex":r"/(press|news|stories)","fetch_detail":True,"max_pages":50,"schedule_minutes":180},
    "Siemens Press":{"class":SitemapAdapter,"endpoint":"https://press.siemens.com/global/en/sitemapindex","sitemap_include_regex":r"(press|release|news)","include_regex":r"/(pressrelease|news|feature)","fetch_detail":True,"max_pages":50,"schedule_minutes":180},
    "中国中铁新闻中心":{"class":SitemapAdapter,"endpoint":"https://www.crec.cn/sitemap.xml","include_regex":r"/(news|xwzx|article|content)","fetch_detail":True,"language":"zh","max_pages":25,"schedule_minutes":360},
    "中车国际":{"class":SitemapAdapter,"endpoint":"https://www.crrcgc.cc/sitemap.xml","include_regex":r"/(news|xwzx|article|content)","fetch_detail":True,"language":"zh","max_pages":50,"schedule_minutes":360},
    "振华重工":{"class":SitemapAdapter,"endpoint":"https://www.zpmc.com/sitemap.xml","include_regex":r"/(news|press|article|content)","fetch_detail":True,"language":"zh","max_pages":50,"schedule_minutes":360},
    "特变电工新闻":{"class":SitemapAdapter,"endpoint":"https://www.tbea.com/sitemap.xml","include_regex":r"/(news|article|content)","fetch_detail":True,"language":"zh","max_pages":50,"schedule_minutes":180},
    "良信电器":{"class":SitemapAdapter,"endpoint":"https://www.lazzen.com/sitemap.xml","include_regex":r"/(news|article|content)","fetch_detail":True,"language":"zh","max_pages":50,"schedule_minutes":180},
    "EGAT":{"class":RSSAdapter,"endpoint":"https://www.egat.co.th/home/feed/","schedule_minutes":360},
    "MIDA Malaysia":{"class":RSSAdapter,"endpoint":"https://www.mida.gov.my/feed/","schedule_minutes":360},
    "Tenaga Nasional Berhad":{"class":RSSAdapter,"endpoint":"https://www.tnb.com.my/rss/announcements","schedule_minutes":360},
    "W.Media":{"class":RSSAdapter,"endpoint":"https://w.media/feed/","schedule_minutes":60},
}


def get_adapter_definition(
    source_name: str,
    source_url: str | None = None,
    metadata: dict | None = None,
) -> dict | None:
    definition = ADAPTER_CONFIGS.get(source_name)
    if definition:
        return dict(definition)
    metadata = metadata or {}
    is_cscec_news = source_name in CSCEC_AUTO_NEWS_SOURCES
    is_cscec_official_html = (
        metadata.get("ka_focus") == "cscec"
        and metadata.get("source_type") == "official"
        and metadata.get("crawl_method") == "html"
        and ("新闻" in source_name or source_name == "中国建筑官网")
    )
    if not (is_cscec_news or is_cscec_official_html):
        return None
    return {
        "class": CSCECNewsAdapter,
        "adapter_family": "cscec_site",
        "endpoint": source_url,
        "auto_discover_news": True,
        "include_wechat_index_leads": True,
        "fetch_detail": True,
        "max_pages": 1,
        "schedule_minutes": 180,
        "initial_status": "active",
    }


def build_adapter(source_name: str, source_url: str, stored_config: dict | None = None):
    definition=get_adapter_definition(source_name,source_url)
    if not definition and (stored_config or {}).get("adapter_family") == "cscec_site":
        definition=get_adapter_definition(source_name,source_url,{"ka_focus":"cscec","source_type":"official","crawl_method":"html"})
    if not definition: raise KeyError(f"no adapter registered for {source_name}")
    config={k:v for k,v in definition.items() if k not in {"class","initial_status"}}; config.update(stored_config or {})
    return definition["class"](source_url, config)
