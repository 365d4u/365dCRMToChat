"""Explicit synthetic AMQP probe; never loads runtime env or business consumers.

Called only by an operator supplying a new connection helper and config in memory.
No database or production queue name is used.
"""
import hashlib
import json
import time
import uuid


def probe(connect, broker, count=100):
    import pika
    name = 'codex.probe.' + uuid.uuid4().hex
    dlq, direct, topic = name + '.invalid', name + '.direct', name + '.topic'
    result = {'runId': name.rsplit('.', 1)[1], 'synthetic': True, 'normalMessages': count,
              'duplicates': 0, 'corruptBodies': 0, 'cleanup': {}, 'passed': False}
    opened = []
    publisher = consumer = None
    stage = 'connect'
    def connection():
        rabbit = connect(broker)
        opened.append(rabbit)
        return rabbit
    def await_message(rabbit, queue):
        channel = rabbit.channel()
        channel.basic_qos(prefetch_count=1)
        items = []
        channel.basic_consume(queue, lambda ch, method, prop, body: items.append((method, prop, body)), auto_ack=False)
        deadline = time.monotonic() + 10
        while not items and time.monotonic() < deadline:
            rabbit.process_data_events(time_limit=0.05)
        if len(items) != 1: raise RuntimeError('synthetic_delivery_missing_or_duplicate')
        return (channel, *items[0])
    def stats(values):
        values = sorted(values)
        return {'count': len(values), 'p50Ms': round(values[int((len(values)-1)*.5)], 2),
                'p95Ms': round(values[int((len(values)-1)*.95)], 2), 'maxMs': round(max(values), 2)}
    try:
        start = time.monotonic()
        producer = connection()
        result['connectionMs'] = round((time.monotonic() - start)*1000, 2)
        publisher = producer.channel()
        publisher.confirm_delivery()
        stage = 'topology'
        publisher.exchange_declare(direct, exchange_type='direct', durable=True)
        publisher.exchange_declare(topic, exchange_type='topic', durable=True)
        publisher.queue_declare(dlq, durable=True)
        publisher.queue_declare(name, durable=True,
            arguments={'x-dead-letter-exchange': '', 'x-dead-letter-routing-key': dlq})
        publisher.queue_bind(name, direct, routing_key='probe.direct')
        publisher.queue_bind(name, topic, routing_key='probe.#')
        receiver = connection()
        consumer = receiver.channel()
        consumer.basic_qos(prefetch_count=1)
        seen = set()
        sent, receipts, confirms = {}, [], []
        def receive(ch, method, properties, body):
            identity = properties.message_id
            if identity in seen: result['duplicates'] += 1
            if identity not in sent or hashlib.sha256(body).hexdigest() != sent[identity][1]:
                result['corruptBodies'] += 1
            else: receipts.append((time.monotonic()-sent[identity][0])*1000)
            seen.add(identity)
            ch.basic_ack(method.delivery_tag)
        tag = consumer.basic_consume(name, receive, auto_ack=False)
        stage = 'benchmark'
        for index in range(count):
            identity = str(index)
            body = json.dumps({'synthetic': True, 'run': name, 'id': identity, 'padding': 'x'*1024}).encode()
            sent[identity] = time.monotonic(), hashlib.sha256(body).hexdigest()
            publisher.basic_publish(direct if index % 2 else topic, 'probe.direct', body,
                pika.BasicProperties(message_id=identity, delivery_mode=2), mandatory=True)
            confirms.append((time.monotonic()-sent[identity][0])*1000)
            deadline = time.monotonic()+10
            while identity not in seen and time.monotonic() < deadline:
                receiver.process_data_events(time_limit=.01)
            if identity not in seen: raise RuntimeError('synthetic_delivery_timeout')
        consumer.basic_cancel(tag)
        receiver.close()
        result['uniqueNormalMessages'] = len(seen)
        result['confirmLatency'] = stats(confirms)
        result['deliveryLatency'] = stats(receipts)
        stage = 'offline-recovery'
        body = b'synthetic-offline-recovery'
        publisher.basic_publish(direct, 'probe.direct', body,
            pika.BasicProperties(message_id='offline', delivery_mode=2), mandatory=True)
        receiver = connection()
        consumer, method, props, received = await_message(receiver, name)
        if received != body or props.message_id != 'offline': raise RuntimeError('offline_mismatch')
        receiver.close()  # Deliberately leave this delivery unacknowledged.
        receiver = connection()
        consumer, method, props, received = await_message(receiver, name)
        if received != body or props.message_id != 'offline' or not method.redelivered:
            raise RuntimeError('unacknowledged_recovery_mismatch')
        consumer.basic_ack(method.delivery_tag)
        consumer.close(); consumer = receiver.channel()
        result['recovery'] = {'offlineMessageReceived': True, 'unacknowledgedRecovered': True, 'redelivered': True}
        stage = 'mandatory-return'
        try:
            publisher.basic_publish(direct, 'no-binding', b'synthetic', mandatory=True)
        except pika.exceptions.UnroutableError:
            result['mandatoryReturnObserved'] = True
        else:
            raise RuntimeError('mandatory_return_missing')
        stage = 'dead-letter-source-receive'
        publisher.basic_publish(direct, 'probe.direct', b'synthetic-invalid',
            pika.BasicProperties(message_id='invalid', delivery_mode=2), mandatory=True)
        consumer, method, props, received = await_message(receiver, name)
        if props.message_id != 'invalid' or received != b'synthetic-invalid': raise RuntimeError('unexpected_recovery_duplicate')
        consumer.basic_nack(method.delivery_tag, requeue=False)
        consumer.close()
        stage = 'dead-letter-receive'
        consumer, method, props, received = await_message(receiver, dlq)
        if received != b'synthetic-invalid': raise RuntimeError('dead_letter_mismatch')
        consumer.basic_ack(method.delivery_tag)
        consumer.close(); consumer = receiver.channel()
        result['deadLetter'] = {'rejectedMessageRetained': True, 'bodyMatches': True}
        stage = 'empty-check'
        samples = []
        deadline = time.monotonic()+20
        while True:
            samples.append(consumer.queue_declare(name, passive=True).method.message_count)
            if samples[-1] == 0 or time.monotonic() >= deadline: break
            receiver.sleep(.1)
        result['remainingMessageCountSamples'] = samples
        result['remainingMessages'] = samples[-1]
        if samples[-1]:
            stage = 'post-ack-delivery-check'
            extras = []
            def extra(ch, method, properties, body):
                # Every payload in this UUID queue belongs to this synthetic run.
                extras.append({'knownSyntheticId': properties.message_id in sent or
                               properties.message_id in ('offline', 'invalid'),
                               'redelivered': bool(method.redelivered)})
                ch.basic_ack(method.delivery_tag)
            consumer.basic_consume(name, extra, auto_ack=False)
            deadline = time.monotonic()+3
            while time.monotonic() < deadline:
                receiver.process_data_events(time_limit=.05)
            consumer.close(); consumer = receiver.channel()
            result['postAckDeliveries'] = extras
            result['postAckReportedRemaining'] = consumer.queue_declare(name, passive=True).method.message_count
        result['passed'] = (len(seen) == count and not result['duplicates']
                            and not result['corruptBodies'] and samples[-1] == 0)
    except Exception as error:
        result['failureStage'] = stage
        result['failureType'] = type(error).__name__  # Never retain exception text/URL.
        if type(error) is RuntimeError and str(error) in {
                'synthetic_delivery_missing_or_duplicate', 'synthetic_delivery_timeout',
                'offline_mismatch', 'unacknowledged_recovery_mismatch',
                'mandatory_return_missing', 'unexpected_recovery_duplicate', 'dead_letter_mismatch'}:
            result['failureCode'] = str(error)
    finally:
        if publisher and publisher.is_open:
            for kind, resource in [('queue', name), ('deadLetterQueue', dlq), ('direct', direct), ('topic', topic)]:
                try:
                    if kind in ('queue', 'deadLetterQueue'): publisher.queue_delete(resource)
                    else: publisher.exchange_delete(resource)
                    result['cleanup'][kind] = True
                except Exception:
                    result['cleanup'][kind] = False
        for rabbit in opened:
            if rabbit.is_open:
                try: rabbit.close()
                except Exception: pass
    return result
