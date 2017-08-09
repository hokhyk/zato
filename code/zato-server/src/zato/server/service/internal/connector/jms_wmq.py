# -*- coding: utf-8 -*-

"""
Copyright (C) 2017, Zato Source s.r.o. https://zato.io

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

# Zato
from zato.server.service import Service

# ################################################################################################################################

class Start(Service):
    """ Starts a WebSphere MQ connection.
    """
    # We assign the name explicitly because otherwise it is turned into zato.connector.amqp-.start (note - instead of _).
    name = 'zato.connector.jms_wmq.start'

    class SimpleIO(object):
        input_required = ('cluster_id', 'frame_max', 'heartbeat', 'host', 'id', 'name', 'port', 'username', 'vhost', 'password')
        input_optional = ('old_name',)
        request_elem = 'zato_connector_jms_wmq_start_request'
        response_elem = 'zato_connector_jms_wmq_start_response'

    def handle(self):
        self.server.worker_store.jms_wmq_connection_create(self.request.input)

# ################################################################################################################################
