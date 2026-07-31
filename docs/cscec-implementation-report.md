# 中建 KA 监测实施报告

完成日期：2026-07-30

## 交付内容

- 新增中建组织主数据，当前解析实体数：82。
- 新增中建专项来源，当前来源数：28。
- 新增组织快照、页面差异、领导事件、组织事件模型。
- 新增 Alembic 迁移 `0003_cscec_monitoring`，幂等升级，不清空已有生产数据。
- 新增中建专用适配器 `CSCECNewsAdapter` 与 `CSCECOrganizationAdapter`。
- 新增 Celery 任务 `tasks.sync_cscec_entities`，并加入每日 UTC 03:30 调度。
- 新增中建 API 与前端“中建KA动态”页面。
- 新增测试覆盖实体主数据、别名归一化、页面差异、事件去重、权限 API、批次互斥、迁移表结构。

## 验证结果

- 后端测试：`42 passed`
- 前端测试和构建：`npm.cmd test` 通过
- 来源与实体校验：28 个中建来源均能匹配到 `cscec_entities` 中的 `entity_id`
- 公众号校验：`中国建筑公众号` 和 `中国建筑投资者关系公众号` 均保持 `manual_import`

## 仍需人工完成

- 将代码上传到 GitHub 主分支。
- Railway API 重新部署并执行 Alembic。
- Railway Worker 重新部署。
- 如已创建 Scheduler，重新部署 Scheduler 且只保留 1 个实例。
- Cloudflare Pages 重新构建前端。
- 真实网络环境验证中建官网栏目选择器，通过后再把对应来源从 `pending_adapter` 改为 `active`。
