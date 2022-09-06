#!/usr/bin/env python3

from flask import (
    Flask, Blueprint, current_app, render_template, json
)
from ..sse_util import render_sse_template
from ..machineroom import msg_bus


bp = Blueprint('home', __name__)


@bp.route('/')
def home():
    bus = current_app.bus
    values = {}

    names = bus.get_node_names((msg_bus.BusRole.CTRL, msg_bus.BusRole.IN_ENDP))
    for n in names:
        node = bus.get_node(n)
        if node:
            values[n] = node.get_dash()

    def sse_update():
        bus.changed.wait()
        for n in values.copy():
            node = bus.get_node(n)
            if node:
                values[n] = node.get_dash()
        bus.changed.clear()
        return json.dumps(values)
    return render_sse_template('pages/home/index.html.jinja2', sse_update, values)
