# 阿里云 RabbitMQ 双来源准备（未部署）

用户要求独立分支保存、不合并主分支、不部署，并允许从生产主机运行隔离的 MQ 收发测试。
原 `E:/PycharmProjects/365dCRMToChat` 没有 Git 仓库；本次将应用源码、测试、契约文档、示例、迁移记录和项目元数据复制到
`E:/PycharmProjects/365dCRMToChat-aliyun-mq-20261021`，以 `522ef92` 保存基线，再建立 `codex/aliyun-rabbitmq-migration`。
没有复制生产环境文件、密钥、备份、旧运维执行脚本或缓存到版本控制；原项目目录不变。本地 main 只是隔离副本基线，无 remote。

## 行为与配置

新增 `crm_to_chat/rabbitmq.py`，供正式快照消费者和临时观察命令共用。使用验证主机名和证书的 AMQPS，Pika `client_properties` 包含共享实例 ID 与兼容 `connection_name`；URL、密码和原始连接异常不进入日志。旧 loopback SSH 隧道仍可使用 AMQP。

| 环境变量 | 用途 |
| --- | --- |
| `CRM_TO_CHAT_AMQP_URL` | 主消费来源，仍使用原配置名 |
| `CRM_TO_CHAT_AMQP_INSTANCE_ID` | 主来源阿里云实例 ID，自建留空 |
| `CRM_TO_CHAT_DRAIN_AMQP_URL` | 迁移期间第二消费来源；不配置则单源 |
| `CRM_TO_CHAT_DRAIN_AMQP_INSTANCE_ID` | 第二来源实例 ID，自建留空 |
| `CRM_TO_CHAT_WORKSPACE_IDS` | 明确允许的工作区，现有范围为 `1` |

正式入口仍须 `CRM_TO_CHAT_WRITE_ENABLED=true`；本次没有修改生产开关。观察入口始终 preview-only，不会启动持久队列消费者。
重复 endpoint/vhost、缺少 DRAIN URL 的实例 ID、不安全公网 AMQP、URL 查询参数等在建立数据库连接前被拒绝。密码中的 `#` 等字符必须 URL 编码；不要将完整 URL 放入命令行或 Git。

两个 Broker 分别声明同名 durable 快照队列、invalid 队列及精确绑定：
`365dCRMToChat.snapshot.v1` / `.invalid`，`365d.realtime.v1` → `crm.message.snapshot.v1`。
保留原 invalid 队列的默认 Exchange 死信配置，不增加 TTL、最大长度或自动清理。
Exchange 仍 passive 检查，不擅自创建/改变业务 Exchange。

**始终只有一个进程中的串行 ChatWriter 和一个数据库会话。** 同线程轮询两个连接、各 prefetch=1；事务提交后只 ACK 原来源 channel。
数据库异常不 ACK，关闭两来源连接并重建数据库会话；传输失败只重连失败来源，另一来源继续轮询。
确认已提交而 ACK 失败的重投沿用既有事务回执；跨来源重复和乱序沿用既有 workspace/eventId/revision 保护，不改变事件契约或身份算法。
SIGTERM/SIGINT 请求停止，在当前回调完成后关闭连接；未 ACK 消息回到原 Broker。

单线程方案的边界：失败来源每 10 秒重试一次，单次握手 stack timeout 为 8 秒；重连期间同一线程可能短暂停顿另一来源的处理。
这不等于两个独立 I/O 线程，也不保证跨 Broker 全局投递顺序。数据库不可用时两端均停止写入，保留未 ACK 消息。

## 将来切换顺序（本次未执行）

1. 先把这份源码与原项目最新变更复核整合，核对生产的队列属性、实例权限、工作区及消费超时/重投上限/DLX 策略。
2. 以单个 CRMToChat writer 先支持双来源：旧隧道为主，阿里云为 DRAIN。两来源都 ready 后，检查阿里云持久快照绑定真实存在，再允许 CRM Relay 切发布目标。不能用临时观察队列或 HTTP ready 替代此项。
3. CRM 切阿里云为主后，CRMToChat 可同样交换主与 DRAIN 配置，仍使用同一写入进程、原数据库与回执。禁止同时运行旧单源 writer 和新的双源 writer；不复活 Respond 写入者。
4. 持续核对所有旧发布进程已切换，旧快照队列 ready/unacked 均持续为零，跨过重试与恢复窗口，之后才取消旧来源并考虑停隧道。保留 Broker、持久队列、回执与恢复资料。
5. 回滚发布目标时保留两端消费。只退回原单源程序会停止处理阿里云积压，不能作为无损回滚；必须另行安排排空，不能 purge 或删除回执。

## 验证

本地纯合成夹具 75 项测试通过，覆盖双源共用一个 writer、任一来源不可用/重连、数据库失败不 ACK、提交先于 ACK、跨来源重复/旧 revision、工作区拒绝及 TLS/实例参数。
现有媒体兼容、历史身份引用与 Respond 写入退役测试继续通过，未改这些业务路径。
结果：`docs/validation-results/2026-10-21-aliyun-unit-tests.json`。

生产主机测试使用现有 venv/Pika，只通过 SSH stdin 在内存中载入本分支的连接 helper 与显式合成探针；没有上传/安装应用、读取数据库配置或调用 ChatWriter。
仅创建 UUID 命名的 `codex.probe.*` 队列/Exchange，测后删除。详见 `docs/validation-results/2026-10-21-aliyun-production-probes.json`。
原业务消费者与 SSH 隧道保持运行，未部署、未重启、未改生产 env、未消费业务队列、未重放真实消息。

这些验证不替代数据库/业务端到端验收、生产属性检查、长时间压力测试或 Broker 故障切换测试；不宣称绝对不丢或端到端 exactly-once。


末轮完整通过结果（约 1 KiB 合成正文，毫秒）：

| 来源主机 | 普通 + 离线恢复 + 死信条数 | 发布确认 p95 | 发布到回调 p95 |
| --- | --- | --- | --- |
| Web/API 154.197.57.214 | 200 + 1 + 1 | 30.44 | 165.82 |
| Webhook/Worker 150.107.38.199 | 200 + 1 + 1 | 38.19 | 102.29 |
| CRMToChat 107.150.104.4 | 100 + 1 + 1 | 15.04 | 268.63 |

三台末轮均无意外重复或正文损坏，publisher confirm、mandatory return、消费者离线积压、未 ACK 重投 redelivered 和死信验证通过，末轮报告剩余为零；测试资源全部清理。
Node 测试是 50 条串行加 150 条分批发送，Pika 是 100 条串行，包含不同事件轮询开销，不能横向推断 Broker 性能差异。
此前 Worker 和 Python 的“已收齐但报告剩余 1”观察仍保留，Python 一轮持续 20 秒为 1；后续 20 条及 100 条均为零，未再次触发附加取消息检查，原因尚未确定。不能将复测通过当作已解释该异常，正式切换须持续核对 ready/unacked 与实际处理回执。
全部测试结束后，API、sender、confirmation、Webhook、Worker、media Worker、CRMToChat consumer/tunnel 保持 active/NRestarts=0，已记录角色的 PID 与开始检查一致；没有修改或启动这些服务。
