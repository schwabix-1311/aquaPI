#import functools
import time
from flask import (
    Blueprint, render_template, json
)
from .sse_util import render_sse_template


bp = Blueprint('about', __name__)


@bp.route('/about')
def about():
    # list of dynamic items for page generation ...
    values = { 'sys': { 'now': time.asctime() }}
    def sse_update():
        # ... and dynamic updates. This may be a superset of above.
        values['sys']['now'] = time.asctime()
        return json.dumps(values)
    return render_sse_template('about.html', sse_update, update=values, delay=1)
