# 最近一年海外销售情报平台实施报告

## 完成范围

### P0：年度数据、回填与事件去重

- 最近 365 天成为资讯、机会、政策、KA 与 Dashboard 的默认查询区间。
- 无可核验发布日期的内容标记为 `date_unverified`，不计入年度统计。
- 新增 Canonical Project / Canonical Event / Event Source，按事件级统计并保留全部来源证据。
- 同一中英文项目、授标/中标/签约等同义事件通过标准化指纹归并。
- 新增分页回填、游标、检查点、暂停、继续、重试、取消与失败记录。
- 新增兼容性 Alembic revision `0002_year_intelligence_platform`，既有数据不删除、不重建。

### P1：机会、政策与 KA

- 国家机会和区域机会合并到同一页面与接口；旧路径自动跳转。
- Dashboard 国家热度图改为横向 Top 10 / Top 20 / 全部，并支持点击筛选。
- 新增 24 类销售情报分类和结构化政策维度。
- 政策页直接展示发布国、受影响国家、发布机构、税率、投资门槛、外资比例、本地化、采购比例、标准认证和销售影响。
- 新增 KA 业务组、实体关系、强/中/弱别名、多候选与领导人公开职业动态。
- “中国电工”等歧义词进入多 KA 候选和人工审核，不自动当作唯一实体。

### P2：批量抓取与来源扩展

- 管理员可创建“一键抓取全部可运行来源”批次。
- Celery 负责队列、重试、进度和取消；浏览器不直接循环调用来源。
- 同一时间只允许一个活动全量批次；重复提交返回冲突。
- `manual_only`、`blocked`、禁用、暂停和待适配来源不会自动执行。
- 数据源列表移除逐行“立即抓取”，增加批次页与批次详情。
- 对 151 个来源执行真实联网能力检查，只有非零真实结果才标记 `adapter_working`。

## 数据库变更

新增或扩展的核心表：

- `canonical_projects`
- `canonical_events`
- `event_sources`
- `policy_intelligence`
- `ka_entities`
- `ka_entity_relations`
- `ka_leader_events`
- `crawl_batches`
- `crawl_batch_items`
- `source_capability_checks`
- `backfill_runs`
- `backfill_checkpoints`

生产发布前先备份 PostgreSQL，然后由 API pre-deploy 执行：

```bash
alembic -c alembic.ini upgrade head
```

确认 `0002_year_intelligence_platform` 完成后，再部署同版本 Worker。

## 真实验证结果

执行结果：

- 后端：`33 passed`
- 前端功能测试：`7 passed`
- ESLint：通过
- Cloudflare 静态生产构建：通过
- Sites/vinext 构建：通过并正常以退出码 0 结束
- 真实来源检查：151 个来源
- 已验证可工作适配器：25
- 可抓取候选能力（含尚待接入 RSS/Sitemap）：38
- 声明具备一年回填能力：37

已验证适配器包括 World Bank、Abu Dhabi Department of Energy、QatarEnergy、Saudi PIF、EGAT、MIDA、Tenaga Nasional Berhad、PEA、IKN Nusantara、Data Center Dynamics、Data Center Knowledge、DataCentre Magazine、W.Media、PV Magazine、Offshore Energy、Vietnam Investment Review、Mexico News Daily、Mexico Business News、Siemens Press、Honeywell、Delta Electronics、IDC圈、振华重工、良信电器和见道网海外项目。

完整逐来源证据与失败原因：

- `docs/source-expansion-report.md`
- `docs/source-expansion-report.json`

最终状态分布：

- `adapter_working`: 25
- `reachable_no_content`: 24
- `certificate_error`: 24
- `javascript_required`: 16
- `parsing_failed`: 15
- `sitemap_available`: 14
- `manual_recommended`: 14
- `login_required`: 12
- `timeout`: 3
- `rss_available`: 2
- `paywalled`: 1
- `robots_blocked`: 1

系统不绕过登录、验证码、付费墙或 robots 限制；这些来源保留真实失败原因。

## 主要修改文件

- 数据模型与迁移：`backend/models.py`、`backend/alembic/versions/0002_year_intelligence_platform.py`
- 事件、政策与 KA：`backend/intelligence.py`、`backend/ingestion.py`、`backend/ka_mappings.json`
- API：`backend/api.py`、`backend/schemas.py`
- Worker 与回填：`backend/tasks.py`、`backend/celery_app.py`
- 来源适配：`backend/adapters/base.py`、`backend/adapters/official.py`、`backend/adapters/registry.py`
- 来源实测：`backend/source_capability_check.py`
- 前端：`app/page.tsx`、`app/globals.css`、`app/country/page.tsx`、`app/region/page.tsx`
- 构建：`next.config.ts`、`package.json`、`scripts/vinext-sites-build.mjs`
- 测试：`backend/tests/test_year_platform.py`、`backend/tests/test_ingestion.py`、`backend/tests/test_migration.py`、`tests/rendered-html.test.mjs`
- 部署：`RAILWAY_DEPLOYMENT.md`

## 尚需外部环境执行

- 本地环境不能代替 Railway 生产 PostgreSQL 执行真实回填；部署迁移后由管理员在“历史回填”页逐来源创建任务。
- 本地修改未自动写入用户的 GitHub、Railway 或 Cloudflare Pages。必须将提交推送到 GitHub，确认 API migration 成功，再部署 Worker 和重建 Cloudflare 前端。
- 未创建 Scheduler 时只能手动创建全量抓取批次；不会自动按周期抓取。
- Sites 的源码提交已在本地生成，但向内部 Sites 源码仓库推送时网络不可达，因此没有保存或发布新的 Sites 版本。
