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
    # we can filter broker's list for page generation
    values = {}
    values["ctrl"] = broker.values_by_role(msg_bus.BusRole.CONTROLLER)
    def sse_update():
        broker.changed.wait()
        values["ctrl"] = broker.values_by_role(msg_bus.BusRole.CONTROLLER)
        broker.changed.clear()
        return json.dumps(broker.values)
    return render_sse_template('dash/index.html', sse_update, values)
