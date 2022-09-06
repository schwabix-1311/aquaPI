#!/usr/bin/env python

from flask import (
    Flask, Blueprint, current_app, request, render_template
)
from ..sse_util import render_sse_template
from ..machineroom import msg_bus


bp = Blueprint('settings', __name__)


#@bp.route('/settings')
@bp.route('/settings', methods=['GET','POST'])
def settings():
#    if request.method == 'POST':
#        username = request.form['username']
#        password = request.form['password']
    # hint: html <details> can be opened by default or by JS:
    # https://stackoverflow.com/questions/14286406/how-to-set-a-details-element-to-open-by-default-or-via-css
# TODO: need a mechanism to keep a POSTing form (<details>) open, or use JS colapsibles

    bus = current_app.bus
    values = {}

    # TODO: this can be simplified to get_nodes(CTRL) since now jinja has access to app.bus
    # Should keep the parameter with nodes though, as this allows to handle groups of CTRL nodes
    # with same page.
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

    return render_template('pages/settings/index.html.jinja2', update=values)


#@bp.route('/settings', methods=['POST'])
#def settings_post():

