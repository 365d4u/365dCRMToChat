import unittest
from unittest.mock import MagicMock

from crm_to_chat.backfill_legacy_links import insert_missing, plan_missing


class LegacyLinkBackfillTests(unittest.TestCase):
    def test_requires_consistent_aliases_for_unmatched_legacy_conversations(self):
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [{'conversation_id': key} for key in ('legacy-ok', 'legacy-conflict', 'rd_93')],
            [{'chatwoot_conv_id': conversation, 'respond_conv_id': respond}
             for conversation, respond in [('legacy-ok', '40'), ('legacy-conflict', '40'),
                                           ('legacy-conflict', '41'), ('rd_93', '40'),
                                           ('legacy-already-linked', '40')]],
        ]
        links, stats = plan_missing(cursor, {'40': ('100', '50', '1'), '41': ('101', '51', '1')})
        self.assertEqual(set(links), {'legacy-ok'})
        self.assertEqual(links['legacy-ok'][0], '100')
        self.assertEqual(stats['conflictingHistory'], 1)
        self.assertEqual(stats['unverifiedHistory'], 1)
        self.assertIn('NOT EXISTS', cursor.execute.call_args_list[0].args[0])

    def test_insert_does_not_replace_a_concurrent_association(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.executemany.return_value = 0
        result = insert_missing(connection, {'legacy': ('100', 'proof')})
        self.assertEqual(result, 0)
        sql, records = cursor.executemany.call_args.args
        self.assertIn('conversation_id = crm_conversation_link.conversation_id', sql)
        self.assertEqual(records, [('legacy', '100', 'proof')])
        connection.commit.assert_called_once()
