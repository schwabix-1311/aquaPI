#!/usr/bin/env python3

import logging
from flask import (Blueprint, render_template)


log = logging.getLogger('pages.spa')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose


bp = Blueprint('spa', __name__)


@bp.route('/')
def spa():

    return render_template('pages/spa.html.jinja2')
