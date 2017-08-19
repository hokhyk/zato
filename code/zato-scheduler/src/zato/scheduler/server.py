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
from zato.scheduler.api import Scheduler

# ################################################################################################################################

class Config(object):
    """ Encapsulates configuration of various scheduler-related layers.
    """
    def __init__(self):
        self.main = Bunch()
        self.startup_jobs = []
        self.odb = None
        self.on_job_executed_cb = None
        self.stats_enabled = None
        self.job_log_level = 'info'
        self.broker_client = None
        self._add_startup_jobs = True
        self._add_scheduler_jobs = True

# ################################################################################################################################

class SchedulerServer(EmbeddableServer):
    """ Main class spawning scheduler-related tasks and listening for HTTP API requests.
    """
    def __init__(self, config, repo_location):
        # Base API
        super(SchedulerServer, self).__init__(config, repo_location)

        # Scheduler
        self.scheduler = Scheduler(self.config)

# ################################################################################################################################

    def serve_forever(self):
        self.scheduler.serve_forever()
        super(SchedulerServer, self).serve_forever()

# ################################################################################################################################
