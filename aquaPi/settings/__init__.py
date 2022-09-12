#!/usr/bin/env python

from flask import (
    Flask, Blueprint, current_app, request, render_template
)
from ..machineroom import msg_bus


bp = Blueprint('settings', __name__)


#@bp.route('/settings')
@bp.route('/settings', methods=['GET','POST'])
def settings():
    sub_form = None

    if request.method == 'POST':
        for key in request.form.keys():

            # page has a (sub-) form for each controller. each sets a hidden input with sub_form name,
            # forward this after submit to allow this sub_form to render in unfolded state
            if key=='sub_form':
                sub_form = request.form[key]
                continue

            # all other values are built like  node_id.attr: value -> update node's attribute
            node_attr = key.split('.')
            if len(node_attr) == 2:
                try:
                    new_value = float(request.form[key])
                except ValueError:
                    new_value = request.form[key]
                # FIXME some attributes need further action, e.g. Schedule.cronspec. Can we use property-set for these?
                setattr(current_app.bus.get_node(node_attr[0]), node_attr[1], new_value)

# TODO: need a mechanism to keep a POSTing form (<details>) open, or use JS collapsibles, sub_form= might be it -> DONE, however, we might need to redirect to same page + anchor, otherwise we jump to top of page

    return render_template('pages/settings/index.html.jinja2', sub_form=sub_form)


#@bp.route('/settings', methods=['POST'])
#def settings_post():

