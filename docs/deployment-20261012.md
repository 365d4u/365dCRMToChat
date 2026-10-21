# CRM 消息站切换：部署与回滚

2026-10-12，依据用户“按照前面的设计来安全切换”的授权执行。Biz 未登记资源使用对应项目发布 Skill 与服务器既有运行配置，不提取/保存数据库凭据。本次范围为消息来源、chat_db 新分表、CRM 跳转和批量媒体刷新。

随后按用户指定主机迁移：正式消费者现位于 `107.150.104.4:/data/365dCRMToChat`；下面的 165 主机目录为首次上线记录，其消费者和隧道已停止并禁用。当前运维以 [主机迁移记录](host-migration-20261012.md) 为准。

后续用户明确禁止旧 Respond 程序再写 chat_db：已发布默认禁写、拒绝开启开关、DAO 写入拦截与只读会话保护。当前搜索、历史映射服务和清理结果见 [后续记录](crm-reference-search-20261012.md)；本页旧来源回滚方案已撤销。

## 已部署

| 项目 | 变更与位置 |
| --- | --- |
| CRM | main `f6f117f`、`6cf85ad`；API current 为 `/data/365d-crm/releases/msgsite-6cf85ada5332a75d413ce375d5100ce5619b8bc6`；API 增加受限媒体接口；共享 PostgreSQL 增加快照/版本/设置/resync；新增 `365d-crm-msgsite-resync.service` |
| 365dCRMToChat | `/var/www/python/365dCRMToChat`；`365d-crm-to-chat.service` 正式消费、事务写入；`365d-crm-to-chat-tunnel.service` 只转发 Broker；运行配置 `/etc/365d-crm-to-chat.env` root 600 |
| chat_db | 新 CRM 消息表、可见视图、回执和已验证关联表；分表注册 ID 7，来源 ID 11；原消息表未改写 |
| chatwoot_message | 十个源文件，新增身份装饰/媒体解析/浏览器刷新；使用 CRM 客户主键和跳转；分页/引用/导出适配稳定资源身份；外部媒体下载失败日志不记录签名 URL |
| respond_to_msgsite | 仅 `service/queue_handle.py` 与 unit 覆盖；`CHAT_DB_WRITE_ENABLED=false`；#fw 和实时转发保留 |

CRM 原 Webhook、发送/入站 Worker、媒体 Worker 没有重启或发布。原 Outbox Relay 发布新增精确路由。未做全量历史回填、未发送客户/飞书测试消息。旧业务主链仍有跟进/转发依赖，不能据此直接停掉 Respond 全套服务。

消息站新主键严格是 `crm_<customerId>`；不是 CRM conversationId。无 CRM 映射的历史会话保留内部旧键，但不显示 Respond ID/外部跳转。关联表仅接受有证据且 verified=1 的映射，未自动导入未知旧映射。

## 恢复点

- CRM：`/data/365d-crm/config/migration/msgsite-20261012/`，保存 schema preimage、已安装 SQL、工作区补丁、旧链接与 SSH authorized_keys 前像。旧 API 为 `internal-replies-86a4308c7081f8b254835b95340c1a6081fb204f`。
- 消息站：`/var/backups/chatwoot_message/crm-cutover-20261012/source-preimage.tar.gz` 保存七个被替换原文件；同目录保存 schema/注册项前像。三个新增文件没有原版本。
- Respond：`/var/backups/respond_to_msgsite/crm-cutover-20261012/queue_handle.py` 保存原文件；unit 覆盖为 `respond_to_msgsite.service.d/30-crm-cutover.conf`。
- CRM API 覆盖为 `365d-crm-api.service.d/30-msgsite.conf`；消息站覆盖为 `chatwoot_message.service.d/30-crm-media.conf`。原环境文件未覆盖，机器 Token/隧道私钥仅保存在服务器受限路径。
- 已移除本次干净临时构建目录及核实无引用的旧重复发布，保留当前、两个 API 回滚版本和独立广告服务活动版本；迁移/恢复资料保留。

## 故障处理与回滚顺序

以下是运维方案，不代表本次已经回滚。操作必须通过对应项目 Skill，在现场核对路径、活动版本及运行引用。

1. 目标故障优先停止 `365d-crm-to-chat.service`，保留源发布和专用持久队列积累消息；修复后恢复消费。不要清队列、删回执或修改消息版本。
2. 不得恢复 Respond 的 chat_db 写入。故障时暂停 CRM 消费、保留队列，修复或回退 CRM 投影版本后继续消费；旧 Respond 备份仅供审计，不能用来重新开启旧消息来源。
3. 需要回退页面时恢复消息站七个原文件，仅移除本次媒体 unit 覆盖并重启该服务；CRM 分表、历史数据和备份继续保留。新增三个文件可暂留，不应删除旧业务数据或人工状态。
4. API 功能回退：先停 resync，恢复 `previous-release.txt` 对应 current，仅移除本次 API 覆盖，然后仅重启 API；不改 Worker/Webhook/media 链接。新数据库结构保留，源开关可通过服务器运行身份设为 false。
5. 关闭源发布后变更不会再生成同步事件；恢复时应对受影响 CRM 会话建立有界 resync，不能声称自动补齐暂停窗口。旧 Respond 停写期间已确认的事件也不会自动回放到旧表。
6. 全面退出集成才停 SSH 隧道、移除本次精确受限公钥；只移除这次新增配置，不覆盖原 authorized_keys。保持恢复点和新投影数据供追查。

## 验证

最终源版本表 5,709 条；目标同数，全部工作区 1，可见 5,695 条/104 客户；正式/异常队列均无积压。20 条源样本无缺失，五条同版摘要一致、十五条目标已更新。三例 45–46 天历史附件使用 backup 返回可用。

Python 36 项、CRM 25 项定向测试及 Linux 正式构建通过。健康/鉴权、版本、进程开关与运行计数见 [验证结果](verification.md)。计数仅为核验时点，不是永久固定值。
