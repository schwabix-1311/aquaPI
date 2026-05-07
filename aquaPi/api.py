#!/usr/bin/env python3

import logging

from http import HTTPStatus
import jsonpickle  # type: ignore[import-untyped]
from flask import (Blueprint, current_app, json, Response, request)

from .machineroom import (MachineRoom, MsgBus)
from .machineroom.msg_bus import BusRole
from .pages.sse_util import send_sse_events


log = logging.getLogger('aquaPi.api')
log.brief = log.warning  # alias, warning used as brief info, info is verbose


bp = Blueprint('api', __name__)


def the_bus() -> MsgBus | None:
    """ access the global object MachineRoom
    """
    mr: MachineRoom = current_app.extensions['machineroom']
    return mr.bus


@bp.route('/api/nodes/')
def api_nodes() -> Response:
    """ return array of all node's ids
    """
    bus = the_bus()
    if bus:
        node_ids = [node.id for node in
                    sorted(bus.get_nodes(), key=lambda node: node.ROLE.value)]
        if node_ids:
            body = json.dumps(node_ids)
            log.debug('API nodes: %s', body)
            return Response(status=HTTPStatus.OK, response=body, mimetype='application/json')
    return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)


@bp.route('/api/nodes/<node_id>')
def api_node(node_id: str) -> Response:
    """ return state of a single node
    """
    bus = the_bus()
    if bus:
        node_id = str(node_id.encode('ascii', 'xmlcharrefreplace'), errors='strict')
        node = bus.get_node(node_id)

        if node:
            item = node.__getstate__()
            item['type'] = type(node).__name__
            item['role'] = str(node.ROLE).rsplit('.', 1)[1]

            if hasattr(node, 'alert') and node.alert:
                item['alert'] = node.alert

            body = jsonpickle.encode({'result': 'SUCCESS', 'data': item},
                                     unpicklable=False, keys=True)
            log.debug('API nodes/%s: %s', node_id, body)
            return Response(status=HTTPStatus.OK, response=body, mimetype='application/json')

        return Response(status=HTTPStatus.NOT_FOUND)

    return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)


@bp.route('/api/history/')
def api_history_nodes() -> Response:
    """ return array of all history node ids
    """
    bus = the_bus()
    if bus:
        node_ids = [node.id for node in bus.get_nodes(BusRole.HISTORY)]
        if node_ids:
            body = json.dumps(node_ids)
            log.debug('API history: %s', body)
            return Response(status=HTTPStatus.OK, response=body, mimetype='application/json')

        return Response(status=HTTPStatus.NOT_FOUND)

    return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)


@bp.route('/api/history/<node_id>')
def api_history(node_id: str) -> Response:
    """ return a single history, may contains several series
        optionally starting at specified age, and clustered by step.
        Clustering ATM only works whith the real DB, in-mem DB can't cluster
    """
    bus = the_bus()
    if bus:
        node_id = str(node_id.encode('ascii', 'xmlcharrefreplace'), errors='strict')
        node = bus.get_node(node_id)

        start = int(request.args.get('start', 0))
        step = int(request.args.get('step', 0))

        if node:
            if hasattr(node, 'get_history'):
                hist = node.get_history(start, step)

                body = json.dumps({'result': 'SUCCESS', 'data': hist}, sort_keys=False)
                log.debug('API history/%s (%d/%d): %s', node_id, start, step, body)
                return Response(status=HTTPStatus.OK, response=body, mimetype='application/json')

            return Response(status=HTTPStatus.BAD_REQUEST)

        return Response(status=HTTPStatus.NOT_FOUND)

    return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)


@bp.route('/api/sse', methods=['GET'])
def api_sse() -> Response:
    """ API to get SSE updates as an array of ids of modified nodes
    """
    if request.headers.get('accept') != 'text/event-stream':
        return Response('MUST ACCEPT content type text/event-stream', status=HTTPStatus.BAD_REQUEST)

    bus = the_bus()

    def sse_update():
        changed_ids = bus.wait_for_changes()
        log.debug('API sse reply: %r', changed_ids)
        return json.dumps([id for id in changed_ids])

    return send_sse_events(sse_update)
