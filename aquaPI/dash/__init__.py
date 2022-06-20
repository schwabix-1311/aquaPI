#!/usr/bin/env python

from flask import (
    Flask, Blueprint, current_app, render_template, json
)
from ..sse_util import render_sse_template
from ..backend import msg_bus
from ..backend import msg_nodes


bp = Blueprint('dash', __name__)


@bp.route('/dash')
def dash():
    broker = current_app.broker
    values = {}

    nodes = broker.get_node_names(msg_bus.BusRole.CTRL)
    values["Controller"] = broker.values_by_names(nodes)   #FIXME use threshold/hysteresis instead

    nodes = broker.get_node_names((msg_bus.BusRole.IN_ENDP,msg_bus.BusRole.AUX))
    values["Inputs"] = broker.values_by_names(nodes)

    nodes = broker.get_node_names(msg_bus.BusRole.OUT_ENDP)
    values["Outputs"] = broker.values_by_names(nodes)

    def sse_update():
        broker.changed.wait()
        values["Controller"] = broker.values_by_names(values["Controller"])
        values["Inputs"] = broker.values_by_names(values["Inputs"].keys())
        values["Outputs"] = broker.values_by_names(values["Outputs"].keys())
        broker.changed.clear()
        return json.dumps(values)
    return render_sse_template('dash/index.html', sse_update, values)
