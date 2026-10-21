from contextlib import redirect_stdout
from io import StringIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crm_to_chat.cli import main
from crm_to_chat.config import bridge_token, enforce_preview_only, observer_config
from crm_to_chat.errors import IntegrationError
from helpers import encoded, fixture


class SafetyTests(unittest.TestCase):
    def test_write_enable_is_always_rejected(self):
        for setting in ("CRM_TO_CHAT_WRITE_ENABLED", "CHAT_DB_WRITE_ENABLED"):
            with self.subTest(setting=setting), self.assertRaisesRegex(IntegrationError, "chat_db_writes_not_supported"):
                enforce_preview_only({setting: "true"})
        output = StringIO()
        with patch.dict(os.environ, {"CRM_TO_CHAT_WRITE_ENABLED": "true"}, clear=True), redirect_stdout(output):
            self.assertEqual(main(["check"]), 2)
        self.assertIn("chat_db_writes_not_supported", output.getvalue())

    def test_no_default_exchange_wildcard_or_insecure_remote_broker(self):
        base = {"CRM_TO_CHAT_AMQP_URL": "amqps://fixture:fixture@broker.example.test/%2F",
                "CRM_TO_CHAT_EXCHANGE": "crm.events"}
        observer_config(base)
        for changed in ({"CRM_TO_CHAT_EXCHANGE": ""}, {"CRM_TO_CHAT_EXCHANGE": "amq.direct"},
                        {"CRM_TO_CHAT_ROUTING_KEY": "#"},
                        {"CRM_TO_CHAT_AMQP_URL": "amqp://broker.example.test"},
                        {"CRM_TO_CHAT_AMQP_URL": "amqps://broker.example.test/?ssl_options=unsafe"}):
            with self.subTest(changed=changed), self.assertRaises(IntegrationError):
                observer_config({**base, **changed})

    def test_offline_modes_never_open_network_and_logs_exclude_business_content(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_bytes(encoded(fixture()) + b"\n")
            output = StringIO()
            with patch.dict(os.environ, {}, clear=True), patch("socket.create_connection", side_effect=AssertionError("network forbidden")), redirect_stdout(output):
                self.assertEqual(main(["check"]), 0)
                self.assertEqual(main(["preview", "--input", str(path)]), 0)
            self.assertNotIn("Synthetic message", output.getvalue())
            self.assertNotIn("fixture.jpg", output.getvalue())
            self.assertNotIn("https://", output.getvalue())

    def test_corrupt_input_skips_without_echoing_secret_and_keeps_later_valid_event(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_bytes(b'{"private":"fixture-only-secret"}\n' + encoded(fixture()) + b"\n")
            output = StringIO()
            with patch.dict(os.environ, {}, clear=True), redirect_stdout(output):
                self.assertEqual(main(["preview", "--input", str(path)]), 2)
            self.assertNotIn("fixture-only-secret", output.getvalue())
            self.assertIn('"applied":1', output.getvalue())

    def test_gateway_startup_requires_both_tokens_before_binding(self):
        output = StringIO()
        with patch.dict(os.environ, {}, clear=True), patch("crm_to_chat.cli.make_server") as server, redirect_stdout(output):
            self.assertEqual(main(["serve"]), 2)
            server.assert_not_called()
        with self.assertRaises(IntegrationError):
            bridge_token({})
