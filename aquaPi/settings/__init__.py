#!/usr/bin/env python3

from flask import (
    Flask, Blueprint, current_app, flash, request, render_template
)
import logging
from ..machineroom import msg_bus

log = logging.getLogger('Settings')
log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

bp = Blueprint('settings', __name__)


# @bp.route('/settings')
@bp.route('/settings', methods=['GET', 'POST'])
def settings():
    bus = current_app.bus
    mr = current_app.machineroom
    sub_form = None

    if request.method == 'POST':
        success = True
        for key in request.form.keys():

            # page has a (sub-) form for each controller. each sets a hidden input with sub_form name,
            # forward this after submit to allow this sub_form to render in unfolded state
            if key == 'sub_form':
                sub_form = request.form[key]
                continue

            # all other values are built like  node_id.attr: value -> update node's attribute
            node_attr = key.split('.')
            if len(node_attr) == 2:
                try:
                    new_value = float(request.form[key])
                except ValueError:
                    new_value = request.form[key]
                try:
                    setattr(bus.get_node(node_attr[0]), node_attr[1], new_value)
                except Exception as ex:
                    # FIXME translation of ex text??
                    # TODO highlight corresponding input
                    success = False
                    flash(str(ex), 'danger')

        # TODO: validation in setters must raise exceptions
        if success:
            mr.save_nodes(bus)
            log.brief("Saved changes")
            flash('Saved changes', 'success')

    # TODO: need a mechanism to keep a POSTing form (<details>) open, or use JS collapsibles, sub_form= might be it
    # -> DONE, however, we might need to redirect to same page + anchor, otherwise we jump to top of page
    return render_template('pages/settings/index.html.jinja2', sub_form=sub_form)

# @bp.route('/settings', methods=['POST'])
# def settings_post():
