#!/usr/bin/env python3

import logging
from flask import (Blueprint, render_template)


log = logging.getLogger('pages.spa')


bp = Blueprint('spa', __name__)


@bp.route('/')
def spa():
    # the SPA shell itself is always served, even for unauthenticated
    # users - it forces its own login dialog open (see
    # AquapiLoginDialog.vue), which also covers password reset; there is
    # no separate server-rendered login page anymore
    return render_template('pages/spa.html.jinja2')
