# -*- coding: utf-8 -*-

"""
Copyright (C) 2017, Zato Source s.r.o. https://zato.io

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

# gevent comes first
from gevent.monkey import patch_all
patch_all()

# stdlib
import logging

# Spring Python
from springpython.jms.core import JmsTemplate, TextMessage

# Zato
from zato.common.ipc.api import IPCAPI
from zato.server.connection.jms_wmq import get_factory

logging.basicConfig()

class WMQOutconn(object):
    """ A sub-process communicating with WebSphere MQ.
    """
    def __init__(self, server_pid):
        self.server_pid = server_pid
        self.ipc_api = IPCAPI(False, 'My Outconn')
        self.ipc_api.run()

    def send(self, msg):
        response = self.ipc_api.invoke_by_pid('zato.helpers.input-logger', 'zzz', self.server_pid, 2048)
        print(933, response)

    '''
    def __init__(self):
        # type: (dict)
        self.config = config
        self.name = self.config.name
        self.jms_template = JmsTemplate(get_factory(self.config.def_config))
        '''

    '''
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

        self.jms_template.send(msg, queue_name)
        '''


if __name__ == '__main__':
    server_pid = 26900
    msg = 'my-msg'

    out = WMQOutconn(server_pid)
    out.send(msg)
