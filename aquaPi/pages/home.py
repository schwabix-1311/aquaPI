#!/usr/bin/env python3

import logging
from flask import (Blueprint, current_app, flash, json, redirect, request)

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

    nodes = bus.get_nodes()
    if not bus.dash_tiles:
        # JS and checkbox binding does not work well for python
        # bool -> cast to int; on return python wil interpret it correctly
        bus.dash_tiles = [{'name': 'Steuerung ' + n.name, 'comp': n.__class__.__name__, 'id': n.id, 'vis': int(True)} for n in bus.get_nodes(BusRole.CTRL)]
        bus.dash_tiles += [{'name': 'Eingang ' + n.name, 'comp': n.__class__.__name__, 'id': n.id, 'vis': int(False)} for n in bus.get_nodes(BusRole.IN_ENDP)]
        bus.dash_tiles += [{'name': 'Ausgang ' + n.name, 'comp': n.__class__.__name__, 'id': n.id, 'vis': int(False)} for n in bus.get_nodes(BusRole.OUT_ENDP)]
        bus.dash_tiles += [{'name': 'Verknüpfung ' + n.name, 'comp': n.__class__.__name__, 'id': n.id, 'vis': int(False)} for n in bus.get_nodes(BusRole.AUX)]
        bus.dash_tiles += [{'name': 'Diagramm ' + n.name, 'comp': n.__class__.__name__, 'id': n.id, 'vis': int(False)} for n in bus.get_nodes(BusRole.HISTORY)]

        # this will need 1..n HistoryNodes, their inputs define what will be on a chart, they feed e.g. InfluxDB, the Vue comp(s) will show one chart per HistNode with all inputs
        # bus.dash_tiles += [{'name': 'Diagramm ' + n.name, 'comp': 'Chart', 'id': n.id, 'vis': int(False)}  for n in bus.get_nodes(BusRole.HISTORY)]

    def sse_update():
        changed_ids = bus.wait_for_changes()
        return json.dumps(changed_ids)

    return render_sse_template('pages/home.html.jinja2', sse_update, tiles=bus.dash_tiles, nodes=nodes)


@bp.route('/', methods=['POST'])
def home_config():
    bus = current_app.bus
    mr = current_app.machineroom

    log.brief('POST for /')
    log.brief(request.form)

    try:
        log.debug('DEBUG: find the current route in request')
        for tile in bus.dash_tiles:
            vis = int(False)
            key = tile['comp'] + '.' + tile['id']
            if key in request.form:
                vis = bool(request.form[key])
                log.debug('  found tile %s: %r', key, vis)
            log.debug('-> set tile %s to %r', key, vis)
            tile['vis'] = int(vis)

        mr.save_nodes(bus)
        log.brief('Saved changes')
        return ('OK', 204)  # Success, no content

    except Exception as ex:
        log.exception('Received invalid dashboard configuration, ignoring.')
        flash(str(ex), 'error')
        return redirect('/')
