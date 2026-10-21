import ast
import importlib.util
import json
import re
import sqlite3
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from crm_to_chat.contracts import parse_event, projection
from crm_to_chat.errors import ContractError
from crm_to_chat.writer import ChatWriter, row_values
from helpers import encoded, fixture


class Cursor:
    def __init__(self, connection): self.q = connection.cursor()
    def __enter__(self): return self
    def __exit__(self, *_): self.q.close()
    def execute(self, sql, values=()):
        sql = sql.replace(' FOR UPDATE', '').replace('%s', '?')
        if ' ON DUPLICATE KEY UPDATE ' in sql:
            key = 'msg_id' if 'INSERT INTO crm_contact_response ' in sql else 'conversation_id'
            sql = sql.replace(' ON DUPLICATE KEY UPDATE ', f' ON CONFLICT({key}) DO UPDATE SET ')
            sql = re.sub(r'VALUES\((\w+)\)', r'excluded.\1', sql)
        self.q.execute(sql, values)
    def fetchone(self):
        row = self.q.fetchone()
        return dict(row) if row else None


class Connection:
    def __init__(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        values = row_values(parse_event(encoded(fixture())))
        columns = ','.join(f'{column} '+('INTEGER' if column in {'revision','workspace_id','role','deleted','crm_customer_id'} else 'TEXT') for column in values)
        self.db.executescript('CREATE TABLE crm_contact_response (id INTEGER PRIMARY KEY AUTOINCREMENT,'+columns+',labels TEXT DEFAULT "",UNIQUE(msg_id));'
            'CREATE TABLE crm_event_receipt(workspace_id TEXT,event_id TEXT,event_hash TEXT,PRIMARY KEY(workspace_id,event_id));'
            'CREATE TABLE chatwoot_conversation_update(conversation_id TEXT PRIMARY KEY,msg_count INT,table_id INT,last_role INT,'
            'last_contact_response_id INT,income_name TEXT,customer_avatar TEXT,outgo_name TEXT,contact_id TEXT,inbox_name TEXT,'
            'msg_source_type INT,msg_source_name TEXT,start_time TEXT,update_date TEXT,no_need_reply INT DEFAULT 0);')
    def cursor(self): return Cursor(self.db)
    def begin(self): self.db.execute('BEGIN')
    def commit(self): self.db.commit()
    def rollback(self): self.db.rollback()


class CutoverTests(unittest.TestCase):
    def test_customer_owns_timeline_and_channel_conversation_is_preserved(self):
        event = parse_event(encoded(fixture()))
        self.assertEqual(projection(event)['identity']['conversationKey'], 'crm_3001')
        self.assertEqual(row_values(event)['crm_conversation_id'], '2001')
        self.assertEqual(row_values(event)['conversation_id'], 'crm_3001')

    def test_unlinked_customer_does_not_create_wrong_jump(self):
        data = fixture(); data['message']['customerId'] = None
        event = parse_event(encoded(data))
        self.assertIsNone(projection(event)['crmUrl'])
        self.assertEqual(row_values(event)['conversation_id'], 'crm_unlinked_2001')

    def test_html_is_escaped_and_media_ids_not_expiring_urls(self):
        data = fixture(); data['message']['text'] = '<script>alert(1)</script>\nHello'
        values = row_values(parse_event(encoded(data)))
        self.assertNotIn('<script>', values['content'])
        self.assertIn('<br>', values['content'])
        self.assertEqual(json.loads(values['attachment'])[0]['data_url'], 'media:message/1001/0')

    def test_writer_duplicate_stale_conflict_and_manual_flag(self):
        c = Connection(); writer = ChatWriter(c)
        event = parse_event(encoded(fixture()))
        self.assertEqual(writer.apply(event), 'applied')
        self.assertEqual(writer.apply(event), 'duplicate')
        c.db.execute('UPDATE chatwoot_conversation_update SET no_need_reply=1'); c.commit()
        second = fixture(event_id='2', revision='2');second['message']['text']='Edited'
        self.assertEqual(writer.apply(parse_event(encoded(second))), 'applied')
        stale = fixture(event_id='late')
        self.assertEqual(writer.apply(parse_event(encoded(stale))), 'stale')
        conflict = fixture(event_id='conflict', revision='2')
        with self.assertRaises(ContractError): writer.apply(parse_event(encoded(conflict)))
        self.assertEqual(c.db.execute('SELECT COUNT(*) FROM crm_event_receipt WHERE event_id="conflict"').fetchone()[0], 0)
        row = c.db.execute('SELECT * FROM chatwoot_conversation_update').fetchone()
        self.assertEqual(row['msg_count'],1); self.assertEqual(row['no_need_reply'],1)

    def test_ownership_move_and_tombstone(self):
        c=Connection();writer=ChatWriter(c);writer.apply(parse_event(encoded(fixture())))
        move=fixture(event_id='move',revision='2');move['message']['customerId']='3002'
        writer.apply(parse_event(encoded(move)))
        self.assertEqual(c.db.execute('SELECT msg_count FROM chatwoot_conversation_update WHERE conversation_id="crm_3001"').fetchone()[0],0)
        deleted=fixture(event_id='delete',revision='3');deleted['message'].update(customerId='3002',deleted=True,text=None,attachments=[])
        writer.apply(parse_event(encoded(deleted)))
        self.assertEqual(c.db.execute('SELECT msg_count FROM chatwoot_conversation_update WHERE conversation_id="crm_3002"').fetchone()[0],0)
        self.assertEqual(c.db.execute('SELECT deleted FROM crm_contact_response').fetchone()[0],1)

    def test_old_consumer_no_chat_db_calls_but_followup_and_forward_remain(self):
        path=Path(r'E:\PycharmProjects\respond_webhook\respond_to_msgsite\service\queue_handle.py')
        module=ast.parse(path.read_text(encoding='utf-8'))
        cls=next(node for node in module.body if isinstance(node,ast.ClassDef) and node.name=='QueueHandler')
        forbidden=Mock(); forbidden.get_id_by_msg_id.side_effect=AssertionError('chat_db accessed')
        context={'os':SimpleNamespace(getenv=lambda *args: 'false'), 'json':json,'logger':Mock(),
            'ContactResponseDAO':forbidden,'RespondConvMapDAO':forbidden,'MapConversationRespondDAO':forbidden,
            'AttachUploadHistoryDAO':forbidden,'ChatwootConversationUpdateDAO':forbidden,
            'FeishuFollowupSales':Mock(),'datetime':__import__('datetime').datetime}
        exec(compile(ast.Module(body=[cls],type_ignores=[]),str(path),'exec'),context)
        handler=context['QueueHandler']();handler._publish_forward_payload=Mock()
        handler.handle_data({'message_id':'9001','contact_id':'8001','event_type':'message.sent','content':'test #fw',
                             'channel_id':'7001','channel_name':'fixture','msg_time':'2026-10-12 10:00:00',
                             'attach_map_list':[{'msg_id':'9001'}]})
        self.assertEqual(forbidden.mock_calls,[])
        handler._publish_forward_payload.assert_called_once()
        handler.feishu_followup.process_message.assert_called_once()

    def test_display_links_require_canonical_or_verified_customer(self):
        path=Path(r'E:\PycharmProjects\chatwoot_message\service\crm_identity.py')
        spec=importlib.util.spec_from_file_location('identity_test',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertIsNone(module.decorate({'conversation_id':'rd_3001','respond_conv_id':'3001'})['crm_url'])
        self.assertEqual(module.decorate({'conversation_id':'rd_9001'},'3001')['crm_url'],'https://crm.365d4u.com/inbox/3001')
        self.assertEqual(module.decorate({'conversation_id':'crm_3002'},'9999')['crm_customer_id'],'3002')
