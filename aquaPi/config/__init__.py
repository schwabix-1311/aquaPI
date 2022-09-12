#!/usr/bin/env python

from flask import (
    Flask, Blueprint, render_template
)
#from ..sse_util import render_sse_template
from ..machineroom import msg_bus


bp = Blueprint('config', __name__)


@bp.route('/config')
def config():
    # this template accesses nodes of all roles directly through context var "bus"
    # no real-time updates

    return render_template('pages/config/index.html.jinja2')
