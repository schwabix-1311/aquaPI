#!/usr/bin/env python3

import time
#import os
#from resource import *
#import sys
from flask import (
    Blueprint, render_template, json
)
from .sse_util import render_sse_template


bp = Blueprint('about', __name__)


# for later ...
#def get_cpu():
#    # could read /proc/loadavg
#    return "NYI"
#
#def get_mem(idx):
#    # could read /proc/meminfo or /proc/self/statm
#    return getrusage(RUSAGE_SELF)[idx] + getrusage(RUSAGE_CHILDREN)[idx]
#
#    #TODO: remove const data values
#    sysstate = { 'Platform': os.uname(), \
#                 'Speicher': get_mem(2), \
#                 'CPU_Usage': 0.0 }
#    def sse_update():
#        sysstate['Speicher'] = get_mem(2)
#        sysstate['CPU_Usage'] = get_mem(0) - sysstate['CPU_Usage']
#        return json.dumps(sysstate)


@bp.route('/about')
def about():
    # list of dynamic items for page generation ...
    values = { 'sys': { 'now': time.asctime() }}
    def sse_update():
        # ... and dynamic updates. This may be a superset of above.
        values['sys']['now'] = time.asctime()
        return json.dumps(values)
    return render_sse_template('about.html', sse_update, update=values, delay=1)
