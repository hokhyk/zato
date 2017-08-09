# -*- coding: utf-8 -*-

"""
Copyright (C) 2017, Zato Source s.r.o. https://zato.io

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

# stdlib
from logging import getLogger
from traceback import format_exc

# Zato
from zato.common.util import spawn_greenlet, start_connectors
from zato.server.base.worker.common import WorkerImpl

# ################################################################################################################################

logger = getLogger(__name__)

# ################################################################################################################################

class JMSWMQ(WorkerImpl):
    """ JMS WebSphere MQ-related functionality for worker objects.
    """

# ################################################################################################################################

    def jms_wmq_connection_create(self, msg):
        msg.is_active = True
        with self.update_lock:
            self.jms_wmq_api.create(msg.name, msg, self.invoke, needs_start=True)

    def on_broker_msg_DEFINITION_JMS_WMQ_CREATE(self, msg):
        start_connectors(self, 'zato.connector.jms_wmq.start', msg)

# ################################################################################################################################

    def on_broker_msg_DEFINITION_JMS_WMQ_EDIT(self, msg):
        msg.is_active = True

        with self.update_lock:

            # Update outconn -> definition mappings
            for out_name, def_name in self.jms_wmq_out_name_to_def.items():
                if def_name == msg.old_name:
                    self.jms_wmq_out_name_to_def[out_name] = msg.name

            # Update definition itself
            self.jms_wmq_api.edit(msg.old_name, msg)

# ################################################################################################################################

    def on_broker_msg_DEFINITION_JMS_WMQ_DELETE(self, msg):
        with self.update_lock:
            for out_name, def_name in self.jms_wmq_out_name_to_def.items():
                if def_name == msg.name:
                    del self.jms_wmq_out_name_to_def[out_name]

            self.jms_wmq_api.delete(msg.name)

# ################################################################################################################################

    def on_broker_msg_DEFINITION_JMS_WMQ_CHANGE_PASSWORD(self, msg):
        with self.update_lock:
            self.jms_wmq_api.change_password(msg.name, msg)

# ################################################################################################################################

    def on_broker_msg_OUTGOING_JMS_WMQ_CREATE(self, msg):
        with self.update_lock:
            self.jms_wmq_out_name_to_def[msg.name] = msg.def_name
            self.jms_wmq_api.create_outconn(msg.def_name, msg)

# ################################################################################################################################

    def on_broker_msg_OUTGOING_JMS_WMQ_EDIT(self, msg):
        with self.update_lock:
            del self.jms_wmq_out_name_to_def[msg.old_name]
            self.jms_wmq_out_name_to_def[msg.name] = msg.def_name
            self.jms_wmq_api.edit_outconn(msg.def_name, msg)

# ################################################################################################################################

    def on_broker_msg_OUTGOING_JMS_WMQ_DELETE(self, msg):
        with self.update_lock:
            del self.jms_wmq_out_name_to_def[msg.name]
            self.jms_wmq_api.delete_outconn(msg.def_name, msg)

# ################################################################################################################################

    def on_broker_msg_CHANNEL_JMS_WMQ_CREATE(self, msg):
        with self.update_lock:
            self.jms_wmq_api.create_channel(msg.def_name, msg)

# ################################################################################################################################

    def on_broker_msg_CHANNEL_JMS_WMQ_EDIT(self, msg):
        with self.update_lock:
            self.jms_wmq_api.edit_channel(msg.def_name, msg)

# ################################################################################################################################

    def on_broker_msg_CHANNEL_JMS_WMQ_DELETE(self, msg):
        with self.update_lock:
            self.jms_wmq_api.delete_channel(msg.def_name, msg)

# ################################################################################################################################

    def jms_wmq_invoke(self, msg, out_name, queue_name, **kwargs):
        """ Invokes a remote queue manager by putting a message on a queue.
        """
        with self.update_lock:
            def_name = self.jms_wmq_out_name_to_def[out_name]

        return self.jms_wmq_api.invoke(def_name, out_name, msg, queue_name, **kwargs)

    def _jms_wmq_invoke_async(self, *args, **kwargs):
        try:
            self.jms_wmq_invoke(*args, **kwargs)
        except Exception, e:
            logger.warn(format_exc(e))

    def jms_wmq_invoke_async(self, *args, **kwargs):
        spawn_greenlet(self._jms_wmq_invoke_async, *args, **kwargs)

# ################################################################################################################################
