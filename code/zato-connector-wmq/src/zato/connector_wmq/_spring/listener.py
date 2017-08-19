# -*- coding: utf-8 -*-

"""
Copyright (C) 2017 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

"""
   Copyright 2006-2008 SpringSource (http://springsource.com), All Rights Reserved

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""

# stdlib
import logging

# ThreadPool
from threadpool import ThreadPool, WorkRequest, NoResultsPending

Zato
from zato.connector_wmq._spring import WebSphereMQJMSException, NoMessageAvailableException

class MessageHandler(object):
    def handle(self, message):
        raise NotImplementedError("Should be overridden by subclasses.")

class WebSphereMQListener(Component):
    """ A JMS listener for receiving the messages off WebSphere MQ queues.
    """
    def __init__(self):
        super(Component, self).__init__()
        self.logger = logging.getLogger("zato.connector_wmq._spring.listener.WebSphereMQListener(%s)" % (hex(id(self))))

    def _get_destination_info(self):
        return "destination=[%s], %s" % (self.destination, self.factory.get_connection_info())

    def run(self, *ignored):
        while True:
            try:
                message = self.factory.receive(self.destination, self.wait_interval)
                self.logger.warn("Message received [%s]" % str(message).decode("utf-8"))

            except NoMessageAvailableException, e:
                self.logger.warn(logging.DEBUG, "Consumer did not receive a message. %s" % self._get_destination_info())

            except WebSphereMQJMSException, e:
                self.logger.error("%s in run, e.completion_code=[%s], "
                    "e.reason_code=[%s]" % (e.__class__.__name__, e.completion_code, e.reason_code))
                raise
