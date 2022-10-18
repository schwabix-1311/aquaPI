#!/usr/bin/env python3

import logging
import time
# import os
# from resource import *
# import sys

from flask import (
    Blueprint, current_app, json, Response
)
from http import HTTPStatus

log = logging.getLogger('API')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


bp = Blueprint('api', __name__)


@bp.route('/api/node/<node_id>')
def api_node(node_id):
    bus = current_app.bus
    node_id = str(node_id.encode('ascii', 'xmlcharrefreplace'), errors='strict')
    node = bus.get_node(node_id)

    if node:
        state = {}
        state.update(id=node.id)
        state.update(type=type(node).__name__)
        state.update(node.__getstate__())

        # FIXME: node.name shows incorrectly, this started with node.id containing xmlcharrefs
        # ?? state['name'] = str(state['name'], encodingerrors='xmlcharrefreplace')
        if hasattr(node, 'get_renderdata'):
            state.update(render_data=node.get_renderdata())
        if hasattr(node, 'alert'):
            state.update(alert=node.alert)
        log.debug(state)

        return json.dumps(state, default=vars)
    else:
        return Response(status=HTTPStatus.NOT_FOUND)


@bp.route('/api/nodes/')
def api_nodes():
    bus = current_app.bus
    node_ids = [node.id for node in bus.get_nodes()]

    if node_ids:
        return json.dumps(node_ids)
    else:
        return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)
