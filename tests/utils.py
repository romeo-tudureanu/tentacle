"""Kraken publisher used to query for event scheduling."""
import uuid

from siren.serializers import (json_loads, msgpack_loads, json_dumps,
                               msgpack_dumps)
from kombu.serialization import register
from kombu import Queue, Exchange, Connection
from kombu.exceptions import TimeoutError

from tentacle import Config, get_logger

register('json', json_dumps, json_loads,
         content_type='application/json',
         content_encoding='utf-8')

register('msgpack', msgpack_dumps, msgpack_loads,
         content_type='application/msgpack',
         content_encoding='utf-8')

logger = get_logger('tentacle')


class Publisher(object):
    """Base publisher class."""

    content_type = Config.CELERY_TASK_SERIALIZER
    needs_response = True

    host = 'localhost'
    port = 5672
    vhost = '/'

    user = None
    password = None

    timeout = 5
    corr_id = None

    def __init__(self, *args, **kwargs):
        """Initialize the publisher."""
        if self.user is None and self.password is None:
            raise Exception('Please provide a username and password.')

        if not hasattr(self, 'exchange'):
            raise Exception('Please provide an exchange name.')

        self._args = args

        payload = kwargs.pop('payload', None)
        self._kwargs = kwargs

        if args and kwargs:
            raise Exception('Please provide only args OR only kwargs.')

        if self.needs_response:
            self.corr_id = str(uuid.uuid4())

        self.payload = payload or self.get_payload()

        self.url = 'amqp://{user}:{password}@{host}:{port}/{vhost}'.format(
            user=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            vhost=self.vhost
        )

    def on_response(self, body, message):
        """Process a response message.

        Check if the correlation_id is the one we are looking for.
        If so, store the response in self.response.
        """
        if self.corr_id == message.properties.get('correlation_id'):
            status = body.get('status')
            if status != 'RETRY':
                self.response = body

    def call(self):
        """Main method of the publisher.

        Publishes messages and checks for responses.
        """
        with Connection(self.url) as conn:
            self.response = None

            exchange = Exchange(name=self.exchange)
            result_queue = Queue(name=self.corr_id,
                                 exchange=exchange,
                                 auto_delete=True)

            producer = conn.Producer(exchange=exchange,
                                     serializer=self.content_type)
            msg = dict(
                body=self.payload,
                routing_key=self.get_routing_key(),
                **self.get_properties()
            )
            producer.publish(**msg)

            if not self.needs_response:
                return None

            with conn.Consumer(queues=[result_queue],
                               callbacks=[self.on_response]):
                logger.debug('Waiting for task id response: %s', self.corr_id)
                try:
                    while not self.response:
                        conn.drain_events(timeout=self.timeout)
                except TimeoutError:
                    logger.debug('Request timed out after %s.', self.timeout)
                    return None

            return self.response

    def _get_sent_message(self):
        """Used for debugging purposes."""
        return self.payload

    def get_routing_key(self):
        """Used by subclasses to override routing key."""
        if hasattr(self, 'routing_key'):
            return self.routing_key
        else:
            raise Exception('Please provide a routing key or \
                             override the get_routing_key function.')

    def get_properties(self):
        """Used by subclasses to customize publishing kwargs."""
        data = {
            'delivery_mode': 2,  # make message persistent
        }
        if self.needs_response:
            data.update({
                'correlation_id': self.corr_id,
                'reply_to': self.corr_id,
            })
        return data

    def get_payload(self):
        """Should be implemented by subclasses."""
        raise NotImplementedError


class KrakenPublisher(Publisher):
    """A publisher customized to talk to Kraken."""

    exchange = 'kraken'
    routing_key = 'kraken'
    user = Config.KRAKEN_USER
    password = Config.KRAKEN_PASSWORD
    vhost = Config.KRAKEN_VHOST
    host = Config.KRAKEN_HOST

    needs_response = False

    def __init__(self, method, *args, **kwargs):
        """Initialize the publisher with the method endpoint."""
        self.method = method
        super(KrakenPublisher, self).__init__(*args, **kwargs)

    def get_payload(self):
        """Create the message payload as accepted by celery.

        http://docs.celeryproject.org/en/latest/internals/protocol.html#example-message
        """
        params = self._args or self._kwargs

        payload = {
            'id': self.corr_id,
            'task': 'kraken.tasks.RPCTask',
            'kwargs': {
                'id': self.corr_id,
                'jsonrpc': '2.0',
                'method': self.method,
                'params': params
            },
        }
        return json_dumps(payload) if self.content_type.endswith('json') \
            else msgpack_dumps(payload)


def kraken_hit(self, method, *args, **kwargs):
    """Hit Kraken on the specified method with the specified kwargs."""
    kraken = KrakenPublisher(method, *args, **kwargs)

    logger.info('Hitting Kraken: %s - %s %s' % (method, args, kwargs))
    kraken.call()


class NautilusPublisher(Publisher):
    """A publisher customized to talk to Nautilus."""

    exchange = 'nautilus'
    routing_key = 'nautilus'
    user = Config.NAUTILUS_USER
    password = Config.NAUTILUS_PASSWORD
    vhost = Config.NAUTILUS_VHOST
    host = Config.NAUTILUS_HOST

    needs_response = False

    def __init__(self, method, *args, **kwargs):
        """Initialize the publisher with the method endpoint."""
        self.method = method
        super(NautilusPublisher, self).__init__(*args, **kwargs)

    def get_payload(self):
        """Create the message payload as accepted by celery.

        http://docs.celeryproject.org/en/latest/internals/protocol.html#example-message
        """
        params = self._args or self._kwargs

        payload = {
            'id': self.corr_id,
            'task': self.method,
            'kwargs': {
                'id': self.corr_id,
                'jsonrpc': '2.0',
                'params': params
            },
        }
        return json_dumps(payload) if self.content_type.endswith('json') \
            else msgpack_dumps(payload)


def nautilus_hit(self, method, *args, **kwargs):
    """Hit Nautilus on the specified method with the specified kwargs."""
    nautilus = NautilusPublisher(method, *args, **kwargs)

    logger.info('Hitting Nautilus: %s - %s %s' % (method, args, kwargs))
    nautilus.call()
