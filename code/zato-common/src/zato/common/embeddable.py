# -*- coding: utf-8 -*-

"""
Copyright (C) 2017 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

# stdlib
import logging
from traceback import format_exc

# Bunch
from bunch import Bunch

# gevent
from gevent.pywsgi import WSGIServer

# Zato
from zato.common import ZATO_ODB_POOL_NAME
from zato.common.crypto import CryptoManager
from zato.common.odb.api import ODBManager, PoolStore
from zato.common.util import get_crypto_manager

# ################################################################################################################################

logger = logging.getLogger(__name__)

# ################################################################################################################################

ok = b'200 OK'
headers = [(b'Content-Type', b'application/json')]

# ################################################################################################################################

class EmbeddableServer(object):
    """ A base class for embeddable servers acting in various capacities, e.g. in the scheduler or WebSphere MQ connector.
    """
    def __init__(self, config, repo_location):
        self.config = config
        self.repo_location = repo_location
        self.sql_pool_store = PoolStore()

        # ODB connection
        self.odb = ODBManager()
        self.odb.crypto_manager = get_crypto_manager(self.repo_location, None, config.main, crypto_manager=CryptoManager())

        if self.config.main.odb.engine != 'sqlite':
            self.config.main.odb.password = self.odb.crypto_manager.decrypt(config.main.odb.password)
            self.config.main.odb.host = config.main.odb.host
            self.config.main.odb.pool_size = config.main.odb.pool_size
            self.config.main.odb.username = config.main.odb.username

        self.sql_pool_store[ZATO_ODB_POOL_NAME] = self.config.main.odb

        main = self.config.main

        if main.crypto.use_tls:
            priv_key, cert = main.crypto.priv_key_location, main.crypto.cert_location
        else:
            priv_key, cert = None, None

        # API server
        self.api_server = WSGIServer((main.bind.host, int(main.bind.port)), self, keyfile=priv_key, certfile=cert)

        self.odb.pool = self.sql_pool_store[ZATO_ODB_POOL_NAME].pool
        self.odb.init_session(ZATO_ODB_POOL_NAME, self.config.odb, self.odb.pool, False)
        self.config.odb = self.odb
        self.cluster_id = self.config.main.cluster.id

# ################################################################################################################################

    def serve_forever(self):
        self.api_server.serve_forever()

# ################################################################################################################################

    def __call__(self, env, start_response):
        try:
            start_response(ok, headers)
            return [b'{}\n']
        except Exception, e:
            logger.warn(format_exc(e))

# ################################################################################################################################
