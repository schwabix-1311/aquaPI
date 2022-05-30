#!/usr/bin/env python

from flask import (
    Flask, Blueprint, current_app, render_template, json
)
from ..sse_util import render_sse_template
from ..backend import msg_bus
from ..backend import msg_nodes


bp = Blueprint('config', __name__)


@bp.route('/config')
def dash():
    broker = current_app.broker
    # we can also add other data
    values = {}
    values["Controller"] = broker.values_by_role(msg_bus.BusRole.CONTROLLER)
    values["Inputs"] = broker.values_by_role(msg_bus.BusRole.IN_ENDP)
    values["Outputs"] = broker.values_by_role(msg_bus.BusRole.OUT_ENDP)
    values["Helpers"] = broker.values_by_role(msg_bus.BusRole.AUXILIARY)
    def sse_update():
        broker.changed.wait()
        values["Controller"] = broker.values_by_role(msg_bus.BusRole.CONTROLLER)
        values["Inputs"] = broker.values_by_role(msg_bus.BusRole.IN_ENDP)
        values["Outputs"] = broker.values_by_role(msg_bus.BusRole.OUT_ENDP)
        values["Helpers"] = broker.values_by_role(msg_bus.BusRole.AUXILIARY)
        broker.changed.clear()
        return json.dumps(values)
    return render_sse_template('config/index.html', sse_update, values)
