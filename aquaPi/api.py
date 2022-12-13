#!/usr/bin/env python3

import logging
# import time
# import os
# from resource import *
# import sys
import jsonpickle

from flask import (
    Blueprint, current_app, json, Response, request
)
from http import HTTPStatus

log = logging.getLogger('API')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


bp = Blueprint('api', __name__)


@bp.route('/api/nodes/<node_id>')
def api_node(node_id):
    bus = current_app.bus
    node_id = str(node_id.encode('ascii', 'xmlcharrefreplace'), errors='strict')
    node = bus.get_node(node_id)

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


@bp.route('/api/nodes/', methods=['GET'])
def api_nodes():
    bus = current_app.bus
    node_ids = [node.id for node in bus.get_nodes()]

    # is_ajax_request = request.headers.get('X-Requested-With') and request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    # if not is_ajax_request:
    #     return Response(status=HTTPStatus.NOT_IMPLEMENTED)

    if node_ids:
        return json.dumps(node_ids)
    else:
        return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)


@bp.route('/api/config/dashboard', methods=['GET', 'POST'])
def api_dashboard():
    is_ajax_request = request.headers.get('X-Requested-With') and request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if not is_ajax_request:
        return Response(status=HTTPStatus.NOT_IMPLEMENTED)

    if request.method == 'POST':
        data = request.json

        visible_tiles = [item['comp'] + '.' + item['id']  for item in data if bool(item['vis'])]

        bus = current_app.bus
        mr = current_app.machineroom

        try:
            log.debug('DEBUG: find the current route in request')
            for tile in bus.dash_tiles:
                key = tile['comp'] + '.' + tile['id']
                # vis = int(False)
                # if key in request.form:
                #     vis = bool(request.form[key])
                #     log.debug('  found tile %s: %r', key, vis)
                # log.debug('-> set tile %s to %r', key, vis)
                # tile['vis'] = int(vis)
                tile['vis'] = int(key in visible_tiles)

            mr.save_nodes(bus)
            log.brief('Saved changes')
            # return ('OK', 204)  # Success, no content

            body = json.dumps({'result': 'SUCCESS', 'resultMsg': 'Saved dashboard configuration', 'data': data}, sort_keys=True)
            return Response(status=HTTPStatus.OK, response=body, mimetype='application/json')

        except Exception as ex:
            log.exception('Received invalid dashboard configuration, ignoring.')
            # flash(str(ex), 'error')
            # return redirect('/')
            body = json.dumps({'result': 'ERROR', 'resultMsg': 'Could not save dashboard configuration!', 'data': data}, sort_keys=True)
            return Response(status=HTTPStatus.NOT_ACCEPTABLE, response=body, mimetype='application/json')

    elif request.method == 'GET':
        bus = current_app.bus
        items = []
        for node in bus.get_nodes():
            log.brief('node:', node)
            items.append(node)

        body = jsonpickle.encode({'result': 'SUCCESS', 'data': items}, unpicklable=False, keys=True)

        # log.brief('body')
        # log.brief(body)

        return Response(status=HTTPStatus.OK, response=body, mimetype='application/json')
    else:
        return Response(status=HTTPStatus.METHOD_NOT_ALLOWED)
