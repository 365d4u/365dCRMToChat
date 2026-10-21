# 365dCRMToChat

CRM 到消息站的独立 Python 投影服务。2026-10-12 已按用户授权完成正式切换；原离线预览和临时队列观察命令继续只读运行。

## 正式链路

CRM 规范消息 → PostgreSQL 同事务 Outbox → 既有 RabbitMQ Relay → 专用队列 → 本项目 → chat_db CRM 分表 → chatwoot_message。

- 消息站会话 ID 为 `crm_<CRM customerId>`，汇总同一客户的渠道消息；每条消息保留 CRM messageId、conversationId、channelAccountId、workspaceId。
- 正式工作区当前仅 `1`。无客户归属的消息暂存但不显示，不猜测 Respond/Provider ID 的对应关系。
- chat_db 新增 CRM 消息分表、可见视图、事件回执和已验证关联表；旧表、人工分组和标签保留。新正文/附件/属性字段为 LONGTEXT。
- 一个 MySQL 事务完成去重、版本检查、消息写入及摘要更新，提交后才 ACK。旧版本跳过；非法/冲突事件保留在异常队列；数据库故障关闭连接后重投。
- `respond_to_msgsite` 已永久退出 chat_db 写入：默认关闭且拒绝启用开关，数据库层阻断写操作并使用只读会话；`#fw` 客服只读查询和原实时转发保留。
- 有 CRM 客户身份时显示 `Go CRM(<id>)`，跳转 `https://crm.365d4u.com/inbox/<id>`。没有可用 CRM 映射时，只有明确且唯一的旧 Respond ID 才显示 `Go Respond(<id>)`；没有 ID 或存在冲突时不猜测跳转。内部历史主键保留。

消息站搜索支持纯数字 CRM 客户 ID 与 `crm_<id>`；新增 `CRM ID Search` 精确模式。`crm_respond_customer_link` 缓存 CRM 已核验的 Respond 引用，`crm_conversation_link` 连接旧会话。`365d-crm-reference-sync.service` 为受限批量同步，timer 每 30 分钟执行；不改写旧消息。展示关联按已审核证据及合并/拆分/撤销/身份转移审计确认当前归属，普通资料版本变化不再自动取消关联；失效引用和归属变化仍取消本服务生成的关联，人工映射保留，冲突不猜测。详见 [搜索和映射记录](docs/crm-reference-search-20261012.md) 及 [本次补齐与 Respond 兜底记录](docs/crm-reference-fallback-20261012.md)。

## 附件批量刷新

数据库保存稳定 `message/<CRM messageId>/<attachment index>` 及元数据，不保存会过期的签名地址。消息站后端调用 CRM 专用 `POST /api/msgsite/media/resolve`，取得当前原始、Provider、预览或备份地址。

CRM 单批最多 50 项，Python 客户端最多 250 项分批处理。分页、引用及导出按需解析。浏览器加载失败后调用消息站 `POST /api/conversations/<crm_id>/media/resolve` 批量刷新，排除已失败候选；单元素最多自动尝试三次。

消息站校验登录和附件所属会话。CRM 机器接口使用独立 Token、工作区白名单，资源限定为消息附件。Token 只留后端；返回 JSON，不代理媒体字节。没有源内容且没有备份的附件仍返回不可用。

## 正式运行

要求 Python 3.12+；正式依赖单独安装：

```powershell
python -m pip install ".[writer]"
```

入口为 `python -m crm_to_chat.consume`，必须明确设置 `CRM_TO_CHAT_WRITE_ENABLED=true` 和 `CRM_TO_CHAT_WORKSPACE_IDS`。数据库复用指定服务器既有 chat_db 运行配置，不复制数据库凭据到本机或跨主机搬运。

正式主机为 `107.150.104.4`，SSH `2208` / `ubuntu`；项目、独立 venv、配置和隧道状态均位于 `/data/365dCRMToChat`。服务 `365d-crm-to-chat.service`，RabbitMQ 经独立 `365d-crm-to-chat-tunnel.service` 的 SSH 回环转发连接。

该主机使用 `CRM_TO_CHAT_DB_ENV_STYLE=respond`，从既有运行环境读取 `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/CHAT_DB_NAME`，不会将 `DB_NAME` 误当作 chat_db。旧 `CONV_DB_*` 模式仍兼容。消息站主机的消费者和隧道已禁用，媒体客户端及原 Token 保留。详情见 [主机迁移记录](docs/host-migration-20261012.md)。

正式队列 `365dCRMToChat.snapshot.v1`，异常队列 `365dCRMToChat.snapshot.v1.invalid`；绑定既有 `365d.realtime.v1` 的精确 `crm.message.snapshot.v1`，不读取其他业务队列。

`migrations/chat_db.sql` 是已执行的增量迁移记录，不可盲目重复运行。现场注册 ID 和原始结构须先核对。发布及回滚见 [切换记录](docs/deployment-20261012.md)。

## 本地预览

```powershell
Set-Location E:\PycharmProjects\365dCRMToChat
python main.py check
python main.py preview --input examples\messages.jsonl
python main.py media-plan --input examples\media-request.json
python -m unittest discover -s tests -v
```

预览默认内存，可指定 `--state var\preview.sqlite3`。这些命令不连接 chat_db，仍拒绝写入开启配置；`check` 的 `chatDbWriteSupported=false` 描述预览 CLI，正式服务使用独立入口。

`observe` 只消费自己随机命名的临时副本队列，不能用于可靠归档或正式切换。`serve` 是本地验证媒体网关，生产页面直接使用消息站到 CRM 的受限接口，无需开放验证服务器。

详见 [消息契约](docs/event-contract.md)、[验证结果](docs/verification.md)。日志不得输出正文、签名媒体链接或凭据。`ops/source-secrets.mjs` 只能通过私有 SSH 管道写入受限配置，禁止单独运行、打印或捕获输出。
# 365dCRMToChat
