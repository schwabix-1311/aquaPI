#!/usr/bin/env python

import logging
from . import msg_bus
from . import msg_nodes


log = logging.getLogger('BackEnd')
log.setLevel(logging.INFO)


class BackEnd():
    ''' The Machine Room
        The core is a message bus, on which different sensors,
        controllers, devices and auxiliary nodes communicate.
        A BusBroker builds the interface to Flask backend.
        Some bus nodes start worker threads (e.g. sensors), the rest
        works in msg handlers and callbacks.
    '''
    def __init__(self, config):
        self.bus = msg_bus.MsgBus()  #threaded=True)

        self.broker = msg_nodes.BusBroker()
        self.broker.plugin(self.bus)

        # this is a hard-wired tempature controller with
        # two sensors (averaged) as input. Simulated nodes!

        # later this will be constructed from configuration storage

        w1_temp = msg_nodes.SensorTemperature('Temp-hinten', msg_nodes.Driver('dummy'))
        w1_temp.plugin(self.bus)

        w2_temp = msg_nodes.SensorTemperature('Temp-re-vo', msg_nodes.Driver('dummy'))
        w2_temp.plugin(self.bus)

        w_temp = msg_nodes.Average('Temp-Mittelwert', [w1_temp.name,w2_temp.name])
        w_temp.plugin(self.bus)

        w_ctrl = msg_nodes.ControlMinTemp('Wassertemperatur', w_temp.name, 25.0)
        w_ctrl.plugin(self.bus)

        w_heat = msg_nodes.DeviceSwitch('Heizrelais', [w_temp.name])
        w_heat.plugin(self.bus)

        breakpoint()
        log.info(self.broker.get_nodes())

        log.info("Bus created: %s", str(self.bus))

    #TODO: add a destructor with self.bus.teardown()
