# Railway 生产部署手册

本文对应当前仓库的生产组合：前端托管平台 + Railway FastAPI + Railway Celery Worker + Railway Celery Beat + Railway PostgreSQL + Railway Redis。

> 当前仓库已完成部署配置和本地验证，但尚未连接你的 GitHub 或 Railway 账户，也没有生成线上 API 域名。完成本文中的网页操作后，才算真正上线。

## 1. 部署结构

Railway 项目内创建五个服务：

| 服务名 | 类型 | 对外域名 | 配置文件 |
| --- | --- | --- | --- |
| `Postgres` | Railway PostgreSQL | 否 | Railway 模板 |
| `Redis` | Railway Redis | 否 | Railway 模板 |
| `API` | 本仓库 Dockerfile | 是 | `/railway.toml` |
| `Worker` | 本仓库 Dockerfile | 否 | `/railway.worker.toml` |
| `Scheduler` | 本仓库 Dockerfile | 否 | `/railway.scheduler.toml` |

三个应用服务的 **Root Directory 均为 `/`**。不要设置为 `/backend`：`backend/Dockerfile` 的构建上下文还需要复制仓库根目录下的 `public/sources.yaml`。

Railway 的 Config File 路径不跟随 Root Directory，必须按上表填写从仓库根开始的绝对路径。配置文件已指定 `backend/Dockerfile`，无需在网页中重复覆盖 Dockerfile Path。

## 2. 上传到私有 GitHub 仓库

1. 登录 GitHub，右上角 `+` → `New repository`。
2. 填写仓库名，Visibility 选择 `Private`，不要勾选自动创建 README、`.gitignore` 或 License。
3. 在本项目根目录确认 `.env`、`.env.local`、数据库文件和 `work/` 没有进入提交：

   ```powershell
   git status --short
   git check-ignore .env backend/.env sales_intelligence.db
   ```

4. 提交并推送。将下面地址替换为你刚创建的私有仓库地址：

   ```powershell
   git add -A
   git commit -m "Prepare Railway production deployment"
   git branch -M main
   git remote add origin https://github.com/<组织或用户名>/<仓库名>.git
   git push -u origin main
   ```

5. Railway 首次选择私有仓库时，按提示安装/授权 Railway GitHub App，只授权这个仓库即可。

不要提交真实的 `JWT_SECRET`、数据库密码、Redis URL、管理员密码或 `OPENAI_API_KEY`。仓库内的 `railway.env.example` 只有变量模板。

## 3. 创建 PostgreSQL 和 Redis

1. Railway Dashboard → `New Project` → `Empty Project`。
2. 项目画布点击 `+ New` → `Database` → `Add PostgreSQL`，将服务准确命名为 `Postgres`。
3. 再次点击 `+ New` → `Database` → `Add Redis`，将服务准确命名为 `Redis`。
4. 等待两个数据库服务变为 Active。

使用准确名称是为了让以下引用生效：

```dotenv
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
```

应用服务通过 Railway 私有网络访问数据库，不要改用 `DATABASE_PUBLIC_URL`。生产环境应在 Railway 中配置数据库备份/恢复策略。

## 4. 配置共享环境变量

进入 Project Settings → Shared Variables，创建以下变量，并共享给 `API`、`Worker`、`Scheduler`。也可以在每个服务的 Variables → Raw Editor 中分别粘贴。

```dotenv
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
JWT_SECRET=<至少64位、不可预测的随机字符串>
ALLOWED_ORIGINS=https://你的前端真实域名
CRAWL_USER_AGENT=Schneider-Sales-Intelligence/1.0 contact=<合规联系邮箱>
ENVIRONMENT=production
FORWARDED_ALLOW_IPS=*
TZ=UTC
ACCESS_TOKEN_MINUTES=15
REFRESH_TOKEN_DAYS=14
CRAWL_TIMEOUT_SECONDS=30
CRAWL_GLOBAL_CONCURRENCY=4
CRAWL_DOMAIN_RATE_SECONDS=2
MAX_CONSECUTIVE_FAILURES=5
SEED_DEMO_DATA=false
ENABLE_INLINE_SCHEDULER=false
OPENAI_MODEL=gpt-4.1-mini
```

`ALLOWED_ORIGINS` 支持多个明确域名，用英文逗号分隔，例如：

```dotenv
ALLOWED_ORIGINS=https://sales.example.com,https://sales-staging.example.com
```

生产环境不能写 `*`。域名只写 origin，不要带路径、查询参数或末尾 `/`。

用 PowerShell 生成强 `JWT_SECRET`：

```powershell
$jwtBytes = New-Object byte[] 64
[Security.Cryptography.RandomNumberGenerator]::Fill($jwtBytes)
[Convert]::ToBase64String($jwtBytes)
```

生成后粘贴到 Railway，并在变量右侧菜单选择 `Seal`。三个服务必须使用同一个 `JWT_SECRET`。

`OPENAI_API_KEY` 是可选项；不创建该变量也能启动，系统会继续使用规则摘要。`PORT` 由 Railway 自动注入，不要手工固定。`NEXT_PUBLIC_API_BASE_URL` 只属于前端构建环境，不能加到这三个后端服务中。

## 5. 创建 API 服务

1. 项目画布点击 `+ New` → `GitHub Repo`，选择私有仓库和 `main` 分支。
2. 将服务重命名为 `API`。
3. Settings → Source：确认连接的是当前仓库和 `main`。
4. Settings → Build：
   - Root Directory：`/`
   - Config File：`/railway.toml`
   - 不要在网页中设置相互冲突的 Dockerfile/Start Command；代码配置优先于网页值。
5. Variables：确认第 4 节全部变量已关联。
6. Settings → Deploy → Serverless/App Sleeping：关闭，API 需要持续在线。
7. Settings → Scale：首版保持一个区域、一个副本。
8. 部署。配置会先执行：

   ```bash
   alembic -c alembic.ini upgrade head
   ```

   迁移成功后启动：

   ```bash
   uvicorn api:app --host 0.0.0.0 --port $PORT --proxy-headers
   ```

   实际配置额外传入 `--forwarded-allow-ips`，并用 shell 包裹以展开 Railway 的 `$PORT`。应用只监听 `0.0.0.0`，由 Railway 终止 TLS 并转发 `X-Forwarded-*`，因此 HTTPS scheme 和客户端 IP 能由 Uvicorn 正确识别。

9. 部署日志中应看到 Alembic 升级成功以及 Uvicorn 启动。若 pre-deploy 失败，Railway 不会把新版本切换为 Active。

## 6. 生成 API Public Domain

1. 打开 `API` 服务 → Settings → Networking。
2. 在 Public Networking 下点击 `Generate Domain`。
3. 等 Railway 检测到 `$PORT` 后，复制完整 HTTPS 地址，例如：

   ```text
   https://schneider-intel-api-production.up.railway.app
   ```

4. 打开：

   ```text
   https://<API域名>/health/live
   https://<API域名>/health/ready
   https://<API域名>/docs
   ```

只给 API 生成公网域名；Worker、Scheduler、Postgres 和 Redis 不需要 HTTP 公网域名。

## 7. 创建 Worker 服务

1. `+ New` → `GitHub Repo`，再次选择同一仓库和 `main`。
2. 重命名为 `Worker`。
3. Settings：Root Directory=`/`，Config File=`/railway.worker.toml`。
4. Variables：关联第 4 节全部共享变量。
5. Settings → Deploy → Serverless/App Sleeping：关闭。
6. Scale 保持一个副本；首版 `--concurrency=4` 已提供进程内并发。
7. 不生成 Public Domain。
8. 部署并确认准确启动命令：

   ```bash
   celery -A celery_app.celery worker --loglevel=INFO --concurrency=4
   ```

日志应包含 Celery worker `ready`。任务到达时会记录 `crawl task received`，结束时记录 `crawl run finished`；失败会显示重试次数和原因。

## 8. 创建且只创建一个 Scheduler

1. `+ New` → `GitHub Repo`，再次选择同一仓库和 `main`。
2. 重命名为 `Scheduler`。
3. Settings：Root Directory=`/`，Config File=`/railway.scheduler.toml`。
4. Variables：关联第 4 节全部共享变量。
5. Settings → Deploy → Serverless/App Sleeping：关闭。
6. Settings → Scale：只选择一个区域，副本数严格设为 `1`，不要启用多区域副本。
7. 不生成 Public Domain。
8. 部署并确认准确启动命令：

   ```bash
   celery -A celery_app.celery beat --loglevel=INFO
   ```

`railway.scheduler.toml` 将部署重叠时间设为 0，代码还通过 Redis 锁 `scheduler:dispatch-due-sources` 做第二层单例保护。即使部署切换时发生瞬时并发，同一分钟也只有一个调度分发器入队。

Scheduler 每分钟只查询满足以下全部条件的来源：`enabled=true`、`adapter_status=active`、已到 `next_run_at`、非 `manual_import`、非 `wechat_manual`。Worker 在执行前会再次检查同样的关键条件，所以公众号 `manual_only` 永远不会进入自动抓取。

## 9. 数据库迁移

API 每次部署前自动运行：

```bash
alembic -c alembic.ini upgrade head
```

Alembic 只执行尚未应用的 revision；重启或再次执行 `upgrade head` 不会清空表或重载演示数据。生产启动也不会调用 `create_all`，`SEED_DEMO_DATA=true` 会直接拒绝启动。

首次部署或排障时，可安装 Railway CLI，登录并链接项目，然后连接 API 容器：

```powershell
railway login
railway link
railway ssh --service API
```

进入容器后执行：

```bash
alembic -c alembic.ini current
alembic -c alembic.ini upgrade head
```

如不想手输 SSH 参数，可在 Railway 项目画布右键 `API` → `Copy SSH Command`。对于包含 schema 变更的发布，先确认 API 的 pre-deploy 迁移成功，再部署/重启 Worker 和 Scheduler，避免后台进程先使用新代码访问旧 schema。

## 10. 创建首个管理员

仓库没有默认管理员、默认密码或后门账号。先确认 API 已完成迁移，再 SSH 到 API 服务：

```powershell
railway ssh --service API
```

推荐让程序生成强密码并只显示一次：

```bash
python cli.py bootstrap-admin --email admin@example.com --name "系统管理员" --generate-password
```

立即把输出密码保存到企业密码管理器。命令会检查系统中是否已有管理员；已有时拒绝再次执行，不会覆盖账号或密码，并写入 `bootstrap.admin_created` 审计日志。

也可交互输入密码，不经过命令行参数或日志：

```bash
python cli.py bootstrap-admin --email admin@example.com --name "系统管理员"
```

若终端不支持交互输入，可临时创建并 Seal 一个 `BOOTSTRAP_ADMIN_PASSWORD` 服务变量，重新部署 API 后执行：

```bash
python cli.py bootstrap-admin --email admin@example.com --name "系统管理员" --password-env BOOTSTRAP_ADMIN_PASSWORD
```

成功后立即从 Railway 删除该临时变量并重新部署 API。不得把管理员密码写进 Git、Dockerfile、Railway 配置文件或聊天记录。

## 11. 把 API 地址写入前端

在前端托管平台的 **构建环境变量** 中设置：

```dotenv
NEXT_PUBLIC_API_BASE_URL=https://<API生成域名>
```

变量值不要带末尾 `/`。保存后必须重新构建/部署前端，因为 `NEXT_PUBLIC_*` 在构建时嵌入浏览器包。

同时回到三个 Railway 应用服务，确保：

```dotenv
ALLOWED_ORIGINS=https://<前端真实域名>
```

若有多个前端域名，用英文逗号分隔。当前前端若仍是私有预览站点，只有有权访问该站点的用户能使用；正式 KA 用户访问前应完成对应前端平台的发布与访问控制配置。

前端使用浏览器 `Intl.DateTimeFormat` 展示时间，因此会按用户设备时区显示；手工导入的 `datetime-local` 会在浏览器中转换为 UTC ISO，后端所有入库时间使用 UTC。Celery Beat 也固定使用 UTC。

## 12. 上线验证

### 12.1 健康检查

```powershell
curl.exe -i https://<API域名>/health/live
curl.exe -i https://<API域名>/health/ready
curl.exe -i https://<API域名>/health
```

预期：

- `/health/live`：HTTP 200，`status=alive`，不依赖数据库和外部新闻源。
- `/health/ready`：数据库可连接时 HTTP 200；Redis 不可用时返回 `status=degraded` 但仍为 200；数据库不可用时 HTTP 503。
- 外部新闻站点失败不会让 API 健康检查失败。

### 12.2 登录与来源 API

```powershell
$body = @{ email = "admin@example.com"; password = "<密码>" } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri "https://<API域名>/api/auth/login" -ContentType "application/json" -Body $body
Invoke-RestMethod -Uri "https://<API域名>/api/sources" -Headers @{ Authorization = "Bearer $($login.access_token)" }
```

预期可看到来源列表，并包含 `adapter_status`、最近抓取状态、条数和失败原因。

### 12.3 Worker 与 Scheduler

1. 打开 Worker Deploy Logs，确认出现 `ready`。
2. 打开 Scheduler Deploy Logs，确认 Beat 已启动，并每分钟发送 `tasks.dispatch_due_sources`。
3. 在数据源管理页选择一个 `active` 且 `enabled` 的来源，点击单源抓取。
4. API 返回 HTTP 202 和 `job_id`。
5. Worker 日志依次出现 `crawl task received` 与 `crawl run finished`。
6. 数据源运行记录出现 `success`、`failed` 或重试状态，并带抓取条数/失败原因。
7. 选择公众号 `manual_only` 来源，确认没有自动抓取入口；只通过“手动导入”录入。

也可在 Worker 容器内验证 broker 连接和 Worker 响应：

```bash
celery -A celery_app.celery inspect ping
```

## 13. 常见故障排查

### CORS

症状：浏览器控制台显示 blocked by CORS，但 curl 可访问 API。

检查：

- `ALLOWED_ORIGINS` 必须与浏览器地址栏中的 origin 完全一致，包括 `https`、子域名和非默认端口。
- 不要带路径或末尾 `/`，多个 origin 用英文逗号分隔。
- 修改变量后，在 Railway 中 Deploy staged changes/重新部署三个应用服务。
- 生产环境禁止 `*`；使用 Cookie/Authorization 的请求不能依赖无条件通配。

### 数据库连接失败

症状：pre-deploy Alembic 失败，或 `/health/ready` 返回 503 且 `database=unavailable`。

检查：

- 数据库服务名是否正好为 `Postgres`。
- `DATABASE_URL` 是否为 `${{Postgres.DATABASE_URL}}`，不要使用公网 URL。
- Postgres 是否 Active，数据库是否达到连接/资源上限。
- 日志若显示驱动 URL 问题，确认镜像包含 `psycopg[binary]`；应用会自动把 `postgres://` 或 `postgresql://` 规范为 `postgresql+psycopg://`。
- 用 API 容器执行 `alembic -c alembic.ini current` 检查 revision。

### Redis / Worker 无法消费

症状：API 可用但手动抓取返回 queue unavailable，或任务长期 queued。

检查：

- Redis 服务名是否正好为 `Redis`，`REDIS_URL=${{Redis.REDIS_URL}}` 是否已分享给三个应用服务。
- Redis 是否 Active；Worker 日志是否出现 broker reconnect 或认证错误。
- Worker 是否关闭了 Serverless/App Sleeping，是否出现 `ready`。
- 执行 `celery -A celery_app.celery inspect ping`。
- `/health/ready` 的 Redis degraded 是提示，不会因队列短暂故障把只读 API 摘除。

### 502 / Application failed to respond

检查：

- API 日志中 Uvicorn 是否监听 `0.0.0.0:$PORT`。
- Public Domain 是否绑定到 API，而不是 Worker/Scheduler。
- `ENVIRONMENT=production` 所需变量是否全部存在；缺少或不合规时应用会 fail fast，并在日志给出明确错误。
- 健康检查路径是否为 `/health/ready`，超时是否为 300 秒。
- 不要在 Railway 网页中用一个未经过 shell 的 Docker start command 直接引用 `$PORT`；当前 `/railway.toml` 已正确包裹。

### 迁移失败

检查：

- 先看 API deployment 的 Pre-deploy Logs，而不是仅看运行日志。
- 确认 `DATABASE_URL` 指向目标生产库，且用户具备建表、建索引、创建 `pg_trgm` extension 的权限。
- 执行 `alembic -c alembic.ini current` 和 `alembic -c alembic.ini history`。
- 不要删除 `alembic_version`、不要手工 drop 表、不要用 `create_all` 替代迁移。
- 迁移失败时 Railway 不会切换新 API；修正 migration 或权限后重新部署。

## 14. 发布顺序建议

首次上线：Postgres → Redis → API（迁移成功）→ 创建管理员 → Worker → Scheduler → 生成/确认 API 域名 → 设置前端 `NEXT_PUBLIC_API_BASE_URL` → 重建前端 → 完整验证。

后续仅代码更新可使用 GitHub 自动部署。含数据库 schema 变更时，先完成 API 的 pre-deploy migration，再让 Worker/Scheduler 使用新版本；Scheduler 始终保持单副本。
