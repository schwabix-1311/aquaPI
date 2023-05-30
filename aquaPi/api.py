#!/usr/bin/env python3

import logging
# import time
# import os
# from resource import *
# import sys

from flask import (
    Blueprint, current_app, json, Response, request
)
from http import HTTPStatus

from .machineroom.misc_nodes import BusRole


log = logging.getLogger('API')
log.brief = log.warning  # alias, warning used as brief info, info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


bp = Blueprint('api', __name__)


@bp.route('/api/nodes/')
def api_nodes():
    bus = current_app.bus
    node_ids = [node.id for node in bus.get_nodes()]

    if node_ids:
        return json.dumps(node_ids)
    else:
        return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)


@bp.route('/api/nodes/<node_id>')
def api_node(node_id: str):
    bus = current_app.bus
    node_id = str(node_id.encode('ascii', 'xmlcharrefreplace'), errors='strict')
    node = bus.get_node(node_id)

    #log.debug(str(node))

    if node:
        state = {}
        state.update(id=node.id)
        state.update(cls=type(node).__name__)
        state.update(node.__getstate__())

        # FIXME: node.name shows some non-ascii chars incorrectly, this started with node.id containing xmlcharrefs
        # ?? state['name'] = str(state['name'], encodingerrors='xmlcharrefreplace')

        if hasattr(node, 'alert') and node.alert:
            state.update(alert=node.alert)
        log.debug(state)

        return json.dumps(state, default=vars)
    else:
        return Response(status=HTTPStatus.NOT_FOUND)


@bp.route('/api/history/')
def api_history_nodes():
    bus = current_app.bus
    node_ids = [node.id for node in bus.get_nodes(BusRole.HISTORY)]

    if node_ids:
        return json.dumps(node_ids)
    else:
        return Response(status=HTTPStatus.NOT_FOUND)


@bp.route('/api/history/<node_id>')
def api_history(node_id: str):
    bus = current_app.bus
    node_id = str(node_id.encode('ascii', 'xmlcharrefreplace'), errors='strict')
    node = bus.get_node(node_id)

    start = int(request.args.get('start', 0))
    step = int(request.args.get('step', 0))

    log.debug('API %s start %d step %d', request.path, start, step)

    if node:
        if hasattr(node, 'get_history'):
            hist = node.get_history(start, step)
            return json.dumps(hist)
        else:
            return Response(status=HTTPStatus.BAD_REQUEST)
    else:
        return Response(status=HTTPStatus.NOT_FOUND)
