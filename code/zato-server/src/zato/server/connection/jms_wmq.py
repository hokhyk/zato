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

# amqp
from amqp.exceptions import ConnectionError as AMQPConnectionError

# gevent
from gevent import sleep, spawn

# Spring Python
from springpython.jms import JMSException
from springpython.jms.core import JmsTemplate, TextMessage
from springpython.jms.factory import WebSphereMQConnectionFactory

# Zato
from zato.common import CHANNEL, SECRET_SHADOW, version
from zato.common.util import get_component_name
from zato.server.connection.connector import Connector, Inactive

# ################################################################################################################################

logger = getLogger(__name__)

# ################################################################################################################################

_default_out_keys=('app_id', 'content_encoding', 'content_type', 'delivery_mode', 'expiration', 'priority', 'user_id')

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
        self.jms_template = JmsTemplate(self.config.factory)

    def publish(self, *args, **kwargs):
        return self.jms_template.send(*args, **kwargs)

# ################################################################################################################################

class Consumer(object):
    """ Consumes messages from WebSphere MQ queues. There is one Consumer object for each Zato WebSphere MQ channel.
    """
    def __init__(self, config, on_amqp_message):
        # type: (dict, Callable)
        self.config = config
        self.name = self.config.name
        self.queue = [Queue(self.config.queue)]
        self.on_amqp_message = on_amqp_message
        self.keep_running = True
        self.is_stopped = False
        self.is_connected = False # Instance-level flag indicating whether we have an active connection now.
        self.timeout = 0.35

    def _on_amqp_message(self, body, msg):
        try:
            return self.on_amqp_message(body, msg, self.name, self.config)
        except Exception, e:
            logger.warn(format_exc(e))

# ################################################################################################################################

    def _get_consumer(self, _gevent_sleep=sleep):
        """ Creates a new connection and consumer to an WebSphere MQ broker.
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
                conn = self.config.conn_class(self.config.conn_url)
                consumer = _Consumer(conn, queues=self.queue, callbacks=[self._on_amqp_message],
                    no_ack=_no_ack[self.config.ack_mode], tag_prefix='{}/{}'.format(
                        self.config.consumer_tag_prefix, get_component_name('amqp-consumer')))
                consumer.consume()
            except Exception, e:
                err_conn_attempts += 1
                noun = 'attempts' if err_conn_attempts > 1 else 'attempt'
                logger.info('Could not create an WebSphere MQ consumer for channel `%s` (%s %s so far), e:`%s`',
                    self.name, err_conn_attempts, noun, format_exc(e))

                # It's fine to sleep for a longer time because if this exception happens it means that we cannot connect
                # to the server at all, which will likely mean that it is down,
                if self.keep_running:
                    _gevent_sleep(2)

        if err_conn_attempts > 0:
            noun = 'attempts' if err_conn_attempts > 1 else 'attempt'
            logger.info('Created an WebSphere MQ consumer for channel `%s` after %s %s', self.name, err_conn_attempts, noun)

        return consumer

# ################################################################################################################################

    def start(self, conn_errors=(socket_error, IOError, OSError), _gevent_sleep=sleep):
        """ Runs the WebSphere MQ consumer's mainloop.
        """
        try:

            connection = None
            consumer = self._get_consumer()
            self.is_connected = True

            # Local aliases.
            timeout = self.timeout

            # Since heartbeats run frequently (self.timeout may be a fraction of a second), we don't want to log each
            # and every error. Instead we log errors each log_every times.
            hb_errors_so_far = 0
            log_every = 20

            while self.keep_running:
                try:

                    connection = consumer.connection

                    # Do not assume the consumer still has the connection, it may have been already closed, we don't know.
                    # Unfortunately, the only way to check it is to invoke the method and catch AttributeError
                    # if connection is already None.
                    try:
                        connection.drain_events(timeout=timeout)
                    except AttributeError:
                        consumer = self._get_consumer()

                # Special-case AMQP-level connection errors and recreate the connection if any is caught.
                except AMQPConnectionError, e:
                    logger.warn('Caught WebSphere MQ connection error in mainloop e:`%s`', format_exc(e))
                    if connection:
                        connection.close()
                        consumer = self._get_consumer()

                # Regular network-level errors - assume the WebSphere MQ connection is still fine and treat it
                # as an opportunity to perform the heartbeat.
                except conn_errors, e:

                    try:
                        connection.heartbeat_check()
                    except Exception, e:
                        hb_errors_so_far += 1
                        if hb_errors_so_far % log_every == 0:
                            logger.warn('Exception in heartbeat (%s so far), e:`%s`', hb_errors_so_far, format_exc(e))

                        # Ok, we've lost the connection, set the flag to False and sleep for some time then.
                        if not connection:
                            self.is_connected = False

                        if self.keep_running:
                            _gevent_sleep(timeout)
                    else:
                        # Reset heartbeat errors counter since we have apparently succeeded.
                        hb_errors_so_far = 0

                        # If there was not any exception but we did not have a previous connection it means that a previously
                        # established connection was broken so we need to recreate it.
                        # But, we do it only if we are still told to keep running.
                        if self.keep_running:
                            if not self.is_connected:
                                consumer = self._get_consumer()
                                self.is_connected = True

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

            # self.timeout is multiplied by 2 because it's used twice in the main loop in self.start
            # plus a bit of additional time is added.
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

        self.conn = WebSphereMQConnectionFactory(
            self.config.queue_manager,
            str(self.config.channel),
            str(self.config.host),
            str(self.config.port),
            self.config.cache_open_send_queues,
            self.config.cache_open_receive_queues,
            self.config.use_shared_connections,
            ssl = self.config.ssl,
            ssl_cipher_spec = str(self.config.ssl_cipher_spec) if self.config.get('ssl_cipher_spec') else None,
            ssl_key_repository = str(self.config.ssl_key_repository) if self.config.get('ssl_key_repository') else None,
            needs_mcd = self.config.needs_mcd,
        )

        self.is_connected = True

# ################################################################################################################################

    def _stop(self):
        self._stop_consumers()
        self.conn.destroy()

# ################################################################################################################################

    def on_amqp_message(self, body, msg, channel_name, channel_config, _WMQMessage=_WMQMessage, _RECEIVED='RECEIVED'):
        """ Invoked each time a message is taken off an WebSphere MQ queue.
        """
        self.on_message_callback(
            channel_config['service_name'], body, channel=_CHANNEL_AMQP,
            data_format=channel_config['data_format'],
            zato_ctx={'zato.channel_item': {
                'id': channel_config.id,
                'name': channel_config.name,
                'is_internal': False,
                'amqp_msg': msg,
            }})

        if msg._state == _RECEIVED:
            if channel_config['ack_mode'] == _ZATO_ACK_MODE_ACK:
                msg.ack()
            else:
                msg.reject()

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

# ################################################################################################################################

    def create_channels(self):
        """ Sets up WebSphere MQ consumers for all channels.
        """
        for config in self.channels.itervalues():
            self._enrich_channel_config(config)

            # TODO: Make the pool size configurable from web-admin
            for x in xrange(30):
                spawn(self._create_consumer, config)

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
        """ Creates an WebSphere MQ consumer for a specific queue and starts it.
        """
        consumer = Consumer(config, self.on_amqp_message)
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

        for x in xrange(config.pool_size):
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
