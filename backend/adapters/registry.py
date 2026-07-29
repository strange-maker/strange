from __future__ import annotations

from adapters.feeds import RSSAdapter
from adapters.official import HTMLListAdapter, SitemapAdapter, WorldBankDocumentsAdapter


ADAPTER_CONFIGS: dict[str, dict] = {
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


def build_adapter(source_name: str, source_url: str, stored_config: dict | None = None):
    definition=ADAPTER_CONFIGS.get(source_name)
    if not definition: raise KeyError(f"no adapter registered for {source_name}")
    config={k:v for k,v in definition.items() if k not in {"class","initial_status"}}; config.update(stored_config or {})
    return definition["class"](source_url, config)
