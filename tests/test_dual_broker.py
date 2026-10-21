"""Synthetic transport faults with the real transaction/receipt writer."""
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from crm_to_chat.consume import ProjectionFailure, receive_with, run, subscribe
from crm_to_chat.errors import IntegrationError
from crm_to_chat.rabbitmq import Broker, brokers, connect_broker
from crm_to_chat.writer import ChatWriter
from helpers import encoded, fixture
from test_cutover import Connection

PRIMARY = 'amqps://fixture:fixture@new.example.test/%2F'
DRAIN = 'amqp://fixture:fixture@127.0.0.1:35672/%2F'


class Stop:
    def __init__(self, rounds=4): self.rounds = rounds
    def is_set(self): return self.rounds <= 0
    def wait(self, seconds): self.rounds -= 1


class DualBrokerTests(unittest.TestCase):
    def test_ali_tls_properties_and_sanitized_failure(self):
        pika = Mock()
        params = SimpleNamespace(host='new.example.test')
        pika.URLParameters.return_value = params
        pika.SSLOptions.side_effect = lambda ctx, host: SimpleNamespace(context=ctx, host=host)
        with patch.dict('sys.modules', {'pika': pika}):
            connect_broker(Broker('primary', PRIMARY, 'rabbitmq-fixture'))
            self.assertTrue(params.ssl_options.context.check_hostname)
            self.assertEqual(params.client_properties['connection_name'], '{__rabbitmq-fixture__}')
            self.assertEqual(params.client_properties['aliyun_rabbitmq_instance_id'], 'rabbitmq-fixture')
            pika.BlockingConnection.side_effect = RuntimeError('fixture-password')
            with self.assertRaisesRegex(IntegrationError, '^rabbitmq_connection_failed$'):
                connect_broker(Broker('primary', PRIMARY))

    def test_duplicate_endpoint_and_incomplete_or_insecure_configuration_rejected(self):
        for args in ((PRIMARY, '', 'amqps://other:other@NEW.example.test:5671/'),
                     (PRIMARY, '', '', 'rabbitmq-fixture'),
                     (DRAIN, 'rabbitmq-fixture'),
                     ('amqp://public.example.test/',),
                     (PRIMARY + '?ssl_options=unsafe',)):
            with self.subTest(args=args), self.assertRaises(IntegrationError):
                brokers(*args)

    def test_cross_broker_duplicate_and_stale_revision_commit_before_each_source_ack(self):
        db = Connection()
        writer = ChatWriter(db)
        first, second = Mock(), Mock()
        # ACK observes the persisted receipt, never an uncommitted application.
        def ack(**_):
            self.assertFalse(db.db.in_transaction)
            self.assertGreater(db.db.execute('SELECT COUNT(*) FROM crm_event_receipt').fetchone()[0], 0)
        first.basic_ack.side_effect = second.basic_ack.side_effect = ack
        primary = receive_with(writer, ('1',), 'primary')
        drain = receive_with(writer, ('1',), 'drain')
        method = SimpleNamespace(delivery_tag=7)
        with redirect_stdout(StringIO()):
            primary(first, method, None, encoded(fixture(event_id='new', revision='2')))
            drain(second, method, None, encoded(fixture(event_id='new', revision='2')))
            drain(second, method, None, encoded(fixture(event_id='older', revision='1')))
        self.assertEqual(db.db.execute('SELECT revision FROM crm_contact_response').fetchone()[0], 2)
        self.assertEqual(db.db.execute('SELECT COUNT(*) FROM crm_contact_response').fetchone()[0], 1)
        self.assertEqual(first.basic_ack.call_count, 1)
        self.assertEqual(second.basic_ack.call_count, 2)

    def test_db_failure_not_acked_and_invalid_or_out_of_scope_dead_lettered(self):
        writer, channel = Mock(), Mock()
        writer.apply.side_effect = RuntimeError('synthetic database failure')
        receive = receive_with(writer, ('1',), 'drain')
        method = SimpleNamespace(delivery_tag=9)
        with self.assertRaises(ProjectionFailure):
            receive(channel, method, None, encoded(fixture()))
        channel.basic_ack.assert_not_called()
        channel.basic_nack.assert_not_called()
        with redirect_stdout(StringIO()):
            receive(channel, method, None, b'not-json')
            receive(channel, method, None, encoded(fixture(workspace_id='2')))
        self.assertEqual(channel.basic_nack.call_count, 2)
        channel.basic_nack.assert_called_with(delivery_tag=9, requeue=False)

    def test_ack_transport_failure_retries_committed_event_as_duplicate(self):
        db = Connection()
        writer = ChatWriter(db)
        first, retry = Mock(), Mock()
        first.basic_ack.side_effect = ConnectionError('synthetic transport failure')
        method = SimpleNamespace(delivery_tag=10)
        with redirect_stdout(StringIO()):
            with self.assertRaises(ConnectionError):
                receive_with(writer, ('1',), 'primary')(first, method, None, encoded(fixture()))
            receive_with(writer, ('1',), 'drain')(retry, method, None, encoded(fixture()))
        self.assertEqual(db.db.execute('SELECT COUNT(*) FROM crm_event_receipt').fetchone()[0], 1)
        self.assertEqual(db.db.execute('SELECT COUNT(*) FROM crm_contact_response').fetchone()[0], 1)
        retry.basic_ack.assert_called_once_with(delivery_tag=10)

    def rabbit(self):
        rabbit = Mock()
        rabbit.is_open = True
        return rabbit

    def test_both_sources_share_one_writer_and_independent_ack_channels(self):
        db = Connection()
        db.close = Mock()
        connections = {'primary': self.rabbit(), 'drain': self.rabbit()}
        applied = []
        def pump(role):
            callback = connections[role].channel().basic_consume.call_args.kwargs['on_message_callback']
            callback(connections[role].channel(), SimpleNamespace(delivery_tag=3), None, encoded(fixture()))
            applied.append(role)
        for role, rabbit in connections.items():
            rabbit.process_data_events.side_effect = lambda time_limit, role=role: pump(role)
        factory = Mock(return_value=db)
        with redirect_stdout(StringIO()):
            run(factory, PRIMARY, drain_url=DRAIN, stop=Stop(3),
                rabbit_connect=lambda source: connections[source.role])
        factory.assert_called_once()
        self.assertEqual(set(applied), {'primary', 'drain'})
        for rabbit in connections.values():
            self.assertGreater(rabbit.channel().basic_ack.call_count, 0)
            rabbit.close.assert_called_once()
        self.assertEqual(db.db.execute('SELECT COUNT(*) FROM crm_event_receipt').fetchone()[0], 1)
        db.close.assert_called_once()

    def test_either_source_can_fail_without_stopping_the_other(self):
        for failed in ('primary', 'drain'):
            with self.subTest(failed=failed):
                healthy = self.rabbit()
                factory = Mock()
                def connect(source):
                    if source.role == failed: raise ConnectionError('synthetic')
                    return healthy
                with redirect_stdout(StringIO()):
                    run(factory, PRIMARY, drain_url=DRAIN, stop=Stop(4), rabbit_connect=connect)
                self.assertGreater(healthy.process_data_events.call_count, 0)
                factory.assert_called_once()

    def test_transport_failure_reconnects_only_failed_source(self):
        primary, drain, recovered = self.rabbit(), self.rabbit(), self.rabbit()
        primary.process_data_events.side_effect = ConnectionError('synthetic')
        attempts = {'primary': 0, 'drain': 0}
        def connect(source):
            attempts[source.role] += 1
            return drain if source.role == 'drain' else primary if attempts['primary'] == 1 else recovered
        # Clock advances enough to exercise retry without any wall-clock sleep.
        ticks = iter(range(0, 1000, 11))
        with redirect_stdout(StringIO()):
            run(Mock(), PRIMARY, drain_url=DRAIN, stop=Stop(5),
                rabbit_connect=connect, clock=lambda: next(ticks))
        self.assertEqual(attempts, {'primary': 2, 'drain': 1})
        self.assertGreater(drain.process_data_events.call_count, 0)
        self.assertGreater(recovered.process_data_events.call_count, 0)

    def test_db_failure_closes_both_transports_without_ack(self):
        primary, drain = self.rabbit(), self.rabbit()
        primary.process_data_events.side_effect = ProjectionFailure()
        stop = Stop(2)
        with redirect_stdout(StringIO()):
            run(Mock(), PRIMARY, drain_url=DRAIN, stop=stop,
                rabbit_connect=lambda source: primary if source.role == 'primary' else drain)
        primary.close.assert_called_once()
        drain.close.assert_called_once()
        primary.channel().basic_ack.assert_not_called()
        drain.channel().basic_ack.assert_not_called()

    def test_pre_stopped_run_never_opens_database_or_broker(self):
        factory, connect = Mock(), Mock()
        run(factory, PRIMARY, stop=Stop(0), rabbit_connect=connect)
        factory.assert_not_called()
        connect.assert_not_called()


if __name__ == '__main__': unittest.main()
