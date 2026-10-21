# CRM 消息快照契约 v1

2026-10-12 发布端与接收端已启用。使用完整 `message.snapshot`，routing key `crm.message.snapshot.v1`，Exchange 为既有 `365d.realtime.v1`；原 `message.changed` 不能替代完整快照。

```json
{
  "schemaVersion": 1,
  "eventType": "message.snapshot",
  "eventId": "crm-msgsite:1001:2",
  "workspaceId": "1",
  "revision": "2",
  "emittedAt": "2026-10-12T11:00:00Z",
  "message": {
    "messageId": "1001", "conversationId": "2001", "customerId": "3001",
    "channelAccountId": "4001", "channel": "instagram",
    "direction": "inbound", "kind": "image", "text": null,
    "occurredAt": "2026-10-12T10:00:00Z", "updatedAt": "2026-10-12T11:00:00Z",
    "replyToMessageId": null, "deleted": false, "status": "received",
    "attachments": [
      {"index": 0, "type": "image", "mimeType": "image/jpeg", "fileName": "photo.jpg", "size": 1024}
    ]
  },
  "presentation": {"customerName": "示例客户", "customerAvatar": null, "accountName": "示例渠道"}
}
```

## 发布保证

- ID 使用 CRM 内部十进制字符串；customerId/replyToMessageId 可以为 null。消息站主键是 `crm_<customerId>`，不能使用 CRM conversationId 替代客户 ID。
- 重投保持 eventId 和完整载荷一致。行锁串行化同消息的单调版本；快照/展示信息变化才增加 revision，不使用时间或投递顺序替代版本。
- 消息变更、版本和 Outbox 同事务提交；既有 Relay 持久发布并使用 publisher confirm。
- 新增/编辑/删除由数据库触发器投影；客户归属和客户展示资料变化排入 resync，由独立任务每次最多 50 条处理。
- 删除/客户抑制快照保留身份、版本，正文 null、附件为空。旧事件不能恢复高版本删除。
- 附件序号从 0 连续排列，快照完整替换集合。不发送 Provider raw payload、Token、私有 locator、存储密钥或过期媒体 URL。
- 源设置、消费者及媒体接口均限制允许工作区，当前仅 1。

源实现为 CRM main 的 `docs/integrations/msgsite-source.sql`、`scripts/msgsite-resync.mjs`；默认关闭，准备完毕才显式启用。

## 接收保证

拒绝未知协议/字段、重复 JSON 键、数字类型 ID、无时区日期、非法附件序号及超过 1 MiB 的事件。新字段须明确升级契约。

正式消息分表隔离旧 Respond 编号；回执与内容摘要实现事务去重和版本保护。同客户汇总到 `crm_<customerId>`，每条消息原会话/账号/工作区保留。

未关联客户的消息暂存为内部 `crm_unlinked_<conversationId>`，可见视图/摘要排除；归属变更后移到客户会话并重算旧摘要，保留人工状态。

附件保存 `media:message/<messageId>/<index>` 与 crm_resource_id，展示时批量获取当前地址。正文 HTML 转义，时间转为旧站使用的 UTC+8 无时区值。

SQLite 仅用于预览，临时队列仅用于观察；正式写入入口为 `crm_to_chat.consume`。
