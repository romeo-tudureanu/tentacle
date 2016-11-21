"""Worker used to handle changes in the event repository."""

from celery import Celery
from celery import bootsteps
from kombu import Consumer, Queue
from siren.serializers import (json_loads, msgpack_loads)

from . import Config, get_logger
from store import get_event_store

logger = get_logger('tentacle')


class EndpointConsumer(bootsteps.ConsumerStep):
    """Consumer that is used to provide endpoints to the Event Repository.

    http://celery.readthedocs.org/en/latest/userguide/extending.html
    """

    def get_consumers(self, channel):
        """Overriding class method."""
        return [Consumer(channel,
                         queues=[Queue(Config.CELERY_DEFAULT_QUEUE)],
                         on_message=self.on_message,
                         tag_prefix='tentacle',)]

    def on_message(self, message):
        """Overriding class method."""
        if Config.CELERY_TASK_SERIALIZER.endswith('json'):
            serializer = json_loads
        else:
            serializer = msgpack_loads
        payload = serializer(message.body)
        if 'action' not in payload:
            # message does not have an action, reject it
            logger.info('Received msg with no action. Rejecting it.')
            message.reject()
        else:
            action = payload.get('action')
            task_payload = payload.get('task')
            logger.info('Received msg with <%s> action and <%s> task name.',
                        action, task_payload['id'])
            logger.debug('Active tasks: %s', ','.join(item for item in app.tasks))

            app.tasks['tentacle.endpointtasks.' + action].delay(task_payload)
            message.ack()


app = Celery('tentacle')
app.steps['consumer'].add(EndpointConsumer)
app.config_from_object(Config)
app.event_store = get_event_store()
