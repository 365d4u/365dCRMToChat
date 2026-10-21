# 365dCRMToChat 指定主机迁移

2026-10-12（Asia/Shanghai）。用户明确指定主机、SSH 端口/用户和项目路径；未将密码写入代码、文档或日志。

## 当前部署

| 项目 | 位置/配置 |
| --- | --- |
| 主机 | `107.150.104.4`，SSH `2208`，`ubuntu` |
| 项目 | `/data/365dCRMToChat` |
| Python | `/data/365dCRMToChat/venv/bin/python`，独立 Python 3.12 venv |
| 消费者 | `365d-crm-to-chat.service`，www-data:webgroup，CPU 30%、内存 256 MiB |
| 隧道 | `365d-crm-to-chat-tunnel.service`，回环端口 35672，经 CRM API 主机转发既有 Broker；仅允许指定来源 IP 和 Broker 目标 |
| 集成配置 | `/data/365dCRMToChat/config/consumer.env`，root 600，仅 MQ/开关/工作区/环境样式 |
| 隧道私钥 | `/data/365dCRMToChat/state/tunnel_key`，www-data 600；没有取回私钥 |
| 数据库 | 复用本机既有服务运行环境；不复制数据库配置或密码。明确使用 CHAT_DB_NAME，不误用 Respond 的 DB_NAME |

目标目录原为空，未覆盖未知项目代码。数据库未迁移、表结构未再改变；同一持久队列、事件回执和 CRM 消息分表继续使用。

数据库环境样式新增显式 `respond`，默认 `conv` 保持兼容。目标 unit 读取既有 `/var/www/respond_webhook/respond_to_msgsite/.env`，仅由程序使用 DB_* 与 CHAT_DB_NAME；这是配置依赖，不调用旧 Respond 代码或 API。将来删除旧项目时须先安排服务器运行配置的正式独立管理，不得直接删除该环境文件。

## 切换证据

- 预检在写入 false 时已证明 chat_db 和 Broker 可连接：24,194 条 CRM 消息、69,048 条回执，正式队列 ready=0/消费者=1（当时为旧主机）。
- 随后先停止并禁用消息站主机 `165.154.134.51` 的消费者与隧道，将其写入开关设 false，再开启指定主机消费者。没有同时启用两个写入器。
- 新消费者 PID 2195290、隧道 PID 2194959，active/running、NRestarts=0；实际进程开关 true、环境样式 respond。新进程日志连续出现 projected/applied，证明真实业务投影提交后完成确认。
- 切换后观察 CRM 消息 24,224、回执 70,815，正式队列 ready=0/消费者=1、异常队列 ready=0。数量是核验快照，不是全量历史数量。
- 原 respond_to_msgsite PID 2188456 及主 Respond 消费者 PID 1970517 保持运行，未重启；原 chat_db 写入开关仍 false。
- 旧主机两项集成服务均 inactive/disabled、PID 0；消息站 PID 1334635 保持运行，根路径正常 302；CRM 媒体 Token 保留。
- 消息站迁移后抽查三个带附件 CRM 消息，12 个附件全部返回可用 source 地址；只解析地址，未下载媒体字节。检查使用实际 data_url 字段。
- Python 39 项合成测试通过，新增三项检查两种环境样式、明确选择 chat_db 及拒绝未知样式。生产预检只读，没有运行测试数据写入。

## 备份和回退

旧主机 `/var/backups/365dCRMToChat/host-migration-20261012/` 保存两份原 unit 和迁移前集成配置，目录 root 700/配置 600；其中没有数据库配置。源 API `/data/365d-crm/config/migration/msgsite-host-107-20261012/` 保存新增受限 SSH 公钥前的 authorized_keys。

目标启用前配置保存在 `/data/365dCRMToChat/backups/host-migration-20261012/consumer-before-enable.env`，仅含 MQ/开关等集成配置，未复制数据库凭据。

需要退回旧部署时，先在指定主机停止并禁用消费者，再停隧道、恢复目标 false；确认目标不消费后，将旧主机集成写入开关恢复 true 并启用旧隧道/消费者。消息站媒体 Token 保留，不覆盖原数据库环境。队列和回执不得删除或清空，未确认消息会重投、已提交事件按回执去重。

只有确认长期不再需要回退后，才评估撤销旧来源精确公钥或删除旧代码备份。消息站仍使用已安装媒体库，不能连同 venv 依赖一起删除。
