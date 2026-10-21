"""Synthetic transport faults with the real transaction/receipt writer."""
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from crm_to_chat.consume import (IO_WAIT_SECONDS, PREFETCH_COUNT, ProjectionFailure,
                                 receive_with, run, subscribe)
from crm_to_chat.errors import IntegrationError
from crm_to_chat.rabbitmq import Broker, brokers, connect_broker
from crm_to_chat.writer import ChatWriter
from helpers import encoded, fixture
from test_cutover import Connection

PRIMARY = 'amqps://fixture:fixture@new.example.test/%2F'


class Stop:
    def __init__(self, rounds=4): self.rounds = rounds; self.waits = []
    def is_set(self): return self.rounds <= 0
    def wait(self, seconds): self.waits.append(seconds); self.rounds -= 1


class SingleBrokerTests(unittest.TestCase):
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

    def test_insecure_configuration_rejected(self):
        for args in (('amqp://public.example.test/',),
                     (PRIMARY + '?ssl_options=unsafe',),
                     ('amqp://localhost/', 'rabbitmq-fixture')):
            with self.subTest(args=args), self.assertRaises(IntegrationError):
                brokers(*args)

    def test_duplicate_and_stale_revision_commit_before_ack(self):
        db = Connection()
        writer = ChatWriter(db)
        first, second = Mock(), Mock()
        # ACK observes the persisted receipt, never an uncommitted application.
        def ack(**_):
            self.assertFalse(db.db.in_transaction)
            self.assertGreater(db.db.execute('SELECT COUNT(*) FROM crm_event_receipt').fetchone()[0], 0)
        first.basic_ack.side_effect = second.basic_ack.side_effect = ack
        primary = receive_with(writer, ('1',), 'primary')
        drain = receive_with(writer, ('1',), 'primary')
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
        receive = receive_with(writer, ('1',), 'primary')
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
            receive_with(writer, ('1',), 'primary')(retry, method, None, encoded(fixture()))
        self.assertEqual(db.db.execute('SELECT COUNT(*) FROM crm_event_receipt').fetchone()[0], 1)
        self.assertEqual(db.db.execute('SELECT COUNT(*) FROM crm_contact_response').fetchone()[0], 1)
        retry.basic_ack.assert_called_once_with(delivery_tag=10)

    def rabbit(self):
        rabbit = Mock()
        rabbit.is_open = True
        return rabbit

    def test_one_transport_one_writer_and_commit_before_ack(self):
        db = Connection()
        db.close = Mock()
        rabbit = self.rabbit()
        def pump(time_limit):
            callback = rabbit.channel().basic_consume.call_args.kwargs['on_message_callback']
            callback(rabbit.channel(), SimpleNamespace(delivery_tag=3), None, encoded(fixture()))
        rabbit.process_data_events.side_effect = pump
        factory = Mock(return_value=db)
        connect = Mock(return_value=rabbit)
        with redirect_stdout(StringIO()):
            run(factory, PRIMARY, stop=Stop(3), rabbit_connect=connect)
        connect.assert_called_once()
        self.assertEqual(brokers(PRIMARY), (Broker('primary', PRIMARY),))
        factory.assert_called_once()
        self.assertGreater(rabbit.channel().basic_ack.call_count, 0)
        rabbit.close.assert_called_once()
        self.assertEqual(db.db.execute('SELECT COUNT(*) FROM crm_event_receipt').fetchone()[0], 1)
        db.close.assert_called_once()

    def test_transport_failure_reconnects_same_source(self):
        primary, recovered = self.rabbit(), self.rabbit()
        primary.process_data_events.side_effect = ConnectionError('synthetic')
        connect = Mock(side_effect=[primary, recovered])
        ticks = iter(range(0, 1000, 11))
        with redirect_stdout(StringIO()):
            run(Mock(), PRIMARY, stop=Stop(5), rabbit_connect=connect, clock=lambda: next(ticks))
        self.assertEqual(connect.call_count, 2)
        self.assertEqual(connect.call_args_list[0], connect.call_args_list[1])
        self.assertGreater(recovered.process_data_events.call_count, 0)

    def test_db_failure_closes_transport_without_ack(self):
        primary = self.rabbit()
        primary.process_data_events.side_effect = ProjectionFailure()
        with redirect_stdout(StringIO()):
            run(Mock(), PRIMARY, stop=Stop(2), rabbit_connect=lambda source: primary)
        primary.close.assert_called_once()
        primary.channel().basic_ack.assert_not_called()

    def test_pre_stopped_run_never_opens_database_or_broker(self):
        factory, connect = Mock(), Mock()
        run(factory, PRIMARY, stop=Stop(0), rabbit_connect=connect)
        factory.assert_not_called()
        connect.assert_not_called()

    def test_connected_pump_waits_for_io_without_sleeping_between_deliveries(self):
        rabbit, stop = self.rabbit(), Stop(4)
        with redirect_stdout(StringIO()):
            run(Mock(), PRIMARY, stop=stop, rabbit_connect=lambda _: rabbit)
        self.assertGreater(rabbit.process_data_events.call_count, 0)
        self.assertTrue(all(c.kwargs['time_limit'] > 0
                            for c in rabbit.process_data_events.call_args_list))
        self.assertEqual(stop.waits[:-1], [0] * (len(stop.waits) - 1))
        self.assertLessEqual(IO_WAIT_SECONDS, 1)
        rabbit.channel().basic_qos.assert_called_once_with(prefetch_count=PREFETCH_COUNT)
        self.assertGreater(PREFETCH_COUNT, 1)
        self.assertLessEqual(PREFETCH_COUNT, 16)

    def test_failed_connection_waits_instead_of_busy_looping(self):
        stop = Stop(4)
        with redirect_stdout(StringIO()):
            run(Mock(), PRIMARY, stop=stop, rabbit_connect=Mock(side_effect=ConnectionError()))
        self.assertTrue(all(seconds > 0 for seconds in stop.waits))

    def test_timings_record_no_payload_and_preserve_commit_before_ack(self):
        db, channel = Connection(), Mock()
        def ack(**_):
            self.assertFalse(db.db.in_transaction)
        channel.basic_ack.side_effect = ack
        output = StringIO()
        with redirect_stdout(output):
            receive_with(ChatWriter(db), ('1',), 'primary')(
                channel, SimpleNamespace(delivery_tag=1, redelivered=True), None, encoded(fixture()))
        import json
        record = json.loads(output.getvalue())
        self.assertEqual(record['result'], 'applied')
        self.assertTrue(record['redelivered'])
        for key in ['parseMs', 'writeMs', 'ackMs', 'snapshotAgeMs']:
            self.assertGreaterEqual(record[key], 0)
        self.assertNotIn('message', record)
        self.assertNotIn('eventId', record)

    def test_prefetched_tail_stays_recoverable_after_database_failure(self):
        db, channel = Connection(), Mock()
        writer = ChatWriter(db)
        events = [encoded(fixture(event_id=f'window-{i}', message_id=str(1001+i)))
                  for i in range(PREFETCH_COUNT)]
        calls = 0
        def apply(event):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('synthetic database failure')
            return writer.apply(event)
        receive = receive_with(SimpleNamespace(apply=apply), ('1',), 'primary')
        with redirect_stdout(StringIO()):
            with self.assertRaises(ProjectionFailure):
                for i, body in enumerate(events):
                    receive(channel, SimpleNamespace(delivery_tag=i+1), None, body)
            self.assertEqual(channel.basic_ack.call_count, 1)
            self.assertEqual(db.db.execute('SELECT COUNT(*) FROM crm_event_receipt').fetchone()[0], 1)
            # Simulate broker redelivery of the entire window after reconnect.
            retry = receive_with(writer, ('1',), 'primary')
            for i, body in enumerate(events):
                retry(channel, SimpleNamespace(delivery_tag=i+1, redelivered=True), None, body)
        self.assertEqual(db.db.execute('SELECT COUNT(*) FROM crm_event_receipt').fetchone()[0], PREFETCH_COUNT)
        self.assertEqual(db.db.execute('SELECT COUNT(*) FROM crm_contact_response').fetchone()[0], PREFETCH_COUNT)


if __name__ == '__main__': unittest.main()
