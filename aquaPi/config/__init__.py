#!/usr/bin/env python

from flask import (
    Flask, Blueprint, current_app, render_template, json
)
#from ..sse_util import render_sse_template
from ..machineroom import msg_bus


bp = Blueprint('config', __name__)


@bp.route('/config')
def config():
    bus = current_app.bus
    values = {}

#  ctrl.node
#  in.node
#  out.node
#  aux.node
    values["ctrl"] = bus.get_nodes(msg_bus.BusRole.CTRL)
    values["aux"] = bus.get_nodes(msg_bus.BusRole.AUX)
    values["in"] = bus.get_nodes(msg_bus.BusRole.IN_ENDP)
    values["out"] = bus.get_nodes(msg_bus.BusRole.OUT_ENDP)

    return render_template('pages/config/index.html.jinja2', update=values)
