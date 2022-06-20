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

        if True:
            # this are 2 hard-wired temperature controllers with
            # two sensors (averaged) as input and shared output. Simulated nodes!

            # later this will be constructed from configuration storage

            w1_temp = msg_nodes.SensorTemp('Heiz1.IN.1', msg_nodes.Driver('dummy'))
            w1_temp.plugin(self.bus)

            w2_temp = msg_nodes.SensorTemp('Heiz1.IN.2', msg_nodes.Driver('dummy'))
            w2_temp.plugin(self.bus)

            w_temp = msg_nodes.Average('Heiz1.AUX.1', [w1_temp.name,w2_temp.name])
            w_temp.plugin(self.bus)

            w1_ctrl = msg_nodes.CtrlMinimum('Heiz1', w_temp.name, 25.0)
            w1_ctrl.plugin(self.bus)

            w2_ctrl = msg_nodes.CtrlMinimum('Heiz2', w2_temp.name, 25.0)
            w2_ctrl.plugin(self.bus)

            w_or = msg_nodes.Or('Heiz1.AUX.2', [w1_ctrl.name,w2_ctrl.name])
            w_or.plugin(self.bus)

            w_heat = msg_nodes.DeviceSwitch('Heiz1.OUT', [w_or.name])
            w_heat.plugin(self.bus)

        #else:
            wasser_i = msg_nodes.SensorTemp('Wasser', msg_nodes.Driver('dummy'))
            wasser = msg_nodes.CtrlMinimum('Temperatur', wasser_i.name, 24.0)
            wasser_o = msg_nodes.DeviceSwitch('Relais', [wasser.name])
            wasser.plugin(self.bus)
            wasser_o.plugin(self.bus)
            wasser_i.plugin(self.bus)
        log.info(self.broker.get_nodes())
        log.info(self.broker.get_nodes(roles=(msg_bus.BusRole.IN_ENDP)))
        log.info(self.broker.get_nodes(roles=(msg_bus.BusRole.OUT_ENDP)))
        log.info(self.broker.get_nodes(roles=(msg_bus.BusRole.CTRL)))
        log.info(self.broker.get_nodes(roles=(msg_bus.BusRole.AUX)))
        log.info(self.broker.get_nodes(roles=(msg_bus.BusRole.BROKER)))
        #breakpoint()

        log.info("Bus created: %s", str(self.bus))

    #TODO: add a destructor with self.bus.teardown()
