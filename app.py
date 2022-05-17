#!/usr/bin/env python3

import os
from resource import *
import time
import sys

from flask import Flask, render_template, json
from sse_util import render_sse_template
sys.path.insert(0, '.')

from backend.msg_bus import *
from backend.inputs import *


#====================#

broker = None

running = True

def create_bus():
    global broker
    bus = MsgBus()  #threaded=True)

    broker = BusBroker()
    broker.plugin(bus)

    w1_temp = SensorTemperature('Wasser1', Driver('dummy'))
    w1_temp.plugin(bus)

    w2_temp = SensorTemperature('Wasser2', Driver('dummy'))
    w2_temp.plugin(bus)

    w_temp = Average('Wasser', [w1_temp.name,w2_temp.name])
    w_temp.plugin(bus)

    w_ctrl = ControlMinTemp('Wasserregelung', w_temp.name, 25.0)
    w_ctrl.plugin(bus)

    w_heat = DeviceSwitch('Heizrelais', [w_ctrl.name])
    w_heat.plugin(bus)


app = Flask(__name__)
#TODO: SECRET_KEY for cookies
app.config.from_mapping({'HOST': '0.0.0.0','ENV':'development','DEBUG': True})

# do not start thread, unless 'flask run', or started as python main
if ('run' in sys.argv) or (__name__ == "__main__"):
    create_bus()


#====================#

def get_cpu():
    # could read /proc/loadavg
    return "NYI"

def get_mem(idx):
    # could read /proc/meminfo or /proc/self/statm
    return getrusage(RUSAGE_SELF)[idx] + getrusage(RUSAGE_CHILDREN)[idx]

@app.route('/')
def hello():
    #TODO: remove const data values
    sysstate = { 'Uhrzeit': time.asctime(), \
                 'Platform': os.uname(), \
                 'Speicher': get_mem(2), \
                 'CPU_Usage': 0.0 }
    def sse_update():
        sysstate['Uhrzeit'] = time.asctime()
        sysstate['Speicher'] = get_mem(2)
        sysstate['CPU_Usage'] = get_mem(0) - sysstate['CPU_Usage']
        return json.dumps(sysstate)
    return render_sse_template('index.html', sse_update, update=sysstate, delay=5)


@app.route('/dash')
def dash():
    global broker
    def sse_update():
        broker.changed.wait()
        #broker.values['Uhrzeit'] = time.asctime()
        broker.changed.clear()
        return json.dumps(broker.values)
    return render_sse_template('dash.html', sse_update, update=broker.values, delay=None)


@app.route('/temp')
def temp():
    return render_template('temp.html')


@app.route('/config')
def config():
    return render_template('config.html')


@app.route('/about')
def about():
    return render_template('about.html')


if __name__ == "__main__":

    print("WARNING: it is not recommended to run this way.\nThe worker thread will show unexpected bahavior!\b\n")
    time.sleep(5)
    app.run(host="0.0.0.0", debug=True)
