import json


def fixture(event_id="event-1", revision="1", message_id="1001", workspace_id="1"):
    return {
        "schemaVersion": 1, "eventType": "message.snapshot", "eventId": event_id,
        "workspaceId": workspace_id, "revision": revision, "emittedAt": "2026-10-10T11:00:00Z",
        "message": {
            "messageId": message_id, "conversationId": "2001", "customerId": "3001",
            "channelAccountId": "4001", "channel": "instagram", "direction": "inbound",
            "kind": "text", "text": "Synthetic message", "occurredAt": "2026-10-10T10:00:00Z",
            "updatedAt": "2026-10-10T11:00:00Z", "replyToMessageId": None, "deleted": False,
            "attachments": [{"index": 0, "type": "image", "mimeType": "image/jpeg", "fileName": "fixture.jpg"}],
        },
    }


def encoded(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def media_response(requests):
    return {"items": [{"resourceId": item["resourceId"], "variant": item["variant"],
                       "status": "available", "candidates": [
                           {"kind": "backup", "url": "https://media.example.test/fixture.mp4",
                            "expiresAt": "2099-01-01T00:00:00Z", "source": "object_storage"}]
                       } for item in requests]}
