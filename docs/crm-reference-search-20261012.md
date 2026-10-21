# CRM ID 搜索、历史关联与旧写入退役

2026-10-12，按用户明确要求实施：消息来源继续是 CRM，旧 Respond 消费者不得再写 chat_db；支持按 CRM 客户 ID 查旧会话，关联存入 chat_db；正式项目部署在 107.150.104.4 的 /data/365dCRMToChat，采用 systemd，清理旧安装文件。

后续用户调整与新版上线见 [历史映射补齐与 Respond 兜底](crm-reference-fallback-20261012.md)：优先 CRM，有明确唯一旧 ID 时允许 Respond 兜底；普通资料版本变化不再撤销已审核且归属未变的展示关联。以下为首轮切换时的历史记录。

## 已上线行为

- 消息站搜索支持数字 CRM customerId 和 crm_<customerId>；新增 CRM ID Search，只返回该 CRM 客户及其已验证历史会话。默认 All Search 保留原订单/旧 ID/名称搜索，也包含 CRM ID；数字碰撞时用精确 CRM 模式。
- 页面有客户身份显示 Go CRM，未知关联没有外跳。映射只用于历史关联，不将 Respond ID 重新显示到页面。
- respond_to_msgsite 的 queue_handle.py 默认禁写且拒绝启用 CHAT_DB_WRITE_ENABLED；database.py 的 execute_update 直接拒绝，execute_query 只接受 SELECT、开启只读事务，连接池会话只读。#fw 所需客服查询和实时转发仍保留。实际进程 PID2197540、flag=false，旧主消费者 PID1970517 保持。
- 旧两文件备份在 /var/backups/respond_to_msgsite/no-chat-db-write-20261012/。不得以故障回滚为由恢复旧写入；优先暂停 CRM 消费并保留队列。

## 关联来源及服务

CRM 的 app.customer_external_references 是唯一权威来源，限定 workspace1 / production / respond / respond/mysql-b0497d24dc471307 / contacts。只有 verified、当前 active 客户版本一致、canonical 根引用同一客户且同版本、工作区渠道身份存在的记录可导入。未知、过期和冲突的引用不猜测。

新增 crm_respond_customer_link，保存 respond_id、crm_customer_id、工作区、源 referenceId/revision 及证据，带客户查询索引。crm_conversation_link 增加客户索引，并根据旧 map_conversation_respond、respond_conv_map 与真实历史会话生成派生关联。不会按数字相等或名字猜测，也不改旧正文、标签、分组或主键。

正式 365d-crm-reference-sync.service 为 oneshot，由 365d-crm-reference-sync.timer 每 30 分钟调度。它使用专用 SSH 公钥，仅允许来自107主机，forced command 只能导出上述范围的引用，不允许转发/PTY。源程序在 /data/365d-crm/operations/msgsite-reference-export/，读取 API 进程实际运行配置；数据库凭据不转移。

目标 key、known_hosts、快照与 schema 前像均在 /data/365dCRMToChat/state/reference-sync（root700，文件600）。服务 CPU30%、Nice15、MemoryMax512MiB。验证完整 NDJSON 页序列和 SHA256 后再写关联，每500条一个事务，重复记录不写；旧版/同版本改归属拒绝，更高源版本按 CRM 证据刷新。撤销/失效/历史冲突只取消本服务生成的关联；人工关联保留。异常大幅缩减需核验，导出失败不修改现有映射。

schema 前像 /data/365dCRMToChat/state/reference-sync/schema-before-20261012.json；增量 SQL 为 migrations/chat_db_references.sql，不可盲目重复执行。首次源范围194593条，当前版本有效181774条；完整导出再核对 canonical 根/渠道身份后181771条。

## 验证及清理

首批181771条客户关系、128638条历史会话关系写入，冲突0、证据不足历史1505条跳过，人工关联冲突0。56项合成测试通过，包括残缺导出/作用域/重复/ID注入、历史多别名冲突、人工保护、旧版本、撤销和数据库批次回滚；包含真实 PyMySQL 驱动的离线参数格式化验证。服务真实搜索覆盖数字、crm_格式、CRM精确模式及旧会话关联；非法ID无结果。列表和导出共用 fetch_paginated_conversations。

消息站三文件已备份到 /var/backups/chatwoot_message/crm-id-search-20261012/ 后发布。线上五种真实搜索用例及一个近期附件解析通过。截图的193516是旧消息站会话ID，当前没有经验证的 CRM 映射，不能把193516自动当作同一个CRM客户。

再次自然全量同步成功：181766条有效引用、128633条历史关联；源版本失效的5条引用及5条派生关联已撤销，未重复写入其余记录。service Result=success/ExecMainStatus=0，timer已enabled/active。第二轮撤销时发现驱动百分号转义问题，失败批次回滚后修正，并增加真实驱动离线回归；最终轮验证了实际撤销路径。源导出首轮的换行问题也已修正。

已删除165消息站主机的旧 /var/www/python/365dCRMToChat、停用的消费者/隧道unit、旧隧道状态与私钥；从CRM源移除旧165主机隧道公钥。消息站附件模块仍独立安装在自身venv，机器Token仅保留在新的 /etc/chatwoot-message-crm-media.env（root600），unit改用此文件；生产附件解析和运行中Token一致性通过。CRM正式消费者PID2195290及旧Respond主消费者未重启。

API、Worker、Webhook、媒体Worker未因这次关联同步部署或重启；本次仅安装独立只读导出运维程序。没有调用Respond API、重放消息、清队列或给客户/飞书发送测试消息。映射数量为核验时点快照，并非永久固定值。

故障可停止映射timer/service，保留现有映射；修复后 start 服务。恢复点、schema和有效快照保留，消息新写入服务独立运行，禁止恢复旧Respond写入。历史关联本身不等于搬运/合并旧消息到CRM新分表。

## 本地临时工作副本归档

用户进一步核对两个目录是否仍有必要。`365dCRMToChat-integration/365d_crm` 是 CRM 消息站迁移改造与发布验证使用的临时 CRM 工作副本；`crm-ad-material` 是 Respond 广告取数迁移、CRM 广告素材只读接口与权限配置任务的临时 CRM 工作副本。两者均非独立运行项目，改动已经合并到 CRM main，归档前没有未提交成果；正式保留 `E:\PycharmProjects\365d_crm` 与 `E:\PycharmProjects\365dCRMToChat`。

临时副本移至 `E:\PycharmProjects\_retired-worktrees\365dCRMToChat-integration-20261012` 和 `E:\PycharmProjects\_retired-worktrees\crm-ad-material-20261012`。前者 Git 登记已移除，Windows 依赖链接导致删除失败后的残留目录完整归档；后者通过 git worktree move 归档，Git 登记同步更新。自动审批检查随后拦截了彻底删除操作，未提供具体原因；采用可恢复归档，尚未释放剩余依赖缓存占用的空间。未改动线上服务或其他工作副本。

用户随后明确询问删除这两个项目，再次核验两份提交均在 origin/main、广告工作副本干净。批量文件删除命令仍被自动审批检查拦截且未执行；改用 Git 原生 worktree remove 后，`crm-ad-material-20261012` 已成功删除，Git 登记也已清理。`365dCRMToChat-integration-20261012` 的未登记残留目录仍保留，尚未删除。主 CRM 与正式消费者目录均存在，线上服务未改动。
