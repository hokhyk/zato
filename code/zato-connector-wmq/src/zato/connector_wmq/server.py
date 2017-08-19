# -*- coding: utf-8 -*-

"""
Copyright (C) 2017 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

# Bunch
from bunch import Bunch

# Zato
from zato.common.embeddable import EmbeddableServer
from zato.common.util import get_crypto_manager_from_server_config, get_odb_session_from_server_config

# ################################################################################################################################

class Config(object):
    """ Encapsulates configuration of various scheduler-related layers.
    """
    def __init__(self):
        self.main = Bunch()
        self.odb = None

# ################################################################################################################################

class ConnectorWMQServer(EmbeddableServer):
    """ Main class spawning WebSphere MQ-related tasks and listening for HTTP API requests.
    """
    def __init__(self, config, repo_location):

        # Base API
        super(ConnectorWMQServer, self).__init__(config, repo_location)

        # Zato objects, ID -> details
        self.definitions = {}
        self.channels = {}
        self.outconns = {}

        # Read in configuration and set up connector threads
        self.configure()

# ################################################################################################################################

    def configure(self):
        """ Configures all MQ connections
        """
        for item in self.config.odb.get_def_jms_wmq_list(self.cluster_id):
            print(item)

# ################################################################################################################################

    def _start_threads(self):
        pass

# ################################################################################################################################

    def serve_forever(self):

        # Start connector threads
        self._start_threads()

        # Start the underlying API server
        super(ConnectorWMQServer, self).serve_forever()

# ################################################################################################################################
