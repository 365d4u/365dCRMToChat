import unittest
from crm_to_chat.environment import mysql_config


class EnvironmentTests(unittest.TestCase):
    def test_original_environment_remains_supported(self):
        values = dict(CONV_DB_HOST='fixture', CONV_DB_USER='fixture',
                      CONV_DB_PASSWORD='synthetic', CONV_DB_NAME='fixture_chat')
        self.assertEqual(mysql_config(values)['database'], 'fixture_chat')
        self.assertEqual(mysql_config(values)['port'], 3306)

    def test_target_uses_explicit_chat_database_not_primary_respond_database(self):
        values = dict(CRM_TO_CHAT_DB_ENV_STYLE='respond', DB_HOST='fixture', DB_PORT='13306',
                      DB_USER='fixture', DB_PASSWORD='synthetic', DB_NAME='wrong_primary',
                      CHAT_DB_NAME='fixture_chat')
        result = mysql_config(values)
        self.assertEqual(result['database'], 'fixture_chat')
        self.assertEqual(result['port'], 13306)
        del values['CHAT_DB_NAME']
        with self.assertRaisesRegex(ValueError, 'runtime configuration missing'):
            mysql_config(values)

    def test_unknown_style_rejected_without_echoing_values(self):
        with self.assertRaisesRegex(ValueError, '^Unknown CRM_TO_CHAT_DB_ENV_STYLE$'):
            mysql_config({'CRM_TO_CHAT_DB_ENV_STYLE': 'unknown_secret_value'})
