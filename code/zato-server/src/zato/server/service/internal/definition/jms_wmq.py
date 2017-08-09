# -*- coding: utf-8 -*-

"""
Copyright (C) 2011 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

# stdlib
from contextlib import closing
from uuid import uuid4

# Zato
from zato.common.broker_message import DEFINITION
from zato.common.odb.model import ConnDefWMQ
from zato.common.odb.query import definition_jms_wmq, definition_jms_wmq_list
from zato.server.service import Bool, Int
from zato.server.service.internal import AdminService, AdminSIO, ChangePasswordBase
from zato.server.service.meta import CreateEditMeta, DeleteMeta, GetListMeta

# ################################################################################################################################

elem = 'definition_jms_wmq'
model = ConnDefWMQ
label = 'an WebSphere MQ definition'
broker_message = DEFINITION
broker_message_prefix = 'JMS_WMQ_'
list_func = definition_jms_wmq_list
skip_input_params = ('dynamic_queue_template',)

# ################################################################################################################################

class GetList(AdminService):
    name = 'zato.definition.jms-wmq.get-list'
    _filter_by = ConnDefWMQ.name,
    __metaclass__ = GetListMeta

# ################################################################################################################################

class Create(AdminService):
    name = 'zato.definition.jms-wmq.create'
    __metaclass__ = CreateEditMeta

# ################################################################################################################################

class Edit(AdminService):
    name = 'zato.definition.jms-wmq.edit'
    __metaclass__ = CreateEditMeta

# ################################################################################################################################

class Delete(AdminService):
    name = 'zato.definition.jms-wmq.delete'
    __metaclass__ = DeleteMeta

# ################################################################################################################################

class GetByID(AdminService):
    """ Returns a particular WebSphere MQ definition by its ID.
    """
    name = 'zato.definition.jms-wmq.get-by-id'

    class SimpleIO(AdminSIO):
        request_elem = 'zato_definition_jms_wmq_get_by_id_request'
        response_elem = 'zato_definition_jms_wmq_get_by_id_response'
        input_required = ('id', 'cluster_id')
        output_required = ('id', 'name', 'host', 'port', 'queue_manager', 'channel', Bool('cache_open_send_queues'),
            Bool('cache_open_receive_queues'), Bool('use_shared_connections'), Bool('ssl'), 'needs_mcd', Int('max_chars_printed'))
        output_optional = ('ssl_cipher_spec', 'ssl_key_repository')

    def get_data(self, session):
        return definition_jms_wmq(session, self.request.input.cluster_id, self.request.input.id)

    def handle(self):
        with closing(self.odb.session()) as session:
            self.response.payload = self.get_data(session)

# ################################################################################################################################


'''
from __future__ import absolute_import, division, print_function, unicode_literals

# stdlib
from contextlib import closing
from traceback import format_exc

# Zato
from zato.common.broker_message import MESSAGE_TYPE, DEFINITION
from zato.common.odb.model import Cluster, ConnDefWMQ
from zato.common.odb.query import definition_jms_wmq, definition_jms_wmq_list
from zato.server.service import Boolean, Integer
from zato.server.service.internal import AdminService, AdminSIO, GetListAdminSIO

class GetList(AdminService):
    """ Returns a list of JMS WebSphere MQ definitions available.
    """
    _filter_by = ConnDefWMQ.name,

    class SimpleIO(GetListAdminSIO):
        request_elem = 'zato_definition_jms_wmq_get_list_request'
        response_elem = 'zato_definition_jms_wmq_get_list_response'
        input_required = ('cluster_id',)
        output_required = ('id', 'name', 'host', 'port', 'queue_manager', 'channel',
            Boolean('cache_open_send_queues'), Boolean('cache_open_receive_queues'),
            Boolean('use_shared_connections'), Boolean('ssl'),
            'needs_mcd', Integer('max_chars_printed'))
        output_optional = ('ssl_cipher_spec', 'ssl_key_repository')

    def get_data(self, session):
        return self._search(definition_jms_wmq_list, session, self.request.input.cluster_id, False)

    def handle(self):
        with closing(self.odb.session()) as session:
            self.response.payload[:] = self.get_data(session)

class GetByID(AdminService):
    """ Returns a particular JMS WebSphere MQ definition.
    """
    class SimpleIO(AdminSIO):
        request_elem = 'zato_definition_jms_wmq_get_by_id_request'
        response_elem = 'zato_definition_jms_wmq_get_by_id_response'
        input_required = ('id', 'cluster_id',)
        output_required = ('id', 'name', 'host', 'port', 'queue_manager', 'channel',
            Boolean('cache_open_send_queues'), Boolean('cache_open_receive_queues'),
            Boolean('use_shared_connections'), Boolean('ssl'),
            'needs_mcd', Integer('max_chars_printed'))
        output_optional = ('ssl_cipher_spec', 'ssl_key_repository')

    def get_data(self, session):
        return definition_jms_wmq(session, self.request.input.cluster_id, self.request.input.id)

    def handle(self):
        with closing(self.odb.session()) as session:
            self.response.payload = self.get_data(session)

class Create(AdminService):
    """ Creates a new JMS WebSphere MQ definition.
    """
    class SimpleIO(AdminSIO):
        request_elem = 'zato_definition_jms_wmq_create_request'
        response_elem = 'zato_definition_jms_wmq_create_response'
        input_required = ('cluster_id', 'name', 'host', 'port', 'queue_manager',
            'channel', Boolean('cache_open_send_queues'), Boolean('cache_open_receive_queues'),
            Boolean('use_shared_connections'), Boolean('ssl'), 'needs_mcd',
            Integer('max_chars_printed'))
        input_optional = ('ssl_cipher_spec', 'ssl_key_repository')
        output_required = ('id', 'name')

    def handle(self):
        input = self.request.input
        with closing(self.odb.session()) as session:
            # Let's see if we already have an object of that name before committing
            # any stuff into the database.
            existing_one = session.query(ConnDefWMQ).\
                filter(ConnDefWMQ.cluster_id==Cluster.id).\
                filter(ConnDefWMQ.name==input.name).\
                first()

            if existing_one:
                raise Exception('JMS WebSphere MQ definition [{0}] already exists on this cluster'.format(input.name))

            try:
                def_ = ConnDefWMQ(None, input.name, input.host, input.port, input.queue_manager,
                    input.channel, input.cache_open_send_queues, input.cache_open_receive_queues,
                    input.use_shared_connections, input.ssl, input.ssl_cipher_spec,
                    input.ssl_key_repository, input.needs_mcd, input.max_chars_printed,
                    input.cluster_id)
                session.add(def_)
                session.commit()

                self.response.payload.id = def_.id
                self.response.payload.name = def_.name

            except Exception, e:
                msg = "Could not create a JMS WebSphere MQ definition, e:[{e}]".format(e=format_exc(e))
                self.logger.error(msg)
                session.rollback()

                raise

class Edit(AdminService):
    """ Updates a JMS WMQ definition.
    """
    class SimpleIO(AdminSIO):
        request_elem = 'zato_definition_jms_wmq_edit_request'
        response_elem = 'zato_definition_jms_wmq_edit_response'
        input_required = ('id', 'cluster_id', 'name', 'host', 'port', 'queue_manager',
            'channel', Boolean('cache_open_send_queues'), Boolean('cache_open_receive_queues'),
            Boolean('use_shared_connections'), Boolean('ssl'),
            'needs_mcd', Integer('max_chars_printed'))
        output_required = ('id', 'name')

    def handle(self):
        input = self.request.input

        with closing(self.odb.session()) as session:
            # Let's see if we already have an object of that name before committing
            # any stuff into the database.
            existing_one = session.query(ConnDefWMQ).\
                filter(ConnDefWMQ.cluster_id==Cluster.id).\
                filter(ConnDefWMQ.id!=input.id).\
                filter(ConnDefWMQ.name==input.name).\
                first()

            if existing_one:
                raise Exception('JMS WebSphere MQ definition [{0}] already exists on this cluster'.format(input.name))

            try:
                definition_jms_wmq = session.query(ConnDefWMQ).filter_by(id=input.id).one()
                old_name = definition_jms_wmq.name
                definition_jms_wmq.name = input.name
                definition_jms_wmq.host = input.host
                definition_jms_wmq.port = input.port
                definition_jms_wmq.queue_manager = input.queue_manager
                definition_jms_wmq.channel = input.channel
                definition_jms_wmq.cache_open_send_queues = input.cache_open_send_queues
                definition_jms_wmq.cache_open_receive_queues = input.cache_open_receive_queues
                definition_jms_wmq.use_shared_connections = input.use_shared_connections
                definition_jms_wmq.ssl = input.ssl
                definition_jms_wmq.ssl_cipher_spec = input.get('ssl_cipher_spec')
                definition_jms_wmq.ssl_key_repository = input.get('ssl_key_repository')
                definition_jms_wmq.needs_mcd = input.needs_mcd
                definition_jms_wmq.max_chars_printed = input.max_chars_printed

                session.add(definition_jms_wmq)
                session.commit()

                input.id = definition_jms_wmq.id
                input.action = DEFINITION.JMS_WMQ_EDIT.value
                input.old_name = old_name
                self.broker_client.publish(input, msg_type=MESSAGE_TYPE.TO_JMS_WMQ_CONNECTOR_ALL)

                self.response.payload.id = definition_jms_wmq.id
                self.response.payload.name = definition_jms_wmq.name

            except Exception, e:
                msg = 'Could not update the JMS WebSphere MQ definition, e:[{e}]'.format(e=format_exc(e))
                self.logger.error(msg)
                session.rollback()

                raise

class Delete(AdminService):
    """ Deletes a JMS WebSphere MQ definition.
    """
    class SimpleIO(AdminSIO):
        request_elem = 'zato_definition_jms_wmq_delete_request'
        response_elem = 'zato_definition_jms_wmq_delete_response'
        input_required = ('id',)

    def handle(self):
        with closing(self.odb.session()) as session:
            try:
                def_ = session.query(ConnDefWMQ).\
                    filter(ConnDefWMQ.id==self.request.input.id).\
                    one()

                session.delete(def_)
                session.commit()

                msg = {'action': DEFINITION.JMS_WMQ_DELETE.value, 'id': self.request.input.id}
                self.broker_client.publish(msg, msg_type=MESSAGE_TYPE.TO_JMS_WMQ_CONNECTOR_ALL)

            except Exception, e:
                session.rollback()
                msg = 'Could not delete the JMS WebSphere MQ definition, e:[{e}]'.format(e=format_exc(e))
                self.logger.error(msg)

                raise
'''
