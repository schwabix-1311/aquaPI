#!/usr/bin/env python3

import logging
from flask import (
    Blueprint, current_app, json
)
# import time

from ..sse_util import render_sse_template


log = logging.getLogger('/home')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


bp = Blueprint('home', __name__)


@bp.route('/')
def home():
    bus = current_app.bus

    # TODO change to a configurable selection [node.id, ...]
    nodes = bus.get_nodes()
    log.debug(nodes)

    def sse_update():
        nodes = bus.wait_for_changes()
        return json.dumps(nodes)

    return render_sse_template('pages/home.html.jinja2', sse_update, nodes)
