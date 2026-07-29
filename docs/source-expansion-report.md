# 数据源扩展与能力验证报告

- 测试时间：2026-07-28T12:37:02.231440+00:00
- 测试来源：151
- 已验证可工作适配器：25
- 可抓取能力（含待接入RSS/sitemap）：38
- 支持一年回填能力：37

> 本报告记录真实联网结果；零条内容不计为适配器成功，网页仅可达也不计为适配器成功。

| 来源 | 状态 | HTTP | 可抓取 | 一年回填 | 条数 | 失败/限制 | 推荐下一步 |
|---|---|---:|:---:|:---:|---:|---|---|
| 36氪出海 | sitemap_available | 200 | 是 | 否 | 84 | - | 新增合规 sitemap 适配器，并在详情页提取标题与发布日期。 |
| ABB News | parsing_failed | 404 | 否 | 否 | 0 | 404 Client Error: Not Found for url: https://global.abb/group/en/media/news | 检查DNS、HTTPS和来源可用性 |
| Abu Dhabi Department of Energy | adapter_working | 200 | 是 | 是 | 5 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| ADNOC | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.adnoc.ae', port=443): Max retries exceeded with url: /robots.txt (Caus | 由来源站修复证书后再启用 |
| African Development Bank Procurement | sitemap_available | 200 | 是 | 否 | 2 | - | 新增合规 sitemap 适配器，并在详情页提取标题与发布日期。 |
| African Energy | javascript_required | 200 | 否 | 否 | 0 | captcha or browser verification detected | 不绕过验证码；建议人工导入 |
| AIIB Projects | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.aiib.org', port=443): Max retries exceeded with url: /robots.txt (Caus | 由来源站修复证书后再启用 |
| Asian Development Bank Projects & Tenders | login_required | 403 | 否 | 否 | 0 | HTTP 403 | 不绕过访问控制；改用公开官方源 |
| Bangkok Post Business | sitemap_available | 200 | 是 | 否 | 12 | - | 新增合规 sitemap 适配器，并在详情页提取标题与发布日期。 |
| BNamericas | login_required | - | 否 | 否 | 0 | restricted_by_source_notes | 保持人工导入或获得明确授权后再测试 |
| BusinessWorld Philippines | javascript_required | 200 | 否 | 否 | 0 | captcha or browser verification detected | 不绕过验证码；建议人工导入 |
| Cloudscene | login_required | - | 否 | 否 | 0 | restricted_by_source_notes | 保持人工导入或获得明确授权后再测试 |
| Construction Week Middle East | parsing_failed | 405 | 否 | 否 | 0 | 405 Client Error: Not Allowed for url: https://www.constructionweekonline.com/ | 检查DNS、HTTPS和来源可用性 |
| Construction Week Saudi | parsing_failed | 405 | 否 | 否 | 0 | 405 Client Error: Not Allowed for url: https://www.constructionweeksaudi.com/ | 检查DNS、HTTPS和来源可用性 |
| Data Center Dynamics | adapter_working | 200 | 是 | 否 | 20 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| Data Center Knowledge | adapter_working | 200 | 是 | 否 | 50 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| DataCentre Magazine | adapter_working | 200 | 是 | 是 | 5 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| Delta Electronics News | adapter_working | 404 | 是 | 是 | 2 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| DEWA | login_required | 403 | 否 | 否 | 0 | HTTP 403 | 不绕过访问控制；改用公开官方源 |
| Eaton News | timeout | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.eaton.com', port=443): Read timed out. (read timeout=8) | 在联网环境低频重试一次 |
| EBRD Procurement | rss_available | 200 | 否 | 否 | 0 | RSS link was advertised but returned zero parseable entries | 保留为候选；零条结果不启用自动抓取 |
| EGAT | adapter_working | 200 | 是 | 否 | 10 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| Egypt NUCA | reachable_no_content | 200 | 否 | 是 | 29 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| Egyptian Electricity Holding Company | timeout | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.eehc.gov.eg', port=443): Read timed out. (read timeout=8) | 在联网环境低频重试一次 |
| Energy Capital & Power | rss_available | 200 | 是 | 否 | 10 | - | 优先配置并验证公开RSS：https://energycapitalpower.com/feed/ |
| Energy Storage News | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.energy-storage.news', port=443): Max retries exceeded with url: /robot | 由来源站修复证书后再启用 |
| Engineering News | parsing_failed | - | 否 | 否 | 0 | 404 Client Error: Not Found for url: https://www.engineeringnews.co.za/page/rss.html | 检查DNS、HTTPS和来源可用性 |
| ESI Africa | login_required | 403 | 否 | 否 | 0 | HTTP 403 | 不绕过访问控制；改用公开官方源 |
| Global Infrastructure Hub | javascript_required | 200 | 否 | 否 | 0 | captcha or browser verification detected | 不绕过验证码；建议人工导入 |
| Gulf Construction | javascript_required | 200 | 否 | 否 | 0 | captcha or browser verification detected | 不绕过验证码；建议人工导入 |
| Honeywell News | adapter_working | 200 | 是 | 是 | 5 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| IDC圈 | adapter_working | 200 | 是 | 是 | 5 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| IKN Nusantara | adapter_working | 200 | 是 | 是 | 5 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| Indonesia BKPM | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.investindonesia.go.id', port=443): Max retries exceeded with url: /rob | 由来源站修复证书后再启用 |
| Inter-American Development Bank Projects | login_required | 403 | 否 | 否 | 0 | HTTP 403 | 不绕过访问控制；改用公开官方源 |
| Islamic Development Bank Procurement | sitemap_available | 200 | 是 | 否 | 2 | - | 新增合规 sitemap 适配器，并在详情页提取标题与发布日期。 |
| Legrand Newsroom | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.legrand.com', port=443): Max retries exceeded with url: /robots.txt (C | 由来源站修复证书后再启用 |
| Masdar | javascript_required | 200 | 否 | 否 | 0 | captcha or browser verification detected | 不绕过验证码；建议人工导入 |
| MEA Thailand | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.mea.or.th', port=443): Max retries exceeded with url: /robots.txt (Cau | 由来源站修复证书后再启用 |
| MEED | login_required | - | 否 | 否 | 0 | restricted_by_source_notes | 保持人工导入或获得明确授权后再测试 |
| Mexico Business News | adapter_working | 200 | 是 | 是 | 5 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| Mexico News Daily | adapter_working | 200 | 是 | 否 | 10 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| Mexico SENER | sitemap_available | 200 | 是 | 否 | 3 | - | 新增合规 sitemap 适配器，并在详情页提取标题与发布日期。 |
| MIDA Malaysia | adapter_working | 200 | 是 | 否 | 10 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| Mining Weekly | parsing_failed | - | 否 | 否 | 0 | 404 Client Error: Not Found for url: https://www.miningweekly.com/page/rss.html | 检查DNS、HTTPS和来源可用性 |
| MRT Corp Malaysia | javascript_required | 200 | 否 | 否 | 0 | captcha or browser verification detected | 不绕过验证码；建议人工导入 |
| NEOM | javascript_required | 200 | 否 | 否 | 0 | captcha or browser verification detected | 不绕过验证码；建议人工导入 |
| NGCP Philippines | login_required | 403 | 否 | 否 | 0 | HTTP 403 | 不绕过访问控制；改用公开官方源 |
| Nikkei Asia | login_required | - | 否 | 否 | 0 | restricted_by_source_notes | 保持人工导入或获得明确授权后再测试 |
| NS Energy | javascript_required | 200 | 否 | 否 | 0 | captcha or browser verification detected | 不绕过验证码；建议人工导入 |
| Offshore Energy | adapter_working | 200 | 是 | 否 | 10 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| PEA Thailand | adapter_working | 200 | 是 | 是 | 4 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| Philippines Department of Energy | sitemap_available | 200 | 是 | 否 | 24 | - | 新增合规 sitemap 适配器，并在详情页提取标题与发布日期。 |
| Philippines PPP Center | login_required | 403 | 否 | 否 | 0 | HTTP 403 | 不绕过访问控制；改用公开官方源 |
| PLN Indonesia | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='web.pln.co.id', port=443): Max retries exceeded with url: /robots.txt (Cau | 由来源站修复证书后再启用 |
| Power Technology | javascript_required | 200 | 否 | 否 | 0 | captcha or browser verification detected | 不绕过验证码；建议人工导入 |
| Proyectos México | javascript_required | 200 | 否 | 否 | 0 | captcha or browser verification detected | 不绕过验证码；建议人工导入 |
| PV Magazine | adapter_working | 200 | 是 | 否 | 10 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| PV Tech | parsing_failed | - | 否 | 否 | 0 | 403 Client Error: Forbidden for url: https://www.pv-tech.org/feed/ | 检查DNS、HTTPS和来源可用性 |
| Qatar Ashghal | reachable_no_content | 200 | 否 | 是 | 98 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| QatarEnergy | adapter_working | 200 | 是 | 是 | 5 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| Renewables Now | parsing_failed | - | 否 | 否 | 0 | 404 Client Error: Not Found for url: https://renewablesnow.com/news/rss/ | 检查DNS、HTTPS和来源可用性 |
| Rockwell Automation News | sitemap_available | 200 | 是 | 是 | 204 | - | 新增合规 sitemap 适配器，并在详情页提取标题与发布日期。 |
| Saudi Arabia Railways | login_required | 401 | 否 | 否 | 0 | HTTP 401 | 不绕过访问控制；改用公开官方源 |
| Saudi Electricity Company | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.se.com.sa', port=443): Max retries exceeded with url: /robots.txt (Cau | 由来源站修复证书后再启用 |
| Saudi PIF | adapter_working | 200 | 是 | 是 | 5 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| Saudi Ports Authority Mawani | parsing_failed | 405 | 否 | 否 | 0 | 405 Client Error: Not Allowed for url: https://mawani.gov.sa/ | 检查DNS、HTTPS和来源可用性 |
| Saudi Vision 2030 | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.vision2030.gov.sa', port=443): Max retries exceeded with url: /robots. | 由来源站修复证书后再启用 |
| Saudi Water Authority | javascript_required | 200 | 否 | 否 | 0 | captcha or browser verification detected | 不绕过验证码；建议人工导入 |
| Siemens Energy Press | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.siemens-energy.com', port=443): Max retries exceeded with url: /robots | 由来源站修复证书后再启用 |
| Siemens Press | adapter_working | 200 | 是 | 是 | 5 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| Tenaga Nasional Berhad | adapter_working | 200 | 是 | 否 | 10 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| Thailand BOI | sitemap_available | 200 | 是 | 否 | 1 | - | 新增合规 sitemap 适配器，并在详情页提取标题与发布日期。 |
| The Edge Malaysia | javascript_required | 200 | 否 | 否 | 0 | captcha or browser verification detected | 不绕过验证码；建议人工导入 |
| The Investor Vietnam | javascript_required | 200 | 否 | 否 | 0 | captcha or browser verification detected | 不绕过验证码；建议人工导入 |
| The Jakarta Post Business | paywalled | 200 | 否 | 否 | 0 | paywall/login text detected | 不绕过付费墙；保留线索或人工导入 |
| UNGM | reachable_no_content | 200 | 否 | 是 | 166 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| Utilities Middle East | parsing_failed | 405 | 否 | 否 | 0 | 405 Client Error: Not Allowed for url: https://www.utilities-me.com/ | 检查DNS、HTTPS和来源可用性 |
| Vertiv News | parsing_failed | 404 | 否 | 否 | 0 | 404 Client Error: Not Found for url: https://www.vertiv.com/en-us/about/news-and-events/news-release | 检查DNS、HTTPS和来源可用性 |
| Vietnam Electricity EVN | reachable_no_content | 200 | 否 | 是 | 92 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| Vietnam Investment Review | adapter_working | 200 | 是 | 否 | 20 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| Vietnam Ministry of Planning and Investment | timeout | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.mpi.gov.vn', port=443): Read timed out. (read timeout=8) | 在联网环境低频重试一次 |
| W.Media | adapter_working | 200 | 是 | 否 | 10 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| World Bank Projects & Procurement | adapter_working | 200 | 是 | 是 | 50 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| Zawya | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.zawya.com', port=443): Max retries exceeded with url: /robots.txt (Cau | 由来源站修复证书后再启用 |
| 一带一路金融工程 | manual_recommended | - | 否 | 否 | 0 | manual_only | 保持人工导入或获得明确授权后再测试 |
| 中东北非工程基建 | manual_recommended | - | 否 | 否 | 0 | manual_only | 保持人工导入或获得明确授权后再测试 |
| 中交集团新闻中心 | parsing_failed | 521 | 否 | 否 | 0 | 521 Server Error:  for url: https://www.ccccltd.cn/ | 检查DNS、HTTPS和来源可用性 |
| 中关村储能产业技术联盟 CNESA | reachable_no_content | 200 | 否 | 是 | 54 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| 中国一带一路网 | parsing_failed | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.yidaiyilu.gov.cn', port=443): Max retries exceeded with url: /robots.t | 检查DNS、HTTPS和来源可用性 |
| 中国一带一路网公众号 | manual_recommended | - | 否 | 否 | 0 | manual_only | 保持人工导入或获得明确授权后再测试 |
| 中国中铁新闻中心 | sitemap_available | 200 | 是 | 否 | 18 | - | 新增合规 sitemap 适配器，并在详情页提取标题与发布日期。 |
| 中国光伏行业协会 | reachable_no_content | 200 | 否 | 是 | 177 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| 中国土木 | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.ccecc.com.cn', port=443): Max retries exceeded with url: /robots.txt ( | 由来源站修复证书后再启用 |
| 中国对外承包工程商会 | reachable_no_content | 200 | 否 | 否 | 0 | reachable but no parseable public list content | 检查官方API、RSS或sitemap |
| 中国建筑新闻中心 | reachable_no_content | 200 | 否 | 否 | 1 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| 中国机电产品进出口商会 | reachable_no_content | 200 | 否 | 是 | 200 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| 中国港湾 | reachable_no_content | 200 | 否 | 否 | 130 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| 中国电力企业联合会 | robots_blocked | 200 | 否 | 否 | 0 | robots.txt disallows this URL | 不自动抓取；寻找官方API/RSS或人工导入 |
| 中国电工 | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.cneec.com.cn', port=443): Max retries exceeded with url: /robots.txt ( | 由来源站修复证书后再启用 |
| 中国电建新闻中心 | parsing_failed | 404 | 否 | 否 | 0 | 404 Client Error: Not Found for url: https://www.powerchina.cn/col/col7440/index.html | 检查DNS、HTTPS和来源可用性 |
| 中国电气装备 | reachable_no_content | 200 | 否 | 是 | 49 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| 中国能建新闻中心 | javascript_required | 200 | 否 | 否 | 0 | no public article links in server HTML | 寻找官方API/RSS/sitemap；不绕过验证 |
| 中国西电 | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.xd.com.cn', port=443): Max retries exceeded with url: /robots.txt (Cau | 由来源站修复证书后再启用 |
| 中国贸促会 | reachable_no_content | 200 | 否 | 是 | 200 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| 中国路桥 | reachable_no_content | 200 | 否 | 是 | 107 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| 中国铁建新闻中心 | reachable_no_content | 200 | 否 | 是 | 105 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| 中工国际 | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.camce.com.cn', port=443): Max retries exceeded with url: /robots.txt ( | 由来源站修复证书后再启用 |
| 中建国际新闻中心 | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.csci.com.hk', port=443): Max retries exceeded with url: /robots.txt (C | 由来源站修复证书后再启用 |
| 中海外 | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.covec.com', port=443): Max retries exceeded with url: /robots.txt (Cau | 由来源站修复证书后再启用 |
| 中电工程 | reachable_no_content | 200 | 否 | 是 | 60 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| 中航国际 | reachable_no_content | 200 | 否 | 是 | 14 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| 中车国际 | sitemap_available | 200 | 是 | 是 | 185 | - | 新增合规 sitemap 适配器，并在详情页提取标题与发布日期。 |
| 今日头条 | javascript_required | 200 | 否 | 否 | 0 | no public article links in server HTML | 寻找官方API/RSS/sitemap；不绕过验证 |
| 保利科技 | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.polytechnologiesinc.com', port=443): Max retries exceeded with url: /r | 由来源站修复证书后再启用 |
| 储能见闻 | manual_recommended | - | 否 | 否 | 0 | manual_only | 保持人工导入或获得明确授权后再测试 |
| 全球光伏 | manual_recommended | - | 否 | 否 | 0 | manual_only | 保持人工导入或获得明确授权后再测试 |
| 出海内参 | manual_recommended | - | 否 | 否 | 0 | manual_only | 保持人工导入或获得明确授权后再测试 |
| 北极星太阳能光伏网 | javascript_required | 200 | 否 | 否 | 0 | captcha or browser verification detected | 不绕过验证码；建议人工导入 |
| 发现报告 | sitemap_available | 200 | 是 | 否 | 7 | - | 新增合规 sitemap 适配器，并在详情页提取标题与发布日期。 |
| 哈尔滨电气 | reachable_no_content | 200 | 否 | 是 | 191 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| 哈电国际 | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.hei.com.cn', port=443): Max retries exceeded with url: /robots.txt (Ca | 由来源站修复证书后再启用 |
| 商务部对外投资和经济合作司 | reachable_no_content | 200 | 否 | 否 | 41 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| 国机集团新闻中心 | reachable_no_content | 200 | 否 | 是 | 200 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| 国资委央企动态 | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.sasac.gov.cn', port=443): Max retries exceeded with url: /robots.txt ( | 由来源站修复证书后再启用 |
| 国际工程与海外项目 | manual_recommended | - | 否 | 否 | 0 | manual_only | 保持人工导入或获得明确授权后再测试 |
| 地方贸促会与商务厅 | manual_recommended | - | 否 | 否 | 0 | manual_only | 保持人工导入或获得明确授权后再测试 |
| 山东电工电气 | parsing_failed | - | 否 | 否 | 0 | ('Connection aborted.', ConnectionAbortedError(10053, '你的主机中的软件中止了一个已建立的连接。', None, 10053, None)) | 检查DNS、HTTPS和来源可用性 |
| 山东电建三公司 | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.sepco3.com', port=443): Max retries exceeded with url: /robots.txt (Ca | 由来源站修复证书后再启用 |
| 巨潮资讯 | reachable_no_content | 200 | 否 | 是 | 19 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| 平高电气 | sitemap_available | 200 | 否 | 否 | 0 | - | 新增合规 sitemap 适配器，并在详情页提取标题与发布日期。 |
| 平高电气竞品观察 | sitemap_available | 200 | 否 | 否 | 0 | - | 新增合规 sitemap 适配器，并在详情页提取标题与发布日期。 |
| 振华重工 | adapter_working | 200 | 是 | 是 | 5 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| 格隆汇 | reachable_no_content | 200 | 否 | 是 | 64 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| 正泰新闻 | login_required | 403 | 否 | 否 | 0 | HTTP 403 | 不绕过访问控制；改用公开官方源 |
| 海外工程那些事儿 | manual_recommended | - | 否 | 否 | 0 | manual_only | 保持人工导入或获得明确授权后再测试 |
| 海外项目甲方信息库 | manual_recommended | - | 否 | 否 | 0 | manual_only | 保持人工导入或获得明确授权后再测试 |
| 特变电工新闻 | sitemap_available | 200 | 是 | 是 | 818 | - | 新增合规 sitemap 适配器，并在详情页提取标题与发布日期。 |
| 电子制造出海资讯 | manual_recommended | - | 否 | 否 | 0 | manual_only | 保持人工导入或获得明确授权后再测试 |
| 界面新闻 | reachable_no_content | 200 | 否 | 是 | 117 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| 良信电器 | adapter_working | 200 | 是 | 是 | 1 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| 苏美达 | reachable_no_content | 200 | 否 | 是 | 137 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| 葛洲坝集团 | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.cggc.ceec.net.cn', port=443): Max retries exceeded with url: /robots.t | 由来源站修复证书后再启用 |
| 见道网海外项目 | adapter_working | 200 | 是 | 否 | 11 | - | 保持低频抓取并持续监控字段完整率；回填能力以适配器分页配置为准。 |
| 许继电气 | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.xjgc.com', port=443): Max retries exceeded with url: /robots.txt (Caus | 由来源站修复证书后再启用 |
| 许继电气竞品观察 | certificate_error | - | 否 | 否 | 0 | HTTPSConnectionPool(host='www.xjgc.com', port=443): Max retries exceeded with url: /robots.txt (Caus | 由来源站修复证书后再启用 |
| 财联社 | reachable_no_content | 200 | 否 | 是 | 103 | - | 页面可达且存在候选链接；需新增并真实验证站点专用选择器后才能标记可抓取。 |
| 走出去情报 | manual_recommended | - | 否 | 否 | 0 | manual_only | 保持人工导入或获得明确授权后再测试 |
| 阿中产业研究院 | manual_recommended | - | 否 | 否 | 0 | manual_only | 保持人工导入或获得明确授权后再测试 |
| 马来西亚建筑通 | manual_recommended | - | 否 | 否 | 0 | manual_only | 保持人工导入或获得明确授权后再测试 |
| 驻外经商机构名录 | parsing_failed | 404 | 否 | 否 | 0 | 404 Client Error: Not Found for url: http://www.mofcom.gov.cn/mofcom/guobie.shtml | 检查DNS、HTTPS和来源可用性 |
