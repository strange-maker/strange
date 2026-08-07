# 中国建筑（中建）KA 组织与领导动态监测

本功能在现有“施耐德电气海外销售情报工作台”上扩展，不引入新的演示数据链路。它把中建组织主数据、官方来源、上市披露、销售相关合作、组织变化和领导公开活动放到同一套可追溯模型中。

## 已实现范围

- 中建组织主数据：`backend/data/cscec_entities.yaml`
- 新增 28 个 `ka_focus=cscec` 来源：`public/sources.yaml`
- 新增数据库迁移：`backend/alembic/versions/0003_cscec_monitoring.py`
- 新增中建专用适配器：`CSCECNewsAdapter`、`CSCECOrganizationAdapter`
- 新增 Celery 任务：`tasks.sync_cscec_entities`
- 新增 API：`/api/ka/cscec/*`、`/api/admin/crawl/cscec/*`
- 新增前端页面：侧边栏“中建KA动态”
- 新增销售情报评分与可解释字段：`backend/sales_intelligence.py`
- 新增 Schinza 脱敏导出解析与批量导入：`backend/schinza_import.py`
- 当前数据库迁移 head：`0006_sales_intel_import`

## 关键约束

- `中建港航局`、`中建筑港`、`中建港务` 分别建模，不做模糊合并。
- `远东环球` 作为中国建筑兴业历史别名保留，状态为 `renamed`。
- 未发现独立官网的海外实体保留 `official_url: null`，不猜测域名。
- 公众号来源固定为 `wechat_manual + manual_import`，永不进入自动调度。
- 页面差异只进入待核验，不自动写成确定事实。
- 出席会议、调研、访问等领导活动不会被误判为任免。
- 海外项目优先排序，但境内战略合作仍完整保留。
- 0–29 分的内部例会、程序性资料和无业务信号记录不进入中建销售页。
- 中建页隐藏“页面差异”和“人工审核”控件，但后台审核与审计数据仍保留。
- 公众号只能通过本机 Schinza 脱敏导出或单篇人工导入进入系统，固定为低可信线索。

## 页面信息结构

### 资讯时间线

- 只展示销售相关性不低于 30 分的记录。
- 默认“海外优先 · 销售价值”排序，也可切换为“海外优先 · 最新发布”。
- 展示中建主体、外部合作方、国家/地区、行业、项目阶段、产品机会、销售机会与建议动作。
- 高价值为 70–100，中价值为 50–69，低价值为 30–49。
- 标题采用正文证据中的主体、合作方、动作和项目，不把“会议”升级为“签约”，也不把“拟合作”升级为“中标”。

### 领导动态

- “人事变化”只包含明确任命、辞任、退休、免职、调任、兼任或董事会变动。
- “高价值业务活动”展示与政府、业主、合作伙伴的会见、调研、签约和战略活动。
- 业务活动不会推断为领导任免，卡片显示销售影响、建议动作和原始证据。

### 组织变化

- 标题必须包含新设、撤并、调整、区域或行业关键词，不使用“公司 → 同一公司”作为标题。
- 实体确有变化时展示“调整前 → 调整后”。
- 展示区域/行业、销售影响、建议联系人、来源数和人工确认状态。

## Schinza 批量导入

1. 只在获得授权的本机运行 Schinza，并导出不含账号凭证的 JSON/CSV。
2. 工作台“数据源管理”点击“Schinza 批量导入”。
3. 选择已配置的 `wechat_manual / manual_import / manual_only` 来源和本机文件。
4. 检查预览后确认导入；重复文件按 SHA-256 幂等返回。
5. 文章按正文实体路由至 `ka_dynamic`、`competitor_dynamic`、`chamber_association`。

禁止上传或保存 `uin`、`key`、`pass_ticket`、`appmsg_token`、`wxtoken`、Cookie、证书或私钥。Railway、Celery 和前端构建均不需要微信凭证环境变量。

## 生产上线步骤

1. 上传代码到 GitHub 主分支。
2. 在 Railway 重新部署 API，pre-deploy command 保持：

```bash
alembic -c alembic.ini upgrade head
```

3. 确认 `/health/ready` 返回 `database=ok` 和 `redis=ok`。
4. 重新部署 Worker：

```bash
celery -A celery_app.celery worker --loglevel=INFO --concurrency=4
```

5. 如已创建 Scheduler，重新部署并只保留 1 个实例：

```bash
celery -A celery_app.celery beat --loglevel=INFO
```

6. 在 Cloudflare Pages 重新部署前端：

```text
Build command: npm run build:cloudflare
Build output directory: out
NEXT_PUBLIC_API_BASE_URL=https://你的Railway API域名
```

7. API 服务的 `ALLOWED_ORIGINS` 要包含 Cloudflare Pages 正式域名。

## 验证清单

- 登录后侧边栏可看到“中建KA动态”。
- 页面顶部“组织实体”数量大于 80。
- 数据源管理中能看到“中国建筑公众号”，状态为 `manual_only`。
- 数据源管理中能打开“Schinza 批量导入”，预览和确认是两个独立步骤。
- 中建资讯默认海外优先，并显示销售分、国家/地区、合作方和建议动作。
- 领导动态分为“人事变化”和“高价值业务活动”。
- 组织变化不再出现“同一公司 → 同一公司”的无意义标题。
- 管理员点击“同步组织架构”后，Worker 日志出现 `tasks.sync_cscec_entities`。
- 管理员点击“抓取中建来源”后，API 返回 HTTP 202。
- 同一时间重复点击“抓取中建来源”，应返回 HTTP 409。

## 适配器状态

中建专用来源必须经过真实网络和选择器验证后才可转为 `active`；待适配、受限和人工来源不会伪装成可自动运行。公众号始终保持 `manual_only`，不会因为批量导入功能而进入 Worker 或 Scheduler 的自动抓取队列。
