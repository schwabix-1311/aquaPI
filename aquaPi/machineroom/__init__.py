#!/usr/bin/env python

import logging
import os
from os import path
import pickle
from .msg_bus import MsgBus
from .msg_nodes import *


log = logging.getLogger('MachineRoom')
log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose


class MachineRoom:
    """ The Machine Room
        The core is a message bus, on which different sensors,
        controllers, devices and auxiliary nodes communicate.
        The Bus also provides the interface to Flask backend.
        Some bus nodes start worker threads (e.g. sensors), the rest
        works in msg handlers and callbacks.
    """
    def __init__(self, config):
        """ Create everything needed to get the machinery going.
            So far the only thing here is the bus.
        """
        #TODO: this might move to the DB, currently separate file is handy
        self.bus_storage = config['NODES']

        if not path.exists(self.bus_storage):
            self.bus = MsgBus()  #threaded=True)

            log.brief("=== There are no controllers defined, creating default")
            self.create_default_nodes()
            self.save_nodes(self.bus)
            log.brief("=== Successfully created Bus and default Nodes")
            log.brief("  ... and saved to %s", self.bus_storage)

        else:
            log.brief("=== Loading Bus & Nodes from %s", self.bus_storage)
            self.bus = self.restore_nodes()

        log.brief("%s", str(self.bus))
        log.info(self.bus.get_nodes())

    def __del__(self):
        """ Persist the required objects, cleanup
            (other languages call this a destructor)
        """
        if self.bus:
            self.save_nodes(self.bus)
            self.bus.teardown()

    def save_nodes(self, container, fname=None):
        """ save the Bus, Nodes and Drivers to storage
            Parameters allow usage for controller templates, contained in "something", not a bus
        """
        if container:
            if not fname:
                fname = self.bus_storage
            with open(fname, 'wb') as p:
                pickle.dump(container, p, protocol=pickle.HIGHEST_PROTOCOL)

    def restore_nodes(self, fname=None):
        """ recreate the Bus, Nodes and Drivers from storage,
            or a controller template in a container from some file
        """
        if not fname:
            fname = self.bus_storage
        with open(fname, 'rb') as p:
            container = pickle.load(p)
        return container

    def create_default_nodes(self):
        """ "let there be light" and heating of course, what else do my fish(es) need?
            Distraction: interesting fact on English:
              "fish" is plural, "fishes" is several species of fish
        """
        single_light = True
        dawn_light = single_light and True
        single_temp = True
        dual_temp = True
        overlapped_temp = dual_temp and True

        if single_light:
            light_schedule = Schedule('Zeitplan 1', '* 14-21 * * *')
            light_schedule.plugin(self.bus)
            light_c = CtrlLight('Beleuchtung', light_schedule.id, fade_time=60) #30*60)
            light_c.plugin(self.bus)

            if not dawn_light:
                light_pwm = SinglePWM('Dimmer', light_c.id, squared=True, maximum=80)
                light_pwm.plugin(self.bus)
            else:
                dawn_schedule = Schedule('Zeitplan 2', '* 22 * * *')
                dawn_schedule.plugin(self.bus)
                dawn_c = CtrlLight('Dämmerlicht', dawn_schedule.id, fade_time=30*60)
                dawn_c.plugin(self.bus)

                light_or = Or('Licht-Oder', [light_c.id, dawn_c.id])
                light_or.plugin(self.bus)
                light_pwm = SinglePWM('Dimmer', light_or.id, squared=True, maximum=80)
                light_pwm.plugin(self.bus)

        if single_temp:
            # single temp sensor -> temp ctrl -> relais
            wasser_i = SensorTemp('Wasser', Driver('dummy', '0x1234'))
            wasser = CtrlMinimum('Temperatur', wasser_i.id, 24.3)
            wasser_o = DeviceSwitch('Heizstab', wasser.id)
            wasser.plugin(self.bus)
            wasser_o.plugin(self.bus)
            wasser_i.plugin(self.bus)

        if dual_temp:
            # 2 temp sensors -> average -> temp ctrl -> relais
            w1_temp = SensorTemp('T-Sensor 1', Driver('dummy', '28-0000x123'))
            w1_temp.plugin(self.bus)

            w2_temp = SensorTemp('T-Sensor 2', Driver('dummy', '28-0000x876'))
            w2_temp.plugin(self.bus)

            w_temp = Average('T-Mittel', [w1_temp.id, w2_temp.id])
            w_temp.plugin(self.bus)

            w1_ctrl = CtrlMinimum('W-Heizung', w_temp.id, 25.0)
            w1_ctrl.plugin(self.bus)

            w2_ctrl = CtrlMaximum('W-Kühlung', w2_temp.id, 26.5)
            w2_ctrl.plugin(self.bus)

            w_heat = DeviceSwitch('W-Heizer', w1_ctrl.id)
            w_heat.plugin(self.bus)

            w_cool = DeviceSwitch('W-Lüfter', w2_ctrl.id)
            w_cool.plugin(self.bus)


#   class MyClass:
#   @classmethod
#   def cleanOnExit(cls):
#       # do here your cleaning
#import atexit ; atexit.register(MyClass.cleanOnExit)
