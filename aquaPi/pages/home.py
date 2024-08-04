#!/usr/bin/env python3

import logging
from flask import (Blueprint, current_app, json)

from ..machineroom import BusRole
from .sse_util import render_sse_template

log = logging.getLogger('/home')
log.brief = log.warning  # alias, warning used as brief info, info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


bp = Blueprint('home', __name__)


#TODO this was /home, based on Jinja templates, should be obsoleted by SPA architecture

@bp.route('/home')
def home():
    bus = current_app.bus

    nodes = bus.get_nodes()

    def sse_update():
        changed_ids = bus.wait_for_changes()
        return json.dumps(changed_ids)

    return render_sse_template('pages/home.html.jinja2', sse_update,
                               tiles=bus.dash_tiles, nodes=nodes)
