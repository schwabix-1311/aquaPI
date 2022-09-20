#!/usr/bin/env python3

import time
# import os
# from resource import *
# import sys

from flask import (
    Blueprint, current_app, json, Response
)
from http import HTTPStatus


bp = Blueprint('api', __name__)


@bp.route('/api/node/<node_id>')
def api_node(node_id):
    bus = current_app.bus
    node_id = str(node_id.encode('ascii', 'xmlcharrefreplace'), errors='strict')
    node = bus.get_node(node_id)

    print(str(node))

    if node:
        state = {}
        state.update(node.__getstate__())
        # FIXME: node.name shows incorrectly, this started with node.id containing xmlcharrefs
        # ?? state['name'] = str(state['name'], encodingerrors='xmlcharrefreplace')
        state.update(id=node.id)
        try:
            state.update(alert=node.alert)
        except:
            pass

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
