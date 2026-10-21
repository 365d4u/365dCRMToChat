"""Synthetic policy tests; compile classes without importing production modules."""
import ast
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(r'E:\PycharmProjects\respond_webhook\respond_to_msgsite')


def load_classes(path, context):
    source = ast.parse(path.read_text(encoding='utf-8-sig'))
    classes = [node for node in source.body if isinstance(node, ast.ClassDef)]
    exec(compile(ast.Module(body=classes, type_ignores=[]), str(path), 'exec'), context)
    return context


class LegacyRetirementTests(unittest.TestCase):
    def handler_context(self, configured=None):
        def getenv(name, default=None):
            return configured if name == 'CHAT_DB_WRITE_ENABLED' and configured is not None else default
        return load_classes(ROOT/'service/queue_handle.py', {
            'os': SimpleNamespace(getenv=getenv), 'json': json, 'logger': Mock(),
            'FeishuFollowupSales': Mock(), 'datetime': __import__('datetime').datetime,
        })

    def database_context(self):
        pool = Mock()
        context = load_classes(ROOT/'service/database.py', {
            'PooledDB': pool, 'pymysql': SimpleNamespace(cursors=SimpleNamespace(DictCursor=object)),
            'logger': Mock(), 'DB_HOST': 'fixture', 'DB_PORT': 3306,
            'DB_USER': 'fixture', 'DB_PASSWORD': 'synthetic', 'DB_NAME': 'fixture_chat',
        })
        context['db_manager'] = context['DBManager']()
        return context, pool

    def test_missing_flag_defaults_to_no_writes(self):
        context = self.handler_context()
        self.assertFalse(context['QueueHandler']().chat_db_write_enabled)

    def test_flag_cannot_reenable_retired_writer(self):
        context = self.handler_context('true')
        with self.assertRaisesRegex(ValueError, 'writes are retired'):
            context['QueueHandler']()
        context['FeishuFollowupSales'].assert_not_called()

    def test_direct_dao_write_is_blocked_before_connection(self):
        context, pool = self.database_context()
        values = dict(msg_id=1, conversation_id='rd_fixture', is_empty=False, contact_id=1,
                      contact='synthetic', role=1, create_date='2026-10-12 10:00:00',
                      update_date='2026-10-12 10:00:00', message_type='incoming')
        with self.assertRaisesRegex(RuntimeError, 'writes are retired'):
            context['ContactResponseDAO'].insert_message(values)
        self.assertIsNone(context['db_manager'].pool)
        pool.assert_not_called()

    def test_write_cannot_bypass_through_query_method(self):
        context, pool = self.database_context()
        for sql in ['INSERT INTO fixture VALUES (1)', 'UPDATE fixture SET x=1', 'DELETE FROM fixture']:
            with self.assertRaisesRegex(RuntimeError, 'read-only SELECT'):
                context['db_manager'].execute_query(sql)
        pool.assert_not_called()

    def test_followup_agent_lookup_remains_in_read_only_transaction(self):
        context, pool = self.database_context()
        connection = pool.return_value.connection.return_value
        cursor = connection.cursor.return_value
        cursor.fetchall.return_value = [{'agent_name_daily': 'Synthetic', 'agent_name_night': 'Fixture'}]
        self.assertEqual(context['RespondAllAgentDAO'].get_agent_name('agent@example.invalid', False), 'Synthetic')
        self.assertEqual(cursor.execute.call_args_list[0].args, ('START TRANSACTION READ ONLY',))
        self.assertTrue(cursor.execute.call_args_list[1].args[0].startswith('SELECT '))
        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()
