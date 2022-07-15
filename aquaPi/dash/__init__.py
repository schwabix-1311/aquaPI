#!/usr/bin/env python

from flask import (
    Flask, Blueprint, current_app, render_template, json
)
from ..sse_util import render_sse_template
from ..machineroom import msg_bus


bp = Blueprint('dash', __name__)


@bp.route('/dash')
def dash():
    bus = current_app.bus
    values = {}

    nodes = bus.get_node_names(msg_bus.BusRole.CTRL)
    values["Controller"] = bus.values_by_names(nodes)   #FIXME use threshold/hysteresis instead

    nodes = bus.get_node_names((msg_bus.BusRole.IN_ENDP,msg_bus.BusRole.AUX))
    values["Inputs"] = bus.values_by_names(nodes)

    nodes = bus.get_node_names(msg_bus.BusRole.OUT_ENDP)
    values["Outputs"] = bus.values_by_names(nodes)

    def sse_update():
        bus.changed.wait()
        values["Controller"] = bus.values_by_names(values["Controller"])
        values["Inputs"] = bus.values_by_names(values["Inputs"].keys())
        values["Outputs"] = bus.values_by_names(values["Outputs"].keys())
        bus.changed.clear()
        return json.dumps(values)
    return render_sse_template('dash/index.html', sse_update, values)
