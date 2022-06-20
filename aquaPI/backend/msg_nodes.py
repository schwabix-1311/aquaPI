#!/usr/bin/env python

import logging
import time
import threading
from threading import Event
import random
from flask import json

from .msg_bus import *
#import driver


log = logging.getLogger('MsgNodes')
log.setLevel(logging.WARNING) #INFO)


#DS1820 family:  /sys/bus/w1/devices/28-............/temperature(25125) ../resolution(12) ../conv_time(750)

class Driver:
    def __init__(self, cfg):
        self.cfg = cfg
        self.val = 25
        self.dir = 1

    def name(self):
        return('fake DS1820')

    def read(self):
        rnd = random.random()
        if rnd < .1:
            self.dir *= -1
        elif rnd > .7:
            self.val += 0.05 * self.dir
        self.val = round(min(max( 24, self.val), 26 ), 2)
        return self.val

    def delay(self):
        return 1.0


class Sensor(BusNode):
    ROLE = BusRole.IN_ENDP

    def __str__(self):
        return '{}({})'.format(type(self).__name__, self.driver.name())


class SensorTemp(Sensor):
    def __init__(self, name, driver):
        BusNode.__init__(self, name)
        self.driver = driver
        self.data = self.driver.read()
        threading.Thread(name=name, target=self._reader, daemon=True).start()

    def _reader(self):
        self.value = None
        while True:
            val = self.driver.read()
            if self.data != val:
                self.data = val
                self.post(MsgValue(self.name, '%.2f' % self.data))
            time.sleep(self.driver.delay())


class Auxiliary(BusListener):
    ROLE = BusRole.AUX

    def __init__(self, name, filter):
        BusListener.__init__(self, name, filter)
        self.data = None
        self.values = {}

class Average(Auxiliary):
    def __init__(self, name, filter):
        Auxiliary.__init__(self, name, filter)
        # 0 -> 1:1 average; >=2 -> moving average, active source dominates
        self.unfair_moving = 0

    def listen(self, msg):
        if isinstance(msg, MsgValue):
            if self.unfair_moving:
                if not self.data:
                    self.data = float(msg.data)
                    self.post(MsgValue(self.name, self.data))
                else:
                    val = round((self.data + float(msg.data)) / 2, self.unfair_moving)
                    if (self.data != val):
                        self.data = val
                        self.post(MsgValue(self.name, round(self.data, 2)))
            else:
                if self.values.setdefault(msg.sender) != float(msg.data):
                    self.values[msg.sender] = float(msg.data)
                val = 0
                for k in self.values:
                    val += self.values[k] / len(self.values)
                if (self.data != val):
                    self.data = val
                    self.post(MsgValue(self.name, round(self.data, 2)))
        return BusListener.listen(self, msg)


class Or(Auxiliary):
    def listen(self, msg):
        if isinstance(msg, MsgValue):
            if self.values.setdefault(msg.sender) != float(msg.data):
                self.values[msg.sender] = float(msg.data)
                log.info('Or got %g from %s', msg.data, msg.sender)
            val = -1 #0
            for k in self.values:
                val = max(val, self.values[k])
            log.info('Or max %g', val)
            if (self.data != val):
                log.info('==> Or change to %g', val)
                self.data = val
                self.post(MsgValue(self.name, round(self.data, 2)))
        return BusListener.listen(self, msg)


class Controller(BusListener):
    ROLE = BusRole.CTRL

    def is_advanced(self):
        for i in self.get_inputs():
            a_node = self.bus.get_node(i)
            if a_node and a_node.ROLE == BusRole.AUX:
                return True
        for i in self.get_outputs():
            a_node = self.bus.get_node(i)
            if a_node and a_node.ROLE == BusRole.AUX:
                return True
        return False


class CtrlMinimum(Controller):
    def __init__(self, name, filter, threshold, hysteresis=0):
        Controller.__init__(self, name, filter)
        self.threshold = threshold
        self.hysteresis = hysteresis
        self.data = 0

    def listen(self, msg):
        if isinstance(msg, MsgValue):
            val = self.data
            if float(msg.data) < self.threshold - self.hysteresis:
                val = 100
            elif float(msg.data) > self.threshold + self.hysteresis:
                val = 0
            if self.data != val:
                log.debug('Min %d -> %d', self.data, val)
                self.data = val
                self.post(MsgValue(self.name, self.data))
        return BusListener.listen(self, msg)


class Device(BusListener):
    ROLE = BusRole.OUT_ENDP


class DeviceSwitch(Device):
    def __init__(self, name, filter):
        Device.__init__(self,name, filter)
        self.data = False

    def listen(self, msg):
        if isinstance(msg, MsgValue):
            if self.data != bool(msg.data):
                self.switch(msg.data)
        return BusListener.listen(self, msg)

    def switch(self, on):
        self.data = bool(on)
        log.info('Switch %s turns %s', self.name, 'ON' if self.data else 'OFF')
        self.post(MsgValue(self.name, self.data))


class BusBroker(BusListener):
    ROLE = BusRole.BROKER
        
    def __init__(self):
        BusListener.__init__(self, 'BusBroker')
        self.values = {}
        self.changed = Event()
        self.changed.clear()

    def listen(self, msg):
        if isinstance(msg, (MsgValue,MsgBorn)):
            log.debug('broker got %s', str(msg))
            if self.values.setdefault(msg.sender) != msg.data:
                self.values[msg.sender] = msg.data
                self.changed.set()
        return BusListener.listen(self, msg)

    def get_nodes(self, roles=None):
        ''' return dict with current nodes: { name:BusNode, ... }
            filtered by set of roles, or all
        '''
        return { n.name:n  for n in self.bus.nodes if not roles or n.ROLE in roles }

    def get_node_names(self, roles=None):
        ''' return arr with current node names: [ name, ... ]
            filtered by set of roles, or all
        '''
        return [ n.name  for n in self.bus.nodes if not roles or n.ROLE in roles ]

    def values_by_names(self, names):
        return {n:self.values[n] for n in self.values if n in names}

    def values_by_role(self, roles):
        return {k:self.values[k] for k in self.values if self.bus.get_node(k).ROLE in roles}
