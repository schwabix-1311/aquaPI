#!/usr/bin/env python

import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from croniter import croniter
from threading import Thread
import random
from flask import json

from .msg_bus import *
#import driver


log = logging.getLogger('MsgNodes')
log.setLevel(logging.DEBUG) #WARNING) #INFO)


#TODO Driver does not belong here
class Driver:
    ''' a fake/development driver!
        once be get 'real':
        DS1820 family:  /sys/bus/w1/devices/28-............/temperature(25125) ../resolution(12) ../conv_time(750)
    '''
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


#========== inputs AKA sensors ==========


class Sensor(BusNode):
    ''' Base class for IN_ENDP delivering measurments,
        e.g. temperature, pH, water level switch
    '''
    ROLE = BusRole.IN_ENDP

    def __str__(self):
        return '{}({})'.format(type(self).__name__, self.driver.name())


class SensorTemp(Sensor):
    ''' A temperature sensor, utilizing a Driver class for
        different interface types.
        Measurements taken in a worker thread, looping with driver.delay()

        Output: float with temperature in °C, unchanged measurements are suppressed.
    '''
    def __init__(self, name, driver):
        super().__init__(name)
        self.driver = driver
        self.data = self.driver.read()
        self._reader_thread = None
        self._reader_stop = False

    def plugin(self, name):
        if super().plugin(name) == self.bus:
            self._reader_thread = Thread(name=self.name, target=self._reader, daemon=True).start()

    def pullout(self):
        self._reader_stop = True
        self._reader_thread.join(timeout=5)
        super().pullout()

    def _reader(self):
        self.data = None
        while not self._reader_stop:
            val = self.driver.read()
            if self.data != val:
                self.data = val
                self.post(MsgData(self.name, '%.2f' % self.data))
            time.sleep(self.driver.delay())
        self._reader_thread = None
        self._reader_stop = False


class Schedule(BusNode):
    ''' A scheduler supporting monthly/weekly/daily/hourly(/per minute)
        trigger output (On=100 / Off=0).
        Internally working like cron; a sepc is 'min hour day month weekday'.
        In contrast to cron it concatenates consecutive triggers to a longer ON phase,
        i,e.  '20-24 9 * * *' is a MsgData(100) at 9:20 and MsgData(0) at 9:24,
        while '20,24 9 * * *' sends two short On/Off pulses at 9:29 and 9:24.
        The cron spec may have a sixth field appened. This is for seconds and will
        switch the time base from minutes to seconds (hires cron)
        By concatenation the shortest time between pulses is 2min or 2sec

        Output: MsgData(100) at start time, MsgData)0) at end time.
    '''
    #TODO: since cron specs are not always intuitive, and require more than 1 cron line to start or end long events at an odd minute, this class should get simple start/end/repeat options.
    ROLE = BusRole.IN_ENDP

    def __init__(self, name, cronspec):
        super().__init__(name)
        self.cronspec = cronspec
        self.hires = len(cronspec.split(' ')) > 5
        self._scheduler_thread = None
        self._scheduler_stop = False

    def plugin(self, bus):
        if super().plugin(bus) == bus:
            self._scheduler_thread = Thread(name=self.name, target=self._scheduler, daemon=True).start()
        return self.bus

    def pullout(self):
        self._scheduler_stop = True
        self._scheduleer_thread.join(timeout=5)
        return super().pullout()

    def __str__(self):
        return '{}({})'.format(type(self).__name__, self.cronspec)

    def _scheduler(self):
        self.data = 0
        self.post(MsgData(self.name, '%.2f' % self.data))
        # get available zones: zoneinfo.available_timezones()
        now = datetime.now(ZoneInfo("Europe/Berlin"))
        cron = croniter(self.cronspec, now, ret_type=float)
        while True:
            #TODO: concatenate cron events to a long sleep and less messages
            nxt = cron.get_next() - time.time()
            if (nxt > 60) or (self.hires and nxt > 1):
                self.data = 0
                self.post(MsgData(self.name, '%.2f' % self.data))
                log.debug("turn off")
#send off
            log.debug("%d for %f s - %s" % (int(self.data), nxt, str(cron.get_current(ret_type=datetime))))
            if self._scheduler_stop:
                break
            if nxt > 0:
                time.sleep(nxt)
            if self._scheduler_stop:
                break
            if not self.data:
                self.data = 100
                self.post(MsgData(self.name, '%.2f' % self.data))
                log.debug("turn ON")
            else:
                log.debug("stay On")
        self._scheduler_thread = None
        self._scheduler_stop = False


#========== controllers ==========


class Controller(BusListener):
    ''' The base class of all controllers, i.e. BusNodes that connect
        inputs with outputs (same may be just forwarding data)
    '''
    ROLE = BusRole.CTRL

    def __init__(self, name, filter):
        super().__init__(name, filter)
        self.data = 0

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
    ''' A controller switching an output to keep a minimum
        input measuremnt by an adjustable threshold and
        an optional hysteresis, e.g. for a heater.

        Output MsgData(100) when input falls below threshold-hyst.
               MsgData(0) when input passes threshold+hyst.
    '''
    def __init__(self, name, filter, threshold, hysteresis=0):
        super().__init__(name, filter)
        self.threshold = threshold
        self.hysteresis = hysteresis

    def listen(self, msg):
        if isinstance(msg, MsgData):
            val = self.data
            if float(msg.data) < self.threshold - self.hysteresis:
                val = 100
            elif float(msg.data) > self.threshold + self.hysteresis:
                val = 0
            if self.data != val:
                log.debug('Min %d -> %d', self.data, val)
                self.data = val
                self.post(MsgData(self.name, self.data))
        return super().listen(msg)


class CtrlLight(Controller):
    ''' A single channel light controller with fader (dust/dawn).
        When input goes to 100, a fader will send a series of
        MsgData with increasing values over a period of fade_time,
        to finally reach the target level. When input goes to 0
        the same fading period is appended (!) to reach 0.

        Output: float 0 ... 100 fade-in (or hard switch) when input goes to 100
                float 100 ... 0 fade-out (or hard) after input goes to 0
    '''
    #TODO: current fader is linear, for better perception it should offer exponential curve. Could also add some random variation, other profiles, and overheat reductions driven from tmeperature ...


    def __init__(self, name, filter, fade_time=None):
        super().__init__(name, filter)
        self.fade_time = fade_time
        if fade_time and not isinstance(fade_time, timedelta):
            self.fade_time = timedelta(seconds=fade_time)
        self._fader_thread = None
        self._fader_stop = False

    def listen(self, msg):
        if isinstance(msg, MsgData):
            if self.data != float(msg.data):
                if not self.fade_time:
                    self.data = float(msg.data)
                    self.post(MsgData(self.name, self.data))
                else:
                    if self._fader_thread:
                        self._fader_stop = True
                        self._fader_thread.join()
                    self.target = float(msg.data)
                    log.debug("_fader %f" % self.target)
                    if self._fader_thread:
                        self._fader_stop = True
                        self._fader_thread.join()
                    self._fader_thread = Thread(name=self.name, target=self._fader, daemon=True).start()

    def _fader(self):
        INCR = 1.0  #0.1
        log.debug("new fader %f -> %f in %r" % (self.data, self.target, self.fade_time))
        step = (self.fade_time / abs(self.target - self.data) * INCR).total_seconds()
        log.debug("fade steps %f" % step)
        while abs(self.target - self.data) > INCR:
            if self.target >= self.data:
                self.data += INCR
            else:
                self.data -= INCR
            log.debug("_fader %f ..." % self.data)

            self.post(MsgData(self.name, round(self.data, 3)))
            time.sleep(step)
            if self._fader_stop:
                break
        if self.data != self.target:
           self.data = self.target
           self.post(MsgData(self.name, self.data))
        log.debug("_fader %f DONE" % self.target)
        self._fader_thread = None
        self._fader_stop = False


#========== auxiliary ==========


class Auxiliary(BusListener):
    ''' Auxiliary nodes are for advanced configurations where
        direct connections of input to controller or controller to
        output does not suffice.
    '''
    ROLE = BusRole.AUX

    def __init__(self, name, filter):
        super().__init__(name, filter)
        self.data = None
        self.values = {}


class Average(Auxiliary):
    ''' Auxiliary node to average 2 or more inputs together.
        The average wights either each input equally (where a dead source
        may factor in an incorrect old value),
        or an "unfair moving average", where the most active input is
        over-represented. In case of a died input it's effect would
        decrease quickly, thus is a good selection for sensor redundancy.

        Output: float arithmetic average of all sensors,
                of moving average of all delivering inputs.
    '''
    def __init__(self, name, filter):
        super().__init__(name, filter)
        # 0 -> 1:1 average; >=2 -> moving average, active source dominates
        self.unfair_moving = 0

    def listen(self, msg):
        if isinstance(msg, MsgData):
            if self.unfair_moving:
                if not self.data:
                    self.data = float(msg.data)
                    self.post(MsgData(self.name, self.data))
                else:
                    val = round((self.data + float(msg.data)) / 2, self.unfair_moving)
                    if (self.data != val):
                        self.data = val
                        self.post(MsgData(self.name, round(self.data, 2)))
            else:
                if self.values.setdefault(msg.sender) != float(msg.data):
                    self.values[msg.sender] = float(msg.data)
                val = 0
                for k in self.values:
                    val += self.values[k] / len(self.values)
                if (self.data != val):
                    self.data = val
                    self.post(MsgData(self.name, round(self.data, 2)))
        return super().listen(msg)


class Or(Auxiliary):
    ''' Auxiliary node to output the hioger of two or more inputs.
        Can be use to let two controllers drive one output, or to have
        redundant inputs.

        Output: the maximum of all listened inputs.
    '''
    def listen(self, msg):
        if isinstance(msg, MsgData):
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
                self.post(MsgData(self.name, round(self.data, 2)))
        return super().listen(msg)


#========== outputs AKA Device ==========


class Device(BusListener):
    ''' Base class for OUT_ENDP such as relais, PWM, GPIO pins.
        Receives float input from listened sender.
        The interpretation is device specific, recommendation is
        to follow pythonic truth testing to avoid surprises.
    '''
    ROLE = BusRole.OUT_ENDP


class DeviceSwitch(Device):
    ''' A binary output to a relais or GPIO pin.
    '''
#TODO: currently a logging dummy, add a driver to the actual HW.
    def __init__(self, name, filter):
        super().__init__(name, filter)
        self.data = False

    def listen(self, msg):
        if isinstance(msg, MsgData):
            if self.data != bool(msg.data):
                self.switch(msg.data)
        return super().listen(msg)

    def switch(self, on):
        self.data = bool(on)
        log.info('Switch %s turns %s', self.name, 'ON' if self.data else 'OFF')
        self.post(MsgData(self.name, self.data))   # to let MsgBroker know out state


class SinglePWM(Device):
    ''' Analog PWM output, using input data as a percentage of full range.
    '''
#TODO: currently a logging dummy, add a driver for the actual HW.
#TODO: this Node or the driver should have a minimum and a maximum level:  0,min...max (with proper scaling!)
    def listen(self, msg):
        if isinstance(msg, MsgData):
            if self.data != float(msg.data):
                self.set_percent(float(msg.data))
        return super().listen(msg)

    def set_percent(self, percent):
        self.data = percent
        log.info('PWM %s set to %s %%', self.name, self.data)
        self.post(MsgData(self.name, self.data))   # to let MsgBroker know out state)
