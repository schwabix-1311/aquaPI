#!/usr/bin/env python

import logging
import time
import threading
from threading import Event
import random

from .msg_bus import *
#import driver


log = logging.getLogger('MsgNodes')
log.setLevel(logging.INFO)


#DS1820 family:  /sys/bus/w1/devices/28-............/temperature(25125) ../resolution(12) ../conv_time(750)

class Driver:
    def __init__(self, cfg):
        self.cfg = cfg
        self.val = 25
        self.dir = 1

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


class SensorTemperature(BusMember):
    def __init__(self, name, driver):
        BusMember.__init__(self, name) #, 'sensor.temperature')
        self.role = BusRole.IN_ENDP
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


class Average(BusListener):
    def __init__(self, name, filter):
        BusListener.__init__(self, name, filter) # 'aggregate.temperature', filter)
        self.role = BusRole.AUXILIARY
        self.data = None
        self.values = {}
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


class ControlMinTemp(BusListener):
    def __init__(self, name, filter, threshold, hysteresis=0):
        BusListener.__init__(self, name, filter) # 'control.temperature', filter)
        self.role = BusRole.CONTROLLER
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
                self.data = val
                self.post(MsgValue(self.name, self.data))
        return BusListener.listen(self, msg)


class DeviceSwitch(BusListener):
    def __init__(self, name, filter):
        BusListener.__init__(self,name, filter) # 'device.switch', filter)
        self.role = BusRole.OUT_ENDP
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
    def __init__(self):
        BusListener.__init__(self, 'BusBroker') # , 'state')
        self.role = BusRole.BROKER
        #self.filter = MsgFilter([])
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

    def get_nodes(self):
        nodes = {}  # dict of node.name: [input(s)]
        #for node in self.bus.members:
        #    if node.__getattribute__('filter'):
        #        nodes[node.name] = node.filter.sender_lst
        #    else:
        #        nodes[node.name] = []
        #return nodes
        for node in self.bus.members:
            try:
                nodes[node.name] = node.filter.sender_lst
            except AttributeError:
                nodes[node.name] = []
        return nodes
        #return { n:[n.filter.sender_lst] for n in self.bus.members }

    def members_by_role(self, roles):
        return [m for m in self.bus.members if m.role in roles]

    def values_by_role(self, roles):
        return {k:self.values[k] for k in self.values if self.bus.get_member(k).role in roles}
