#!/usr/bin/env python3

import logging
from flask import (Blueprint, abort, render_template)


log = logging.getLogger('pages.spa')


bp = Blueprint('spa', __name__)


@bp.route('/', defaults={'page': ''})
@bp.route('/<path:page>')
def spa(page):
    # the SPA shell itself is always served, even for unauthenticated
    # users - it forces its own login dialog open (see
    # AquapiLoginDialog.vue), which also covers password reset; there is
    # no separate server-rendered login page anymore
    #
    # the '/<path:page>' rule also catches vue-router's history-mode
    # client-side routes (e.g. /wiring, /parameters) on a direct load or
    # refresh, since Flask now sees the full path instead of everything
    # after a '#'. It must not swallow genuine /api/ 404s though - no
    # more-specific catch-all is registered for that prefix, so an
    # unmatched /api/... path would otherwise land here too.
    if page.startswith('api/'):
        abort(404)
    return render_template('pages/spa.html.jinja2')
