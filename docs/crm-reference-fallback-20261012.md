# CRM 历史映射补齐与 Respond 跳转兜底

2026-10-12，按用户最新要求：尽量补齐有可靠证据的 CRM customerId 与旧 Respond ID；优先 Go CRM，没有可用 CRM 关联且有明确唯一 Respond ID 时恢复 Go Respond。旧 Respond 消费者仍永久禁止 chat_db 写入。

## 原因与规则

旧导出把客户资料的通用 version 与引用审核时 version 不相等视为失效。头像及资料自然更新也增加 version，导致已审核且归属未变的映射被撤销。截图三个客户的版本分别从 521→573、28→31、20→39，归属操作记录没有审核后的变化。

源仍是 CRM `app.customer_external_references`，范围 workspace1 / production / respond / respond/mysql-b0497d24dc471307 / contacts。导出保持 verified、active、canonical 根同一客户和工作区渠道身份约束。对资料版本变化，要求引用及根引用都保留审核证据；客户合并、拆分、撤销、身份转移在任一审核之后发生时，仍拒绝关联。CRM 其他身份/订单接口的版本规则没有改变。

每次导出在显式 repeatable-read/read-only 事务内按 5,000 条分页，查询/锁超时及 250,000 条上限保留；校验完整 NDJSON 和 SHA256 后才更新派生关联。没有 CRM 业务数据库写入、表结构变更、旧消息迁移或 Respond API 请求。

消息站合并两个旧 Respond 对照表的直接边及 `rd_` 主键证据；所有别名必须已核验并指向同一 CRM 客户，才用于补充显示。无 CRM 时仅唯一有效旧 ID 可生成 Respond 链接；数字 Chatwoot ID、名字、联系方式及支付单号不作为身份映射。人工关联仍由原机制保护。

精确 CRM ID / `crm_<id>` 搜索不再使用旧合并会话规则扩大结果，也不纳入其他名称/邮箱匹配。All Search 与 ID/Name Search 保留原逻辑。发现并修复 CRM 902 曾额外带入无 CRM 证据的旧会话 190413 的回归。

## 上线结果

源代码已合入并推送 CRM main `ce336bf1515fdd515464483481d49b140a1a76d1`，仅部署独立导出程序及策略模块；没有重启 CRM API/Worker。通过 Biz CLI 管理员 SHA 守卫、加密备份与审计，change 393/394。源目录原为 root 所有，临时允许已配置 ubuntu 发布账号通过 Biz 写入后恢复 root:root 755，文件 644。原文件另保留于 `/data/365d-crm/config/deployments/reference-owner-audit-20261012/export.mjs.before`（root600）。

- 完整只读预览：194,561 条可用引用、141,423 条历史关联，历史归属冲突 0；已有明确边但源证据不足的历史集合 910 条暂不建立 CRM 关联。
- 常规 `365d-crm-reference-sync.service` 成功更新：引用 20,007 条、历史关联 19,224 条，本轮撤销均为 0。数字包含首次写入、恢复和刷新，不代表新增客户数。
- 同步后表内 verified 引用 194,561 条、verified 历史关联 141,423 条。
- 截图旧会话 `rd_429120621` → CRM 3755；旧会话 115195 / Respond 317763983 → CRM 7007；`rd_457693542` → CRM 20384。
- 未映射 `rd_316370720` 已核验显示 `Go Respond(316370720)`；旧数字会话 174800、175409 没有明确 Respond 对照或 CRM 证据，不猜测跳转。
- 消息站四文件：`service/crm_identity.py`、`service/conversation_manager.py`、`templates/conversations_list.html`、`templates/conversation_detail.html`。保留已有 reply-v3 媒体文案和其余资料/附件文件。
- 消息站最终 PID1342120，active、NRestarts0、回环及公网均302；最近服务日志没有新增错误。备份 `/var/backups/chatwoot_message/crm-preferred-respond-fallback-20261012/`。
- 107 消费者 PID2195290、隧道2194959、旧只读 Respond 下游2197540、主 Respond1970517均保持运行与原 PID。本次没有部署消费者代码、重启这些进程、重放或清理队列。
- 映射 timer 已恢复 active/enabled，仍每次完成后约30分钟运行。源/目标运行环境、Token、私钥不转移或输出。

## 验证与恢复

65 项离线 Python 测试、6 项 Node 身份审核规则测试通过；8 项合成真实模板渲染通过。服务器显式只读连接验证7种身份情形及14项真实模板渲染；暂存与正式搜索均覆盖9种真实用例及非法 ID 无结果，包括上述三个截图客户和 CRM 902 合并会话回归。没有生产登录浏览器点击验收、真实客户发送、附件下载或数据库迁移。

目标保留同步前快照和预览快照于 `/data/365dCRMToChat/state/reference-sync/`，目录700/文件root600。故障先停受影响映射 timer/service，保留当前映射与消息队列；修复导出可经 Biz guarded rollback 394 回到旧严格版本（会再次撤销资料版本变化的历史关联）。页面可按四文件前像恢复。禁止为回滚恢复旧 Respond chat_db 写入。

所有数量与 PID 是本次核验快照。新的归属操作仍可能使关联失效；未知关系不补造。
