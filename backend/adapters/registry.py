from __future__ import annotations

from adapters.feeds import RSSAdapter
from adapters.official import HTMLListAdapter, WorldBankDocumentsAdapter


ADAPTER_CONFIGS: dict[str, dict] = {
    "World Bank Projects & Procurement":{"class":WorldBankDocumentsAdapter,"endpoint":"https://search.worldbank.org/api/v3/wds","schedule_minutes":180},
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
}


def build_adapter(source_name: str, source_url: str, stored_config: dict | None = None):
    definition=ADAPTER_CONFIGS.get(source_name)
    if not definition: raise KeyError(f"no adapter registered for {source_name}")
    config={k:v for k,v in definition.items() if k not in {"class","initial_status"}}; config.update(stored_config or {})
    return definition["class"](source_url, config)
