"""Transactional CRM projection into an independent chat_db message partition."""
import html
import json
from datetime import datetime, timedelta, timezone
from .contracts import CustomerAvatarEvent
from .errors import ContractError


def site_time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(
        timezone(timedelta(hours=8))).replace(tzinfo=None)


def row_values(event):
    m = event.data['message']
    p = event.data.get('presentation', {})
    customer = m['customerId']
    # Unowned messages stay in projection state without becoming a public timeline.
    conversation = f'crm_{customer}' if customer else f'crm_unlinked_{m["conversationId"]}'
    attachments = [{'id': a['index'], 'file_type': a['type'],
                    'data_url': f'media:message/{event.message_id}/{a["index"]}',
                    'crm_resource_id': f'message/{event.message_id}/{a["index"]}',
                    'file_name': a.get('fileName')} for a in m['attachments']]
    text = '[已删除]' if m['deleted'] else html.escape(m['text'] or '').replace('\n', '<br>')
    return {'msg_id': event.message_id, 'reply_to_id': m['replyToMessageId'],
            'conversation_id': conversation, 'is_empty': not text and not attachments,
            'contact_avatar': p.get('customerAvatar') or '', 'contact_id': customer or 0,
            'contact': (p.get('customerName') if m['direction'] == 'inbound' else p.get('accountName')) or 'CRM',
            'role': int(m['direction'] == 'inbound'), 'content': text,
            'attachment': json.dumps(attachments, ensure_ascii=False), 'source_res_id': None,
            'create_date': site_time(m['occurredAt']), 'update_date': site_time(m['updatedAt']),
            'message_type': 'incoming' if m['direction'] == 'inbound' else 'outgoing',
            'content_attribute': json.dumps({'crm': {'messageId': event.message_id,
                'conversationId': m['conversationId'], 'customerId': customer,
                'channelAccountId': m['channelAccountId'], 'channel': m['channel'],
                'status': m.get('status')}, 'presentation': p}, ensure_ascii=False),
            'workspace_id': event.workspace_id, 'crm_conversation_id': m['conversationId'],
            'crm_customer_id': customer, 'crm_channel_account_id': m['channelAccountId'],
            'revision': event.revision, 'snapshot_hash': event.message_fingerprint,
            'deleted': m['deleted']}


class ChatWriter:
    def __init__(self, connection, *, customer_avatar_events=False):
        self.connection = connection
        self.customer_avatar_events = customer_avatar_events

    def apply(self, event):
        c = self.connection
        c.begin()
        try:
            with c.cursor() as q:
                q.execute('SELECT event_hash FROM crm_event_receipt WHERE workspace_id=%s AND event_id=%s FOR UPDATE',
                          (event.workspace_id, event.event_id))
                receipt = q.fetchone()
                if receipt:
                    if receipt['event_hash'] != event.fingerprint:
                        raise ContractError('event_id_conflict')
                    c.commit()
                    return 'duplicate'
                if isinstance(event, CustomerAvatarEvent):
                    if not self.customer_avatar_events:
                        raise ContractError('unsupported_event_type')
                    outcome = self.apply_customer_avatar(q, event)
                else:
                    outcome = self.apply_snapshot(q, event)
                q.execute('INSERT INTO crm_event_receipt (workspace_id,event_id,event_hash) VALUES (%s,%s,%s)',
                          (event.workspace_id, event.event_id, event.fingerprint))
            c.commit()
            return outcome
        except Exception:
            c.rollback()
            raise

    @staticmethod
    def apply_customer_avatar(q, event):
        keys = (event.workspace_id, event.customer_id)
        q.execute('SELECT revision FROM crm_customer_avatar WHERE workspace_id=%s AND customer_id=%s FOR UPDATE', keys)
        previous = q.fetchone()
        if previous and previous['revision'] >= event.revision:
            return 'stale'
        avatar = event.data['avatarUrl']
        if previous:
            q.execute('UPDATE crm_customer_avatar SET revision=%s,avatar_url=%s '
                      'WHERE workspace_id=%s AND customer_id=%s', (event.revision, avatar, *keys))
        else:
            q.execute('INSERT INTO crm_customer_avatar (revision,avatar_url,workspace_id,customer_id) '
                      'VALUES (%s,%s,%s,%s)', (event.revision, avatar, *keys))
        q.execute('UPDATE chatwoot_conversation_update SET customer_avatar=%s '
                  'WHERE conversation_id=%s AND table_id=7 AND msg_source_type=11 AND contact_id=%s '
                  'AND EXISTS (SELECT 1 FROM crm_contact_response '
                  'WHERE id=chatwoot_conversation_update.last_contact_response_id '
                  'AND workspace_id=%s AND crm_customer_id=%s AND deleted=0)',
                  (avatar or '', f'crm_{event.customer_id}', event.customer_id, *keys))
        return 'applied'

    def apply_snapshot(self, q, event):
        values = row_values(event)
        q.execute('SELECT conversation_id,revision,snapshot_hash,workspace_id FROM crm_contact_response '
                  'WHERE msg_id=%s FOR UPDATE', (event.message_id,))
        previous = q.fetchone()
        if previous and str(previous['workspace_id']) != event.workspace_id:
            raise ContractError('message_workspace_conflict')
        if previous and previous['revision'] >= event.revision:
            if previous['revision'] > event.revision:
                return 'stale'
            if previous['snapshot_hash'] != values['snapshot_hash']:
                raise ContractError('revision_conflict')
            return 'unchanged'
        columns = list(values)
        q.execute('INSERT INTO crm_contact_response (' + ','.join(columns) + ') VALUES ('
                  + ','.join(['%s'] * len(columns)) + ') ON DUPLICATE KEY UPDATE '
                  + ','.join(f'{col}=VALUES({col})' for col in columns if col != 'msg_id'),
                  [values[col] for col in columns])
        affected = {values['conversation_id']}
        if previous:
            affected.add(previous['conversation_id'])
        for conversation in sorted(affected):
            if conversation.startswith('crm_') and not conversation.startswith('crm_unlinked_'):
                self.refresh_summary(q, conversation)
        return 'applied'

    def refresh_summary(self, q, conversation):
        # Only CRM-owned fields change. Existing no_need_reply, groups and labels survive.
        q.execute('SELECT COUNT(*) AS n,MIN(create_date) AS start_time FROM crm_contact_response '
                  'WHERE conversation_id=%s AND deleted=0', (conversation,))
        aggregate = q.fetchone()
        q.execute('SELECT * FROM crm_contact_response WHERE conversation_id=%s AND deleted=0 '
                  'ORDER BY create_date DESC,msg_id DESC LIMIT 1', (conversation,))
        latest = q.fetchone()
        if not latest:
            q.execute('UPDATE chatwoot_conversation_update SET msg_count=0 WHERE conversation_id=%s', (conversation,))
            return
        p = json.loads(latest['content_attribute'])['presentation']
        avatar = p.get('customerAvatar')
        if self.customer_avatar_events:
            q.execute('SELECT avatar_url FROM crm_customer_avatar WHERE workspace_id=%s AND customer_id=%s',
                      (latest['workspace_id'], latest['crm_customer_id']))
            profile = q.fetchone()
            if profile:
                avatar = profile['avatar_url']
        q.execute('INSERT INTO chatwoot_conversation_update (conversation_id,msg_count,table_id,last_role,'
                  'last_contact_response_id,income_name,customer_avatar,outgo_name,contact_id,inbox_name,'
                  'msg_source_type,msg_source_name,start_time,update_date) VALUES (%s,%s,7,%s,%s,%s,%s,%s,%s,%s,11,\'\',%s,%s) '
                  'ON DUPLICATE KEY UPDATE msg_count=VALUES(msg_count),table_id=7,last_role=VALUES(last_role),'
                  'last_contact_response_id=VALUES(last_contact_response_id),income_name=VALUES(income_name),'
                  'customer_avatar=VALUES(customer_avatar),outgo_name=VALUES(outgo_name),contact_id=VALUES(contact_id),'
                  'inbox_name=VALUES(inbox_name),msg_source_type=11,start_time=VALUES(start_time),update_date=VALUES(update_date)',
                  (conversation, aggregate['n'], latest['role'], latest['id'], (p.get('accountName') or 'CRM')[:100],
                   (avatar or '')[:600], (p.get('customerName') or 'CRM')[:100],
                   latest['crm_customer_id'], (p.get('accountName') or 'CRM')[:80],
                   aggregate['start_time'], latest['create_date']))
