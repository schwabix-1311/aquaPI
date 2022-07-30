#!/usr/bin/env python

from flask import (
    Flask, Blueprint, current_app, render_template, json
)
from ..sse_util import render_sse_template
from ..machineroom import msg_bus


bp = Blueprint('settings', __name__)


@bp.route('/settings')
def settings():
    bus = current_app.bus
    values = {}

    names = bus.get_node_names(msg_bus.BusRole.CTRL)
    for n in names:
        node = bus.get_node(n)
        if node:
            settings = node.get_settings()
            in_name = node.get_inputs()[0]
            settings['>> Driven by'] = in_name
            in_node = bus.get_node(in_name)
            settings.update(in_node.get_settings())
            out_name = node.get_outputs()[0]
            settings['>> Driving'] = out_name
            out_node = bus.get_node(out_name)
            settings.update(out_node.get_settings())

            values[n] = settings

    return render_template('settings/index.html', update=values)
