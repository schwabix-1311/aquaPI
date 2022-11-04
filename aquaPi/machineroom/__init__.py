#!/usr/bin/env python3

import logging
import os
from os import path
import pickle
import atexit
from .msg_bus import MsgBus
from .msg_nodes import *


log = logging.getLogger('MachineRoom')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


mr = None


def init(storage):
    global mr

    mr = MachineRoom(storage)
    return mr


# This is brute force, as a destructor AKA __del__ is not called after Ctrl-C.
# However, the concept of shutting down a web server by app code is a no-no.
# A development server might allow this, but this was removed from werkzeug with v2.1.
# Instead, I could crete a route /flush and a button (debug-only). This should
# save_nodes and bring all nodes to a safe state, e.g. heater OFF
# Seen as an appliance aquaPi should somehow allow a restart for updates, or to recover SW state

@atexit.register
def cleanup():
    log.brief('Preparing shutdown ...')
    if  mr and mr.bus:
        # this does not work completely, teardown aborts half-way.
        # Best guess: we run multi-threaded as a daemon and have only limited time until we're killed.
        mr.save_nodes(mr.bus)
        mr.bus.teardown()
        mr.bus = None


class MachineRoom:
    """ The Machine Room
        The core is a message bus, on which different sensors,
        controllers, devices and auxiliary nodes communicate.
        The Bus also provides the interface to Flask backend.
        Some bus nodes start worker threads (e.g. sensors), the rest
        works in msg handlers and callbacks.
    """
    def __init__(self, bus_storage):
        """ Create everything needed to get the machinery going.
            So far the only thing here is the bus.
        """
        self.bus_storage = bus_storage

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
        REAL_CONFIG = False
        SINGLE_LIGHT = True
        DAWN_LIGHT = SINGLE_LIGHT and False #True
        SINGLE_TEMP = True
        COMPLEX_TEMP = False #True

        if REAL_CONFIG:
            # single LED bar, dawn & dusk 15mins, perceptive corr.
            light_schedule = Schedule('Zeitplan Licht', '* 14-21 * * *')
            light_c = CtrlLight('Beleuchtung', light_schedule.id, fade_time=15*60)
            light_pwm = SinglePWM('Dimmer', light_c.id, 'PWM 0', percept=True, maximum=85)
            light_schedule.plugin(self.bus)
            light_c.plugin(self.bus)
            light_pwm.plugin(self.bus)

            # single temp sensor, switched relais
            wasser_i = SensorTemp('Wasser', 'DS1820 xA2E9C')
            wasser = CtrlMinimum('Temperatur', wasser_i.id, 25.0)
            wasser_o = DeviceSwitch('Heizstab', wasser.id, 'GPIO 12', inverted=True)
            wasser_i.plugin(self.bus)
            wasser.plugin(self.bus)
            wasser_o.plugin(self.bus)
            return

        if SINGLE_LIGHT:
            light_schedule = Schedule('Zeitplan 1', '* 14-21 * * *')
            light_schedule.plugin(self.bus)
            light_c = CtrlLight('Beleuchtung', light_schedule.id, fade_time=30*60) #30*60)
            light_c.plugin(self.bus)
            if not DAWN_LIGHT:
                light_pwm = SinglePWM('Dimmer', light_c.id, 'PWM 0', percept=True, maximum=80)
                light_pwm.plugin(self.bus)
            else:
                dawn_schedule = Schedule('Zeitplan 2', '* 22 * * *')
                dawn_schedule.plugin(self.bus)
                dawn_c = CtrlLight('Dämmerlicht', dawn_schedule.id, fade_time=30*60)
                dawn_c.plugin(self.bus)

                light_max = Max('Max Licht', [light_c.id, dawn_c.id])
                light_max.plugin(self.bus)
                light_pwm = SinglePWM('Dimmer', light_max.id, 'PWM 0', percept=True, maximum=80)
                light_pwm.plugin(self.bus)


        if SINGLE_TEMP:
            # single temp sensor -> temp ctrl -> relais
            wasser_i = SensorTemp('Wasser', 'DS1820 xA2E9C')
            #wasser_i = SensorTemp('Wasser', DriverDS1820({'address': '28-0119383a2e9c', 'fake': True, 'delay': 2 }))  # '28-01193867a71e0x1234'
            wasser = CtrlMinimum('Temperatur', wasser_i.id, 25.0)
            wasser_o = DeviceSwitch('Heizstab', wasser.id, 'GPIO 12')
            wasser.plugin(self.bus)
            wasser_o.plugin(self.bus)
            wasser_i.plugin(self.bus)

        elif COMPLEX_TEMP:
            # 2 temp sensors -> average -> temp ctrl -> relais
            w1_temp = SensorTemp('T-Sensor 1', 'DS1820 xA2E9C')
            w1_temp.plugin(self.bus)

            w2_temp = SensorTemp('T-Sensor 2', 'DS1820 x7A71E')
            w2_temp.plugin(self.bus)

            w_temp = Average('T-Mittel', [w1_temp.id, w2_temp.id])
            w_temp.plugin(self.bus)

            w1_ctrl = CtrlMinimum('W-Heizung', w_temp.id, 25.0)
            w1_ctrl.plugin(self.bus)

            w2_ctrl = CtrlMaximum('W-Kühlung', w2_temp.id, 26.5)
            w2_ctrl.plugin(self.bus)

            w_heat = DeviceSwitch('W-Heizer', w1_ctrl.id, 'GPIO 0')
            w_heat.plugin(self.bus)

            w_cool = DeviceSwitch('W-Lüfter', w2_ctrl.id, 'GPIO 1')
            w_cool.plugin(self.bus)
