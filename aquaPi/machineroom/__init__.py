#!/usr/bin/env python

import logging
import os
from os import path
import pickle
from .msg_bus import MsgBus
from .msg_nodes import *


log = logging.getLogger('MachineRoom')
log.setLevel(logging.INFO)


class MachineRoom():
    ''' The Machine Room
        The core is a message bus, on which different sensors,
        controllers, devices and auxiliary nodes communicate.
        The Bus also provides the interface to Flask backend.
        Some bus nodes start worker threads (e.g. sensors), the rest
        works in msg handlers and callbacks.
    '''
    def __init__(self, config):
        #TODO: this might move to the DB, currently separate file is handy
        if not path.exists(config['NODES']):
            # construct default controlleri(s) if there's
            # no configuration storage (pickle stream)

            self.bus = MsgBus()  #threaded=True)

            self.create_default_nodes()

            log.info("Bus & Nodes created: %s", str(self.bus))
            # this will pickle the MsgBus, all referenced BusNodes and Drivers
            with open(config['NODES'], 'wb') as p:
                pickle.dump(self.bus, p, protocol=pickle.HIGHEST_PROTOCOL)
            log.info("  ... and saved")

        else:
            # likewise this restores Bus, Nodes and Drivers
            with open(config['NODES'], 'rb') as p:
                self.bus = pickle.load(p)
            log.info("Bus & Nodes loaded")

        log.info("Bus & Nodes created: %s", str(self.bus))
        log.warning(self.bus.get_nodes())

    def create_default_nodes(self):
        single_light = True
        dawn_light = single_light and False
        single_temp = True
        dual_temp = False
        overlapped_temp = dual_temp and True

        if single_light:
            light_schedule = Schedule('Zeitplan 1', '* 14-21 * * *')
            light_schedule.plugin(self.bus)
            light_c = CtrlLight('Beleuchtung', light_schedule.name, fade_time=60) #30*60)
            light_c.plugin(self.bus)

            if not dawn_light:
                light_pwm = SinglePWM('Dimmer', light_c.name, squared=True, maximum=80)
                light_pwm.plugin(self.bus)
            else:
                dawn_schedule = Schedule('Zeitplan 2', '* 22 * * *')
                dawn_schedule.plugin(self.bus)
                dawn_c = CtrlLight('Dämmerlicht', dawn_schedule.name, fade_time=30*60)
                dawn_c.plugin(self.bus)

                light_or = Or('Licht-Oder', [light_c.name,dawn_c.name])
                light_or.plugin(self.bus)
                light_pwm = SinglePWM('Dimmer', light_or.name, squared=True, maximum=80)
                light_pwm.plugin(self.bus)


        if single_temp:
            # single temp sensor -> temp ctrl -> relais
            wasser_i = SensorTemp('Wasser', Driver('dummy', '0x1234'))
            wasser = CtrlMinimum('Temperatur', wasser_i.name, 24.3)
            wasser_o = DeviceSwitch('Heizstab', wasser.name)
            wasser.plugin(self.bus)
            wasser_o.plugin(self.bus)
            wasser_i.plugin(self.bus)

        if dual_temp:
            # 2 temp sensors -> average -> temp ctrl -> relais
            w1_temp = SensorTemp('T-Sensor 1', Driver('dummy', '28-0000x123'))
            w1_temp.plugin(self.bus)

            w2_temp = SensorTemp('T-Sensor 2', Driver('dummy', '28-0000x876'))
            w2_temp.plugin(self.bus)

            w_temp = Average('T-Mittel', [w1_temp.name,w2_temp.name])
            w_temp.plugin(self.bus)

            w1_ctrl = CtrlMinimum('Heizung', w_temp.name, 25.0)
            w1_ctrl.plugin(self.bus)

            w2_ctrl = CtrlMaximum('Kühlung', w_temp.name, 26.5)
            w2_ctrl.plugin(self.bus)

            w_heat = DeviceSwitch('Heizstab', w1_ctrl.name)
            w_heat.plugin(self.bus)

            w_cool = DeviceSwitch('Lüfter', w2_ctrl.name)
            w_cool.plugin(self.bus)

    #TODO: add a destructor with self.bus.teardown()


#   class MyClass:
#   @classmethod
#   def cleanOnExit(cls):
#       # do here your cleaning
#import atexit ; atexit.register(MyClass.cleanOnExit)
