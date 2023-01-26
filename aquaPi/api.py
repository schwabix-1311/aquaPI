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
from .machineroom import BusRole
from .machineroom.msg_types import MsgFilter
from .pages.sse_util import send_sse_events

log = logging.getLogger('API')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

# log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
log.setLevel(logging.DEBUG)


bp = Blueprint('api', __name__)


@bp.route('/api/nodes/<node_id>')
def api_node(node_id):
    with_history = request.args.get('add_history', False) in ['true', 'True', '1']

    bus = current_app.bus
    node_id = str(node_id.encode('ascii', 'xmlcharrefreplace'), errors='strict')
    node = bus.get_node(node_id)

    if node:
        # state = {}
        # state.update(id=node.id)
        # state.update(cls=type(node).__name__)
        # state.update(node.__getstate__())
        #
        # # FIXME: node.name shows some non-ascii chars incorrectly, this started with node.id containing xmlcharrefs
        # # ?? state['name'] = str(state['name'], encodingerrors='xmlcharrefreplace')
        #
        # if hasattr(node, 'alert') and node.alert:
        #     state.update(alert=node.alert)
        #
        # log.brief('node id:' + node.id)
        # log.brief('===================')
        # log.debug(state)
        #
        # log.debug('vars:')
        # log.debug(vars)
        # log.debug('locals:')
        # log.debug(locals())
        #
        # return json.dumps(state, default=vars)


        item = node.__getstate__()
        item['type'] = type(node).__name__
        item['role'] = str(node.ROLE).rsplit('.', 1)[1]

        if with_history is False and 'store' in node.__getstate__():
            del item['store']

        # if 'inputs' in item and isinstance(item['inputs'], MsgFilter):
        # log.brief(type(item['inputs']))
        # inputs = item['inputs'].__getstate__()
        # log.brief(item['inputs'])
        # log.brief(type(node.get_inputs()))
        # test = [ for node.get_inputs()]
        # test = [n.__getstate__() for n in node.get_inputs()]
        # log.brief('====================== test:')
        # log.brief(test)
        # items.append(item)

        body = jsonpickle.encode({'result': 'SUCCESS', 'data': item}, unpicklable=False, keys=True)

        return Response(status=HTTPStatus.OK, response=body, mimetype='application/json')
    else:
        return Response(status=HTTPStatus.NOT_FOUND)


@bp.route('/api/nodes/', methods=['GET'])
def api_nodes():
    bus = current_app.bus
    node_ids = [node.id for node in bus.get_nodes()]

    # is_ajax_request = request.headers.get('X-Requested-With', '') == 'XMLHttpRequest'

    # if not is_ajax_request:
    #     return Response(status=HTTPStatus.NOT_IMPLEMENTED)

    if node_ids:
        return json.dumps(node_ids)
    else:
        return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)


@bp.route('/api/config/dashboard', methods=['GET', 'POST'])
def api_dashboard():
    is_ajax_request = request.headers.get('X-Requested-With', '') == 'XMLHttpRequest'

    if not is_ajax_request:
        return Response('Only AJAX request is implemented', status=HTTPStatus.BAD_REQUEST)

    if request.method == 'POST':
        data = request.json

        visible_tiles = [item['comp'] + '.' + item['id'] for item in data if bool(item['vis'])]

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

            body = json.dumps({'result': 'SUCCESS', 'resultMsg': 'Saved dashboard configuration', 'data': data},
                              sort_keys=True)
            return Response(status=HTTPStatus.OK, response=body, mimetype='application/json')

        except Exception as ex:
            log.exception('Received invalid dashboard configuration, ignoring.')
            # flash(str(ex), 'error')
            # return redirect('/')
            body = json.dumps({'result': 'ERROR', 'resultMsg': 'Could not save dashboard configuration!', 'data': data},
                              sort_keys=True)
            return Response(status=HTTPStatus.NOT_ACCEPTABLE, response=body, mimetype='application/json')

    elif request.method == 'GET':
        with_history = request.args.get('add_history', False) in ['true', 'True', '1']

        bus = current_app.bus
        items = []
        for node in bus.get_nodes():
            item = node.__getstate__()
            item['type'] = type(node).__name__
            item['role'] = str(node.ROLE).rsplit('.', 1)[1]

            if with_history is False and 'store' in node.__getstate__():
                del item['store']

            # if 'inputs' in item and isinstance(item['inputs'], MsgFilter):
                # log.brief(type(item['inputs']))
                # inputs = item['inputs'].__getstate__()
                # log.brief(item['inputs'])
                # log.brief(type(node.get_inputs()))
                # test = [ for node.get_inputs()]
                # test = [n.__getstate__() for n in node.get_inputs()]
                # log.brief('====================== test:')
                # log.brief(test)

            items.append(item)

        body = jsonpickle.encode({'result': 'SUCCESS', 'data': items}, unpicklable=False, keys=True)

        return Response(status=HTTPStatus.OK, response=body, mimetype='application/json')
    else:
        return Response(status=HTTPStatus.METHOD_NOT_ALLOWED)


@bp.route('/api/sse', methods=['GET'])
def api_sse():
    if request.headers.get('accept') != 'text/event-stream':
        return Response('MUST ACCEPT content type text/event-stream', status=HTTPStatus.BAD_REQUEST)

    bus = current_app.bus

    nodes = bus.get_nodes()
    if not bus.dash_tiles:
        # JS and checkbox binding does not work well for python
        # bool -> cast to int; on return python will interpret it correctly
        bus.dash_tiles = [
            {'identifier': n.identifier, 'name': 'Steuerung ' + n.name, 'comp': n.__class__.__name__, 'id': n.id,
             'vis': int(True)} for n in bus.get_nodes(BusRole.CTRL)]
        bus.dash_tiles += [
            {'identifier': n.identifier, 'name': 'Eingang ' + n.name, 'comp': n.__class__.__name__, 'id': n.id,
             'vis': int(False)} for n in bus.get_nodes(BusRole.IN_ENDP)]
        bus.dash_tiles += [
            {'identifier': n.identifier, 'name': 'Ausgang ' + n.name, 'comp': n.__class__.__name__, 'id': n.id,
             'vis': int(False)} for n in bus.get_nodes(BusRole.OUT_ENDP)]
        bus.dash_tiles += [
            {'identifier': n.identifier, 'name': 'Verknüpfung ' + n.name, 'comp': n.__class__.__name__, 'id': n.id,
             'vis': int(False)} for n in bus.get_nodes(BusRole.AUX)]
        bus.dash_tiles += [
            {'identifier': n.identifier, 'name': 'Diagramm ' + n.name, 'comp': n.__class__.__name__, 'id': n.id,
             'vis': int(False)} for n in bus.get_nodes(BusRole.HISTORY)]

        # this will need 1..n HistoryNodes, their inputs define what will be on a chart, they feed e.g. InfluxDB, the Vue comp(s) will show one chart per HistNode with all inputs
        # bus.dash_tiles += [{'name': 'Diagramm ' + n.name, 'comp': 'Chart', 'id': n.id, 'vis': int(False)}  for n in bus.get_nodes(BusRole.HISTORY)]

    def sse_update():
        changed_ids = bus.wait_for_changes()
        return json.dumps(changed_ids)

    return send_sse_events(sse_update)
