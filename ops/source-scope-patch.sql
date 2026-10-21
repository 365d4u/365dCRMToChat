ALTER TABLE app.msgsite_settings ADD workspace_ids bigint[] NOT NULL DEFAULT '{}';
UPDATE app.msgsite_settings SET workspace_ids=ARRAY(SELECT id FROM app.inbox_workspaces WHERE kind='production' AND status='active');
CREATE OR REPLACE FUNCTION app.msgsite_emit_message(target_id bigint, force_deleted boolean DEFAULT false) RETURNS void LANGUAGE plpgsql AS $$
DECLARE item record; snapshot jsonb; profile jsonb; revision_no bigint; payload_digest text; exchange text;
BEGIN
  SELECT exchange_name INTO exchange FROM app.msgsite_settings WHERE singleton AND enabled;
  IF exchange IS NULL THEN RETURN; END IF;
  -- Serialize against canonical message writes before taking a fresh snapshot.
  PERFORM 1 FROM app.messages WHERE id=target_id FOR NO KEY UPDATE;
  SELECT m.*,c.customer_id,c.channel_account_id,a.workspace_id,a.channel,
         u.display_name AS customer_name,u.avatar_url AS customer_avatar,
         COALESCE((SELECT COALESCE(NULLIF(p.account_display_name,''),NULLIF(p.account_username,''))
           FROM app.provider_connections p WHERE p.channel_account_id=a.id
           ORDER BY (p.status='active') DESC,p.id LIMIT 1),'CRM') AS account_name
  INTO item FROM app.messages m
    JOIN app.channel_conversations c ON c.id=m.channel_conversation_id
    JOIN app.channel_accounts a ON a.id=c.channel_account_id
    LEFT JOIN app.customers u ON u.id=c.customer_id WHERE m.id=target_id;
  IF NOT FOUND THEN RETURN; END IF;
  IF NOT EXISTS(SELECT 1 FROM app.msgsite_settings WHERE singleton AND item.workspace_id=ANY(workspace_ids)) THEN RETURN; END IF;
  snapshot=jsonb_build_object(
    'messageId',item.id::text,'conversationId',item.channel_conversation_id::text,
    'customerId',item.customer_id::text,'channelAccountId',item.channel_account_id::text,
    'channel',item.channel,'direction',item.direction,'kind',item.kind,
    'text',CASE WHEN force_deleted OR item.is_deleted OR item.customer_suppressed THEN NULL ELSE item.text_body END,
    'occurredAt',COALESCE(item.timeline_at,item.created_at),'updatedAt',item.updated_at,
    'replyToMessageId',item.reply_to_message_id::text,
    'deleted',force_deleted OR item.is_deleted OR item.customer_suppressed OR item.is_test,
    'status',item.status,
    'attachments',CASE WHEN force_deleted OR item.is_deleted OR item.customer_suppressed OR item.is_test THEN '[]'::jsonb ELSE
      COALESCE((SELECT jsonb_agg(jsonb_build_object('index',n-1,'type',COALESCE(v->>'type','file'),
        'mimeType',v->>'mimeType','fileName',v->>'fileName',
        'size',CASE WHEN jsonb_typeof(v->'size')='number' THEN v->'size' ELSE NULL END))
        FROM jsonb_array_elements(item.attachments) WITH ORDINALITY AS t(v,n)),'[]'::jsonb) END);
  IF item.is_test THEN snapshot=jsonb_set(snapshot,'{text}','null'); END IF;
  profile=jsonb_build_object('customerName',left(item.customer_name,255),
    'customerAvatar',left(item.customer_avatar,600),'accountName',left(item.account_name,255));
  payload_digest=md5((snapshot||profile)::text);
  INSERT INTO app.msgsite_message_versions(message_id,revision,payload_hash)
    VALUES(target_id,1,payload_digest) ON CONFLICT(message_id) DO UPDATE
      SET revision=app.msgsite_message_versions.revision+1,payload_hash=EXCLUDED.payload_hash,updated_at=now()
      WHERE app.msgsite_message_versions.payload_hash<>EXCLUDED.payload_hash
    RETURNING revision INTO revision_no;
  IF revision_no IS NULL THEN RETURN; END IF;
  INSERT INTO app.outbox_events(aggregate_type,aggregate_id,event_type,payload,exchange_name,routing_key)
    VALUES('msgsite_message',target_id,'message.snapshot',jsonb_build_object(
      'schemaVersion',1,'eventType','message.snapshot',
      'eventId','crm-msgsite:'||target_id||':'||revision_no,'workspaceId',item.workspace_id::text,
      'revision',revision_no::text,'emittedAt',clock_timestamp(),'message',snapshot,'presentation',profile),
      exchange,'crm.message.snapshot.v1');
END $$;