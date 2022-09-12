#!/usr/bin/env python3

import time
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
    # TODO this must iterate a configurable selection of (node.id, attrib), and template must use this
    for node in bus.get_nodes():
        prop_set = node.get_dash()
        for prop in prop_set:
            values[node.id + '.' + prop[0]] = prop[2]

    # For real-time updates through SSE we render the page. All updateable items are
    # given unique identifiers. Function sse_update below can then create or update
    # a dictionary with same id as key and current value.

    # TODO for dashboard (=home) there should be a configurable list of items to show.

    def sse_update():
        bus.changed.wait()
        for node in bus.get_nodes():
            prop_set = node.get_dash()
            for prop in prop_set:
                values[node.id + '.' + prop[0]] = prop[2]
        bus.changed.clear()
        return json.dumps(values)
    return render_sse_template('pages/home/index.html.jinja2', sse_update, values)
