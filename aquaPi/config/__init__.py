#!/usr/bin/env python

from flask import (
    Flask, Blueprint, current_app, render_template, json
)
from ..sse_util import render_sse_template
from ..machineroom import msg_bus
from ..machineroom import msg_nodes


bp = Blueprint('config', __name__)


@bp.route('/config')
def config():
    broker = current_app.broker
    values = {}

#  ctrl.node
#  in.node
#  out.node
#  aux.node
    values["ctrl"] = broker.get_nodes(msg_bus.BusRole.CTRL)
    values["aux"] = broker.get_nodes(msg_bus.BusRole.AUX)
    values["in"] = broker.get_nodes(msg_bus.BusRole.IN_ENDP)
    values["out"] = broker.get_nodes(msg_bus.BusRole.OUT_ENDP)

    return render_template('config/index.html', update=values)
