from types import SimpleNamespace
import ssl
import unittest
from unittest.mock import Mock, patch

from crm_to_chat.observer import connect, observe
from crm_to_chat.preview import PreviewStore
from helpers import encoded, fixture


class ObserverTests(unittest.TestCase):
    def connection(self, deliveries):
        channel = Mock()
        channel.is_open = True
        channel.consume.return_value = iter(deliveries)
        connection = Mock()
        connection.channel.return_value = channel
        return connection, channel

    def test_only_exclusive_copy_queue_is_consumed_and_confirmed(self):
        connection, channel = self.connection([
            (SimpleNamespace(delivery_tag=10), None, encoded(fixture())),
            (SimpleNamespace(delivery_tag=11), None, b"not-json"),
        ])
        reports = []
        with PreviewStore() as store:
            self.assertEqual(observe(connection, "crm.events", "crm.message.snapshot.v1", store,
                                     reports.append, max_messages=2), 2)
        channel.exchange_declare.assert_called_once_with(exchange="crm.events", passive=True)
        declared = channel.queue_declare.call_args.kwargs
        self.assertTrue(declared["queue"].startswith("365dCRMToChat.preview."))
        self.assertTrue(declared["exclusive"])
        self.assertTrue(declared["auto_delete"])
        self.assertFalse(declared["durable"])
        self.assertEqual(channel.consume.call_args.kwargs["queue"], declared["queue"])
        self.assertEqual(channel.queue_bind.call_args.kwargs["queue"], declared["queue"])
        channel.basic_ack.assert_called_once_with(delivery_tag=10)
        channel.basic_reject.assert_called_once_with(delivery_tag=11, requeue=False)
        channel.basic_get.assert_not_called()
        channel.basic_publish.assert_not_called()
        channel.queue_purge.assert_not_called()
        channel.queue_delete.assert_not_called()
        self.assertEqual(reports[1]["outcome"], "rejected")

    def test_storage_failure_is_not_acknowledged(self):
        connection, channel = self.connection([(SimpleNamespace(delivery_tag=10), None, encoded(fixture()))])
        store = Mock()
        store.apply.side_effect = RuntimeError("local storage unavailable")
        with self.assertRaises(RuntimeError):
            observe(connection, "crm.events", "crm.message.snapshot.v1", store, Mock(), max_messages=1)
        channel.basic_ack.assert_not_called()
        channel.basic_reject.assert_not_called()
        channel.cancel.assert_called_once()

    def test_tls_verifies_certificate_without_opening_real_connection(self):
        # Mock the optional package so the test suite needs only the standard library.
        package = Mock()
        params = SimpleNamespace(host="broker.example.test")
        package.URLParameters.return_value = params
        package.SSLOptions.side_effect = lambda context, host: SimpleNamespace(context=context, host=host)
        with patch.dict("sys.modules", {"pika": package}):
            connect("amqps://fixture:fixture@broker.example.test/%2F")
        self.assertTrue(params.ssl_options.context.check_hostname)
        self.assertEqual(params.ssl_options.context.verify_mode, ssl.CERT_REQUIRED)
        package.BlockingConnection.assert_called_once_with(params)
