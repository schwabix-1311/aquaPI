#!/usr/bin/env python3

import logging
from flask import (Blueprint, current_app, json)

from ..machineroom import (MsgBus, BusRole)
from .sse_util import render_sse_template


log = logging.getLogger('/home')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


bp = Blueprint('home', __name__)


@bp.route('/')
def home():
    bus = current_app.bus

    # TODO change to a configurable selection [node.id, ...]
    nodes = bus.get_nodes()
    dash_tiles = [{'name': 'Controller ' + n.name, 'comp': n.__class__.__name__, 'id': n.id, 'vis': int(True)}  for n in bus.get_nodes(BusRole.CTRL)]
    dash_tiles += [{'name': 'Node ' + n.name, 'comp': 'BusNode', 'id': n.id, 'vis': int(False)}  for n in bus.get_nodes(())] #BusRole.IN_ENDP, BusRole.OUT_ENDP))]
    dash_tiles += [{'name': 'Chart ' + n.name, 'comp': 'Chart', 'id': n.id, 'vis': int(False)}  for n in bus.get_nodes((BusRole.IN_ENDP, BusRole.OUT_ENDP))]

    log.debug(dash_tiles)

    def sse_update():
        changed_ids = bus.wait_for_changes()
        return json.dumps(changed_ids)

    return render_sse_template('pages/home.html.jinja2', sse_update, tiles=dash_tiles, nodes=nodes)
