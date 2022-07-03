#!/usr/bin/env python

import logging
from .msg_bus import MsgBus
from .msg_nodes import *


log = logging.getLogger('MachineRoom')
log.setLevel(logging.INFO)


class MachineRoom():
    ''' The Machine Room
        The core is a message bus, on which different sensors,
        controllers, devices and auxiliary nodes communicate.
        A BusBroker builds the interface to Flask backend.
        Some bus nodes start worker threads (e.g. sensors), the rest
        works in msg handlers and callbacks.
    '''
    def __init__(self, config):
        self.bus = MsgBus()  #threaded=True)

        self.broker = BusBroker()
        self.broker.plugin(self.bus)

        #TODO  temporary, until construction from config data works
        # later this will be constructed from configuration storage

        single_light = True
        single_temp = False
        dual_temp = False
        overlapped_temp = dual_temp and True

        if single_light:
            light_schedule = Schedule('Zeitplan 1', '* 14-21 * * *')
            light = CtrlLight('Licht 1c', light_schedule.name, fade_time=60) #30*60)
            light_o = SinglePWM('PWM-W', light.name, squared=True, maximum=80)
            light.plugin(self.bus)
            light_o.plugin(self.bus)
            light_schedule.plugin(self.bus)

        if single_temp:
            # single temp sensor -> temp ctrl -> relais
            wasser_i = SensorTemp('Wasser', Driver('dummy'))
            wasser = CtrlMinimum('Temperatur', wasser_i.name, 24.0)
            wasser_o = DeviceSwitch('Relais', wasser.name)
            wasser.plugin(self.bus)
            wasser_o.plugin(self.bus)
            wasser_i.plugin(self.bus)

        if dual_temp:
            # 2 temp sensors -> average -> temp ctrl -> relais
            w1_temp = SensorTemp('Heiz1.IN.1', Driver('dummy'))
            w1_temp.plugin(self.bus)

            w2_temp = SensorTemp('Heiz1.IN.2', Driver('dummy'))
            w2_temp.plugin(self.bus)

            w_temp = Average('Heiz1.AUX.1', [w1_temp.name,w2_temp.name])
            w_temp.plugin(self.bus)

            w1_ctrl = CtrlMinimum('Heiz1', w_temp.name, 25.0)
            w1_ctrl.plugin(self.bus)

            if not overlapped_temp:
                w_heat = DeviceSwitch('Heiz1.OUT', w1_ctrl.name)
                w_heat.plugin(self.bus)
            else:
                w2_ctrl = CtrlMinimum('Heiz2', w2_temp.name, 25.0)
                w2_ctrl.plugin(self.bus)

                w_or = Or('Heiz1.AUX.2', [w1_ctrl.name,w2_ctrl.name])
                w_or.plugin(self.bus)

                w_heat = DeviceSwitch('Heiz1.OUT', w_or.name)
                w_heat.plugin(self.bus)

        log.info(self.broker.get_nodes())
        #breakpoint()

        log.info("Bus created: %s", str(self.bus))

    #TODO: add a destructor with self.bus.teardown()

#   class MyClass:
#   @classmethod
#   def cleanOnExit(cls):
#       # do here your cleaning
#import atexit ; atexit.register(MyClass.cleanOnExit)
