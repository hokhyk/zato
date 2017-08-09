# -*- coding: utf-8 -*-

"""
Copyright (C) 2017, Zato Source s.r.o. https://zato.io

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

# stdlib
from datetime import datetime, timedelta
from exceptions import IOError, OSError
from logging import getLogger
from socket import error as socket_error
from traceback import format_exc

import greenify
greenify.greenify()

# amqp
from amqp.exceptions import ConnectionError as AMQPConnectionError

# gevent
from gevent import sleep, spawn

# Spring Python
from springpython.jms import JMSException, NoMessageAvailableException, WebSphereMQJMSException
from springpython.jms.core import JmsTemplate, TextMessage
from springpython.jms.factory import WebSphereMQConnectionFactory

# ThreadPool
from threadpool import ThreadPool, WorkRequest, NoResultsPending

# Zato
from zato.common import CHANNEL, SECRET_SHADOW, version
from zato.common.util import get_component_name, spawn_greenlet
from zato.server.connection.connector import Connector, Inactive

# ################################################################################################################################

logger = getLogger(__name__)

# ################################################################################################################################

def get_factory(config):
    return WebSphereMQConnectionFactory(
        config.queue_manager, str(config.channel), str(config.host), str(config.port),
        config.cache_open_send_queues,
        config.cache_open_receive_queues, config.use_shared_connections,
        ssl=config.ssl, ssl_cipher_spec=str(config.ssl_cipher_spec) if config.get('ssl_cipher_spec') else None,
        ssl_key_repository=str(config.ssl_key_repository) if config.get('ssl_key_repository') else None,
        needs_mcd=config.needs_mcd,
    )

# ################################################################################################################################

def ping_factory(factory, pymqi):

    qmgr = pymqi.QueueManager(None)
    qmgr.connect_tcp_client(str(factory.queue_manager), pymqi.CD(), str(factory.channel),
        b'{}({})'.format(factory.host, factory.listener_port), user=None, password=None)

    pcf = pymqi.PCFExecute(qmgr)

    try:
        pcf.MQCMD_PING_Q_MGR()
    finally:
        qmgr.disconnect()

# ################################################################################################################################

class _WMQMessage(object):
    __slots__ = ('body', 'impl')

    def __init__(self, body, impl):
        self.body = body
        self.impl = impl

# ################################################################################################################################

class _WMQProducers(object):
    """ Encapsulates information about producers used by outgoing WebSphere MQ connection to send messages to a broker.
    Each outgoing connection has one _WMQroducers object assigned.
    """
    def __init__(self, config):
        # type: (dict)
        self.config = config
        self.name = self.config.name
        self.jms_template = JmsTemplate(get_factory(self.config.def_config))

    def publish(self, body, queue_name, *args, **kwargs):

        msg = TextMessage(body)

        msg.jms_destination = queue_name
        msg.jms_expiration = kwargs.get('priority') or self.config.expiration
        msg.jms_correlation_id = kwargs.get('correlation_id')
        msg.jms_delivery_mode = kwargs.get('delivery_mode') or self.config.delivery_mode
        msg.jms_expiration = kwargs.get('expiration') or self.config.expiration or None
        msg.jms_message_id = kwargs.get('message_id')
        msg.jms_priority = kwargs.get('priority') or self.config.priority
        msg.jms_redelivered = kwargs.get('redelivered')
        msg.jms_reply_to = kwargs.get('reply_to')
        msg.jms_timestamp = kwargs.get('timestamp')
        msg.max_chars_printed = kwargs.get('max_chars_printed') or 100

        spawn(self.jms_template.send, msg, queue_name)

# ################################################################################################################################

class _WMQConsumer(object):
    def __init__(self, config, queue, pymqi):
        # type: (WebSphereMQConnectionFactory, str, object)
        self.factory = get_factory(config)
        self.queue = queue
        self.pymqi = pymqi

    def ping(self):
        """ Ping the factory's underlying queue manager. This only confirms that the QM is available when ping was issued,
        it's still possible that it will disconnect afterwards but we have at least some indication whether it is up now.
        """
        ping_factory(self.factory, self.pymqi)

    def consume(self):
        try:
            msg = self.factory.receive(self.queue, 0.5)
        except NoMessageAvailableException:
            pass
        except WebSphereMQJMSException, e:
            self.logger.error("%s in .receive, e.completion_code:`%s`, "
                "e.reason_code:`%s`" % (e.__class__.__name__, e.completion_code, e.reason_code))
            raise
        else:
            return msg

# ################################################################################################################################

class Consumer(object):
    """ Consumes messages from WebSphere MQ queues. There is one Consumer object for each Zato WebSphere MQ channel.
    """
    def __init__(self, config, conn, on_wmq_message):
        # type: (dict, WebSphereMQConnectionFactory, Callable)
        self.config = config
        self.name = self.config.name
        self.conn = conn
        self.on_wmq_message = on_wmq_message
        self.keep_running = True
        self.is_stopped = False
        self.is_connected = False # Instance-level flag indicating whether we have an active connection now.
        self.timeout = 0.5

    def _on_wmq_message(self, msg):
        try:
            return self.on_wmq_message(msg, self.name, self.config)
        except Exception, e:
            logger.warn(format_exc(e))

# ################################################################################################################################

    def _get_consumer(self, _gevent_sleep=sleep):
        """ Creates a new connection and consumer to a WebSphere MQ queue manager.
        """

        # We cannot assume that we will obtain the consumer right-away. For instance, the remote end
        # may be currently available when we are starting. It's OK to block indefinitely (or until self.keep_running is False)
        # because we run in our own greenlet.
        consumer = None
        err_conn_attempts = 0

        while not consumer:
            if not self.keep_running:
                break

            try:
                consumer = _WMQConsumer(self.config.def_config, self.config.queue, self.config.pymqi)
                try:
                    consumer.ping()
                except Exception, e:
                    logger.warn(format_exc(e))
                    consumer = None
                    raise

            except Exception, e:
                err_conn_attempts += 1
                noun = 'attempts' if err_conn_attempts > 1 else 'attempt'
                logger.info('Could not create a WebSphere MQ consumer for channel `%s` (%s) (%s %s so far), e:`%s`',
                    self.name, self.config.conn_url, err_conn_attempts, noun, format_exc(e))

                # It's fine to sleep for a longer time because if this exception happens it means that we cannot connect
                # to the server at all, which will likely mean that it is down,
                if self.keep_running:
                    _gevent_sleep(2)

        if err_conn_attempts > 0:
            noun = 'attempts' if err_conn_attempts > 1 else 'attempt'
            logger.info('Created a WebSphere MQ consumer for channel `%s` after %s %s', self.name, err_conn_attempts, noun)

        return consumer

# ################################################################################################################################

    def start(self, conn_errors=(socket_error, IOError, OSError), _spawn=spawn, _gevent_sleep=sleep):
        """ Runs the WebSphere MQ consumer's mainloop.
        """
        try:

            connection = None
            consumer = self._get_consumer()
            self.is_connected = True

            # Local aliases.
            timeout = self.timeout

            while self.keep_running:
                try:
                    msg = consumer.consume()

                    if msg:
                        _spawn(self._on_wmq_message, msg)
                    else:
                        _gevent_sleep(timeout) # To give other greenlets an opportunity to run at all

                except Exception, e:
                    logger.warn(format_exc(e))

            if connection:
                logger.info('Closing connection for `%s`', consumer)
                connection.close()
            self.is_stopped = True # Set to True if we break out of the main loop.

        except Exception, e:
            logger.warn('Unrecoverable exception in consumer, e:`%s`', format_exc(e))

# ################################################################################################################################

    def stop(self):
        """ Stops the consumer and wait for the confirmation that it actually is not running anymore.
        """
        self.keep_running = False

        # Wait until actually stopped.
        if not self.is_stopped:

            now = datetime.utcnow()
            delta = (self.timeout * 2) + 0.2
            until = now + timedelta(seconds=delta)

            while now < until:
                sleep(0.1)
                now = datetime.utcnow()
                if self.is_stopped:
                    return

            if not self.is_connected:
                return

            # If we get here it means that we did not stop in the time expected, raise an exception in that case.
            raise Exception('Consumer for channel `{}` did not stop in the expected time of {}s.'.format(
                self.name, delta))

# ################################################################################################################################

class ConnectorJMSWMQ(Connector):
    """ An WebSphere MQ connector under which channels or outgoing connections run.
    """
    start_in_greenlet = True

# ################################################################################################################################

    def _start(self):
        self._consumers = {}
        self._producers = {}
        self.config.conn_url = self._get_conn_string()

        # Imported here because it's an optional dependency that requires linking against a proprietary library.
        import pymqi
        self.pymqi = pymqi

        self.is_connected = True

# ################################################################################################################################

    def _stop(self):
        self._stop_consumers()
        self.conn.destroy()

# ################################################################################################################################

    def on_wmq_message(self, msg, channel_name, channel_config, _CHANNEL_JMS_WMQ=CHANNEL.JMS_WMQ):
        """ Invoked each time a message is taken off an WebSphere MQ queue.
        """
        self.on_message_callback(
            channel_config['service_name'], msg.text, channel=_CHANNEL_JMS_WMQ,
            data_format=channel_config['data_format'],
            zato_ctx={'zato.channel_item': {
                'id': channel_config.id,
                'name': channel_config.name,
                'is_internal': False,
                'wmq_msg': msg,
            }})

# ################################################################################################################################

    def _get_conn_string(self, needs_password=True):
        return 'zato+wmq{}://{}@{}:{}?channel={}'.format(
            's' if self.config.ssl else '', self.config.queue_manager, self.config.host, self.config.port, self.config.channel)

# ################################################################################################################################

    def get_log_details(self):
        return self._get_conn_string(False)

# ################################################################################################################################

    def _enrich_channel_config(self, config):
        config.conn_url = self.config.conn_url
        config.def_config = self.config
        config.pymqi = self.pymqi
        config.queue = str(config.queue) # It could be unicode but PyMQI requires strings

# ################################################################################################################################

    def create_channels(self):
        """ Sets up WebSphere MQ consumers for all channels.
        """
        for config in self.channels.itervalues():
            self._enrich_channel_config(config)

            # TODO: Make the pool size configurable from web-admin
            for x in xrange(1):
                spawn_greenlet(self._create_consumer, config)

# ################################################################################################################################

    def create_outconns(self):
        """ Sets up WebSphere MQ producers for outgoing connections. Called when the connector starts up thus it only creates producers
        because self.outconns entries are already available.
        """
        with self.lock:
            for config in self.outconns.itervalues():
                self._create_producers(config)

# ################################################################################################################################

    def _create_consumer(self, config):
        # type: (str)
        """ Creates a WebSphere MQ consumer for a specific queue and starts it.
        """
        consumer = Consumer(config, self.conn, self.on_wmq_message)
        self._consumers.setdefault(config.name, []).append(consumer)
        consumer.start()

# ################################################################################################################################

    def _create_producers(self, config):
        # type: (dict)
        """ Creates outgoing WebSphere MQ producers using kombu.
        """
        config.conn_url = self.config.conn_url
        config.def_config = self.config
        config.factory = self.conn
        self._producers[config.name] = _WMQProducers(config)

# ################################################################################################################################

    def _stop_consumers(self):
        for config in self.channels.values():
            self._delete_channel(config, False)

# ################################################################################################################################

    def _stop_producers(self):
        for producer in self._producers.itervalues():
            try:
                producer.stop()
            except Exception, e:
                logger.warn('Could not stop WebSphere MQ producer `%s`, e:`%s`', producer.name, format_exc(e))
            else:
                logger.info('Stopped producer for outconn `%s` in WebSphere MQ connector `%s`', producer.name, self.config.name)

# ################################################################################################################################

    def _create_channel(self, config):
        # type: (dict)
        """ Creates a channel. Must be called with self.lock held.
        """
        self.channels[config.name] = config
        self._enrich_channel_config(config)

        for x in xrange(1):
            spawn(self._create_consumer, config)

# ################################################################################################################################

    def create_channel(self, config):
        """ Creates a channel.
        """
        with self.lock:
            self._create_channel(config)

        logger.info('Added channel `%s` to WebSphere MQ connector `%s`', config.name, self.config.name)

# ################################################################################################################################

    def edit_channel(self, config):
        # type: (dict)
        """ Obtains self.lock and updates a channel
        """
        with self.lock:
            self._delete_channel(config)
            self._create_channel(config)

        old_name = ' ({})'.format(config.old_name) if config.old_name != config.name else ''
        logger.info('Updated channel `%s`%s in WebSphere MQ connector `%s`', config.name, old_name, config.def_name)

# ################################################################################################################################

    def _delete_channel(self, config, delete_from_channels=True):
        # type: (dict)
        """ Deletes a channel. Must be called with self.lock held.
        """
        # Closing consumers may take time so we report the progress after about each 5% of consumers is closed,
        # or, if there are ten consumers or less, after each connection is closed.
        consumers = self._consumers[config.name]
        total = len(consumers)
        progress_after = int(round(total * 0.05)) if total > 10 else 1
        noun = 'consumer' if total == 1 else 'consumers'

        for idx, consumer in enumerate(consumers, 1):
            consumer.stop()
            if idx % progress_after == 0:
                if idx != total:
                    logger.info(
                        'Stopped %s/%s %s for channel `%s` in WebSphere MQ connector `%s`', idx, total, noun, config.name,
                        self.config.name)

        logger.info('Stopped %s/%s %s for channel `%s` in WebSphere MQ connector `%s`', total, total, noun, config.name, self.config.name)

        del self._consumers[config.name]

        # Note that we do not always delete from self.channels because they may be needed in our super-class,
        # in particular, in its self.edit method.
        if delete_from_channels:
            del self.channels[config.name]

# ################################################################################################################################

    def delete_channel(self, config):
        # type: (dict)
        """ Obtains self.lock and deletes a channel.
        """
        with self.lock:
            self._delete_channel(config)

        logger.info('Deleted channel `%s` from WebSphere MQ connector `%s`', config.name, self.config.name)

# ################################################################################################################################

    def _create_outconn(self, config):
        # type: (dict)
        """ Creates an outgoing connection. Must be called with self.lock held.
        """
        self.outconns[config.name] = config
        self._create_producers(config)

# ################################################################################################################################

    def create_outconn(self, config):
        # type: (dict)
        """ Creates an outgoing connection.
        """
        with self.lock:
            self._create_outconn(config)

        logger.info('Added outconn `%s` to WebSphere MQ connector `%s`', config.name, self.config.name)

# ################################################################################################################################

    def edit_outconn(self, config):
        # type: (dict)
        """ Obtains self.lock and updates an outgoing connection.
        """
        with self.lock:
            self._delete_outconn(config)
            self._create_outconn(config)

        old_name = ' ({})'.format(config.old_name) if config.old_name != config.name else ''
        logger.info('Updated outconn `%s`%s in WebSphere MQ connector `%s`', config.name, old_name, config.def_name)

# ################################################################################################################################

    def _delete_outconn(self, config):
        # type: (dict)
        """ Deletes an outgoing connection. Must be called with self.lock held.
        """
        self._producers[config.name].stop()
        del self._producers[config.name]
        del self.outconns[config.name]

# ################################################################################################################################

    def delete_outconn(self, config):
        # type: (dict)
        """ Obtains self.lock and deletes an outgoing connection.
        """
        with self.lock:
            self._delete_outconn(config)

        logger.info('Deleted outconn `%s` from WebSphere MQ connector `%s`', config.name, self.config.name)

# ################################################################################################################################

    def invoke(self, out_name, msg, queue_name, **kwargs):
        # type: (str, str, str, str, dict, dict, Any, Any)
        """ Synchronously publishes a message to an WebSphere MQ broker.
        """
        with self.lock:
            outconn_config = self.outconns[out_name]

        # Don't do anything if this connection is not active
        if not outconn_config['is_active']:
            raise Inactive('Connection is inactive `{}` ({})'.format(out_name, self._get_conn_string(False)))

        return self._producers[out_name].publish(msg, queue_name)

# ################################################################################################################################
