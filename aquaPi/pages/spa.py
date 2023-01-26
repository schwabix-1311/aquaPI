#!/usr/bin/env python3

import logging
import jsonpickle
from flask import (Blueprint, current_app, flash, request, render_template)

from ..machineroom import BusRole


log = logging.getLogger('/spa')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


bp = Blueprint('spa', __name__)


@bp.route('/')
def spa():
    # bus = current_app.bus
    #
    # nodes = bus.get_nodes()
    # if not bus.dash_tiles:
    #     # JS and checkbox binding does not work well for python
    #     # bool -> cast to int; on return python will interpret it correctly
    #     bus.dash_tiles = [{'identifier': n.identifier, 'name': 'Steuerung ' + n.name, 'comp': n.__class__.__name__, 'id': n.id, 'vis': int(True)} for n in bus.get_nodes(BusRole.CTRL)]
    #     bus.dash_tiles += [{'identifier': n.identifier, 'name': 'Eingang ' + n.name, 'comp': n.__class__.__name__, 'id': n.id, 'vis': int(False)} for n in bus.get_nodes(BusRole.IN_ENDP)]
    #     bus.dash_tiles += [{'identifier': n.identifier, 'name': 'Ausgang ' + n.name, 'comp': n.__class__.__name__, 'id': n.id, 'vis': int(False)} for n in bus.get_nodes(BusRole.OUT_ENDP)]
    #     bus.dash_tiles += [{'identifier': n.identifier, 'name': 'Verknüpfung ' + n.name, 'comp': n.__class__.__name__, 'id': n.id, 'vis': int(False)} for n in bus.get_nodes(BusRole.AUX)]
    #     bus.dash_tiles += [{'identifier': n.identifier, 'name': 'Diagramm ' + n.name, 'comp': n.__class__.__name__, 'id': n.id, 'vis': int(False)} for n in bus.get_nodes(BusRole.HISTORY)]

    return render_template('pages/spa.html.jinja2')
