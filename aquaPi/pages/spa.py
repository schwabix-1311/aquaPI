#!/usr/bin/env python3

import logging
from flask import (Blueprint, render_template)


log = logging.getLogger('/spa')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


bp = Blueprint('spa', __name__)


@bp.route('/')
def spa():

    return render_template('pages/spa.html.jinja2')
