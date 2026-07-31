# 中国建筑（中建）KA 组织与领导动态监测

本功能在现有“施耐德电气海外销售情报工作台”上扩展，不引入新的演示数据链路。它把中建组织主数据、官方来源、上市披露、页面快照、组织差异和领导任免事件放到同一套可追溯模型中。

## 已实现范围

- 中建组织主数据：`backend/data/cscec_entities.yaml`
- 新增 28 个 `ka_focus=cscec` 来源：`public/sources.yaml`
- 新增数据库迁移：`backend/alembic/versions/0003_cscec_monitoring.py`
- 新增中建专用适配器：`CSCECNewsAdapter`、`CSCECOrganizationAdapter`
- 新增 Celery 任务：`tasks.sync_cscec_entities`
- 新增 API：`/api/ka/cscec/*`、`/api/admin/crawl/cscec/*`
- 新增前端页面：侧边栏“中建KA动态”

## 关键约束

- `中建港航局`、`中建筑港`、`中建港务` 分别建模，不做模糊合并。
- `远东环球` 作为中国建筑兴业历史别名保留，状态为 `renamed`。
- 未发现独立官网的海外实体保留 `official_url: null`，不猜测域名。
- 公众号来源固定为 `wechat_manual + manual_import`，永不进入自动调度。
- 页面差异只进入待核验，不自动写成确定事实。
- 出席会议、调研、访问等领导活动不会被误判为任免。

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
- 管理员点击“同步组织架构”后，Worker 日志出现 `tasks.sync_cscec_entities`。
- 管理员点击“抓取中建来源”后，API 返回 HTTP 202。
- 同一时间重复点击“抓取中建来源”，应返回 HTTP 409。

## 适配器状态

当前只有“中国建筑企业动态”和“中国建筑组织架构”注册了中建专用适配器，但默认仍标记为 `pending_adapter`，等待真实网络验证后再启用自动调度。其他新增官方入口已预留来源配置和实体映射，后续逐个验证选择器后再转为 `active`。
