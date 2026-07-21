# 首批抓取适配器状态

校验时间：2026-07-20（Asia/Shanghai）。校验使用生产 User-Agent，遵守 `robots.txt`，只读取公开 RSS、API 或 HTML 列表；校验脚本不会把结果写成数据库抓取成功记录。

## 已验证可返回有效条目（active）

- World Bank Projects & Procurement（官方 API）
- Data Center Dynamics（RSS）
- Data Center Knowledge（RSS）
- Mexico News Daily（RSS）
- PV Tech（RSS）
- PV Magazine（RSS）
- Energy Storage News（RSS）
- Offshore Energy（RSS）
- Vietnam Investment Review（HTML）
- 见道网海外项目（HTML）

## 不作为成功来源

- `blocked`：Asian Development Bank、AIIB、Construction Week Saudi。校验期间其 `robots.txt` 返回 403/405，自动抓取默认关闭。
- `pending_adapter`：Engineering News、Mining Weekly、Renewables Now 的原 RSS 端点失效；中国一带一路网本次网络不可达；北极星光伏页面可访问但当前选择器没有提取到有效条目。
- 其余来源保持 `pending_adapter`、`manual_only`、`blocked` 或 `disabled`，不会显示虚假成功时间或条数。

再次验证：

```powershell
cd backend
$env:CRAWL_TIMEOUT_SECONDS='12'
.\.venv\Scripts\python.exe -B adapter_check.py
```
