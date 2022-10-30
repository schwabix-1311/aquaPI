#!/usr/bin/env python3

import logging
from flask import (
    Blueprint, render_template
)

# from ..sse_util import render_sse_template
# from ..machineroom import msg_bus

log = logging.getLogger('/config')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


bp = Blueprint('config', __name__)


@bp.route('/config')
def config():
    # this template accesses nodes of all roles directly through context var "bus"
    # no real-time updates

    return render_template('pages/config.html.jinja2')
