#!/usr/bin/env python

import sys
import logging
import time
from datetime import datetime, timedelta
if sys.version_info >= (3,9):
    from zoneinfo import ZoneInfo
else:
    from backports.zoneinfo import ZoneInfo
from croniter import croniter
from threading import Thread
import random
from flask import json

from .msg_bus import *
#import driver


log = logging.getLogger('MsgNodes')
log.setLevel(logging.WARNING) #INFO)
#log.setLevel(logging.DEBUG)


#TODO Driver does not belong here
class Driver:
    ''' a fake/development driver!
        once we get 'real':
        DS1820 family:  /sys/bus/w1/devices/28-............/temperature(25125) ../resolution(12) ../conv_time(750)
    '''
    def __init__(self, name, cfg):
        self.name = 'fake DS1820'  # name
        self.cfg = cfg
        self.val = 24.25
        self.dir = 1

    def __getstate__(self):
        state = {'name':self.name, 'cfg':self.cfg}
        log.debug('Driver.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.warning('Driver.setstate %r', state)
        self.__init__(state['name'], state['cfg'])

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

    #def __getstate__(self):
    #    return super().__getstate__()

    #def __setstate__(self, state):
    #    self.__init__(state)


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

    def __getstate__(self):
        state = super().__getstate__()
        state.update(driver=self.driver)
        log.debug('< SensorTemp.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.warning('SensorTemp.setstate %r', state)
        self.__init__(state['name'], state['driver'])

    def __str__(self):
        return '{}({})'.format(type(self).__name__, self.driver.name)

    def plugin(self, bus):
        if super().plugin(bus):
            self._reader_thread = Thread(name=self.name, target=self._reader, daemon=True)
            self._reader_thread.start()
        return bool(self._bus != None)

    def pullout(self):
        if self._reader_thread:
            self._reader_stop = True
            self._reader_thread.join(timeout=5)
            self._reader_thread = None
        super().pullout()

    def _reader(self):
        #log.debug('SensorTemp.reader started')
        self.data = None
        while not self._reader_stop:
            #log.debug('SensorTemp.reader looping %r', self.data)
            val = self.driver.read()
            if self.data != val:
                self.data = val
                self.post(MsgData(self.name, round(self.data, 2)))
            time.sleep(self.driver.delay())
        self._reader_thread = None
        self._reader_stop = False

    def get_dash(self):
        return { 'Temperature [°C]': round(self.data, 2) }

    def get_settings(self):
        return { 'Sensor driver': self.driver.name }


class Schedule(BusNode):
    ''' A scheduler supporting monthly/weekly/daily/hourly(/per minute)
        trigger output (On=100 / Off=0).
        Internally working like cron; a spec is 'min hour day month weekday'.
        In contrast to cron we concatenate consecutive events to a long ON state,
        i,e.  '20-24 9 * * *' is a MsgData(100) at 9:20 and MsgData(0) at 9:24,
        while '20,24 9 * * *' sends two short On/Off pulses at 9:29 and 9:24.
        The cron spec supports a sixth field appened. This is for seconds and will
        switch the time base ("tick") from 1 minute to 1 second (hires cron).
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

    def __getstate__(self):
        state = super().__getstate__()
        state.update(cronspec=self.cronspec)
        log.debug('Schedule.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.warning('Schedule.setstate %r', state)
        self.__init__(state['name'], state['cronspec'])

    def plugin(self, bus):
        if super().plugin(bus):
            self._scheduler_thread = Thread(name=self.name, target=self._scheduler, daemon=True)
            self._scheduler_thread.start()
        return bool(self._bus != None)

    def pullout(self):
        if self._scheduler_thread:
            self._scheduler_stop = True
            self._scheduler_thread.join(timeout=5)
            self._scheduler_thread = None
        return super().pullout()

    def __str__(self):
        return '{}({})'.format(type(self).__name__, self.cronspec)

    def _scheduler(self):
        self.data = 0
        self.post(MsgData(self.name, self.data))
        now = datetime.now().astimezone()  # = local tz

        cron = croniter(self.cronspec, now, ret_type=float)
        tick = 1 if self.hires else 60

        while True:
            # for 1st loop iteration find seconds since preciding cron event ...
            cron.get_next()
            pre = cron.get_prev() - time.time()
            log.debug(' backwd %f =  %s', pre, str(cron.get_current(ret_type=datetime)))

            # ... if more than 1 tick in the past, start with OFF, else start with ON
            # Following iterations pre will be >1 tick in past, otherwise it would
            # have been concatenated with current.
            if pre < -tick:
                nxt = cron.get_next() - time.time()
                log.warning("%s: stay off for %f s (%f h)", self.name, nxt, nxt /60/60)
                self.data = 0
                self.post(MsgData(self.name, self.data))
#send off
                log.debug("%d for %f s - %s" % (int(self.data), nxt, str(cron.get_current(ret_type=datetime))))
                if nxt > 0:
                    if self._scheduler_stop:
                        break
                    time.sleep(nxt)
                if self._scheduler_stop:
                    break

            nxt = cron.get_next()
            log.debug('next is  %s', str(cron.get_current(ret_type=datetime)))
            while True:
                # concatenate cron events that occur every tick
                n_nxt = cron.get_next()
                log.debug(' ?  %s', str(cron.get_current(ret_type=datetime)))
                if n_nxt - nxt > tick:
                    break
                nxt = n_nxt
                log.debug(' + extended to %s', str(cron.get_current(ret_type=datetime)))
            cron.get_prev()

            nxt = nxt - time.time()
            log.warning("%s: stay ON for %f s (%f h)", self.name, nxt, nxt /60/60)
            self.data = 100
            self.post(MsgData(self.name, self.data))
            log.debug("%d for %f s - %s", int(self.data), nxt, str(cron.get_current(ret_type=datetime)))
            if nxt > 0:
                if self._scheduler_stop:
                    break
                time.sleep(nxt)
            if self._scheduler_stop:
                break

        self._scheduler_thread = None
        self._scheduler_stop = False

    def get_dash(self):
        if self.hires:
            return { 'CRON [m h DoM M DoW s]': self.cronspec }
        return { 'CRON [m h DoM M DoW]': self.cronspec }

    def get_settings(self):
        field = self.cronspec.split()
        return { 'CRON minute [*/digit/range/list]': field[0] \
               , 'CRON hour ["]': field[1] \
               , 'CRON day of month ["]': field[2] \
               , 'CRON month ["]': field[3] \
               , 'CRON weekday [0=Sun]': field[4]
               # could allow hires:
               #, 'CRON second [opt]': field[5] if len(field)>5 else ''
               }


#========== controllers ==========


class Controller(BusListener):
    ''' The base class of all controllers, i.e. BusNodes that connect
        inputs with outputs (same may be just forwarding data)
    '''
    ROLE = BusRole.CTRL

    def __init__(self, name, inputs):
        super().__init__(name, inputs)
        self.data = 0

    #def __getstate__(self):
    #    return super().__getstate__()

    #def __setstate__(self, state):
    #    self.__init__(state)

    def is_advanced(self):
        for i in self.get_inputs():
            a_node = self._bus.get_node(i)
            if a_node and a_node.ROLE == BusRole.AUX:
                return True
        for i in self.get_outputs():
            a_node = self._bus.get_node(i)
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
    def __init__(self, name, inputs, threshold, hysteresis=0):
        super().__init__(name, inputs)
        self.threshold = threshold
        self.hysteresis = hysteresis
        self._in_val = None

    def __getstate__(self):
        state = super().__getstate__()
        state.update(threshold=self.threshold, hysteresis=self.hysteresis)
        log.debug('CtrlMinimum.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.warning('CtrlMinimum.setstate %r', state)
        self.__init__(state['name'], state['inputs'], state['threshold'], state['hysteresis'])

    def listen(self, msg):
        if isinstance(msg, MsgData):
            self._in_val = float(msg.data)
            val = self.data
            if float(msg.data) < self.threshold - self.hysteresis:
                val = 100
            elif float(msg.data) >= self.threshold + self.hysteresis:
                val = 0
            if self.data != val:
                log.debug('CtrlMinimum: %d -> %d', self.data, val)
                self.data = val
                self.post(MsgData(self.name, self.data))
        return super().listen(msg)

    def get_dash(self):
        return { 'State': 'ON' if self.data else 'OFF' }

    def get_settings(self):
        return { 'Minimum [°C]': self.threshold \
               , 'Hysteresis [K]': self.hysteresis  }


class CtrlMaximum(Controller):
    ''' A controller switching an output to keep a maximum
        input measuremnt by an adjustable threshold and
        an optional hysteresis, e.g. for a cooler, or pH

        Output MsgData(100) when input rises above threshold+hyst.
               MsgData(0) when input passes threshold-hyst.
    '''
    def __init__(self, name, inputs, threshold, hysteresis=0):
        super().__init__(name, inputs)
        self.threshold = threshold
        self.hysteresis = hysteresis
        self._in_val = None

    def __getstate__(self):
        state = super().__getstate__()
        state.update(threshold=self.threshold, hysteresis=self.hysteresis)
        log.debug('CtrlMaximum.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.warning('CtrlMaximum.setstate %r', state)
        self.__init__(state['name'], state['inputs'], state['threshold'], state['hysteresis'])

    def listen(self, msg):
        if isinstance(msg, MsgData):
            self._in_val = float(msg.data)
            val = self.data
            if float(msg.data) > self.threshold + self.hysteresis:
                val = 100
            elif float(msg.data) <= self.threshold - self.hysteresis:
                val = 0
            if self.data != val:
                log.debug('CtrlMinimum: %d -> %d', self.data, val)
                self.data = val
                self.post(MsgData(self.name, self.data))
        return super().listen(msg)

    def get_dash(self):
        return { 'State': 'ON' if self.data else 'OFF' }

    def get_settings(self):
        return { 'Maximum [°C]': self.threshold \
               , 'Hysteresis [K]': self.hysteresis  }


class CtrlLight(Controller):
    ''' A single channel light controller with fader (dust/dawn).
        When input goes to >0, a fader will send a series of
        MsgData with increasing values over a period of fade_time,
        to finally reach the target level. When input goes to 0
        the same fading period is appended (!) to reach 0.

        Output: float 0...target  fade-in (or switch) when input goes to >0
                float target...0  fade-out (or switch) after input goes to 0
    '''
    #TODO: could add random variation, other profiles, and overheat reductions driven from tmeperature ...


    def __init__(self, name, inputs, fade_time=None):
        super().__init__(name, inputs)
        self.fade_time = fade_time
        if fade_time and not isinstance(fade_time, timedelta):
            self.fade_time = timedelta(seconds=fade_time)
        self._fader_thread = None
        self._fader_stop = False

    def __getstate__(self):
        state = super().__getstate__()
        state.update(fade_time=self.fade_time)
        log.debug('CtrlLight.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.warning('CtrlLight.setstate %r', state)
        self.__init__(state['name'], state['inputs'], state['fade_time'])

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
                    self._fader_thread = Thread(name=self.name, target=self._fader, daemon=True)
                    self._fader_thread.start()

    def _fader(self):
        #coarse INCR = 1.0
        INCR = 0.1
        step = (self.fade_time / abs(self.target - self.data) * INCR).total_seconds()
        log.info("%s: fading in %f s from %f -> %f, change every %f s", self.name, self.fade_time.total_seconds(), self.data, self.target, step)
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

    def get_dash(self):
        return { 'State': 'ON' if self.data else 'OFF' \
               , 'Dim [%]': round(self.data, 2) }

    def get_settings(self):
        return { 'Fade time [s]': self.fade_time.total_seconds() }

#========== auxiliary ==========


class Auxiliary(BusListener):
    ''' Auxiliary nodes are for advanced configurations where
        direct connections of input to controller or controller to
        output does not suffice.
    '''
    ROLE = BusRole.AUX

    def __init__(self, name, inputs):
        super().__init__(name, inputs)
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
    def __init__(self, name, inputs):
        super().__init__(name, inputs)
        # 0 -> 1:1 average; >=2 -> moving average, active source dominates
        self.unfair_moving = 0

    #def __getstate__(self):
    #    return super().__getstate__()

    #def __setstate__(self, state):
    #    self.__init__(state)

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

    def get_settings(self):
        return { 'Input name(s)': ';'.join(self.get_inputs()) }


class Or(Auxiliary):
    ''' Auxiliary node to output the hioger of two or more inputs.
        Can be use to let two controllers drive one output, or to have
        redundant inputs.

        Output: the maximum of all listened inputs.
    '''
    #def __getstate__(self):
    #    return super().__getstate__()

    #def __setstate__(self, state):
    #    self.__init__(state)

    def listen(self, msg):
        if isinstance(msg, MsgData):
            if self.values.setdefault(msg.sender) != float(msg.data):
                self.values[msg.sender] = float(msg.data)
            val = -1 #0
            for k in self.values:
                val = max(val, self.values[k])
            if (self.data != val):
                self.data = val
                self.post(MsgData(self.name, round(self.data, 2)))
        return super().listen(msg)

    def get_settings(self):
        return { 'Input name(s)': ';'.join(self.get_inputs()) }


#========== outputs AKA Device ==========


class Device(BusListener):
    ''' Base class for OUT_ENDP such as relais, PWM, GPIO pins.
        Receives float input from listened sender.
        The interpretation is device specific, recommendation is
        to follow pythonic truth testing to avoid surprises.
    '''
    ROLE = BusRole.OUT_ENDP

    #def __getstate__(self):
    #    return super().__getstate__()

    #def __setstate__(self, state):
    #    self.__init__(state)



class DeviceSwitch(Device):
    ''' A binary output to a relais or GPIO pin.
    '''
#TODO: currently a logging dummy, add a driver to the actual HW.
    def __init__(self, name, inputs, inverted=False):
        super().__init__(name, inputs)
        self.data = False
        self.inverted = inverted

    #def __getstate__(self):
    #    return super().__getstate__()

    #def __setstate__(self, state):
    #    self.__init__(state)

    def listen(self, msg):
        if isinstance(msg, MsgData):
            if self.data != bool(msg.data):
                self.switch(msg.data)
        return super().listen(msg)

    def switch(self, on):
        self.data = bool(on)
        log.info('%s turns %s', self.name, 'ON' if self.data else 'OFF')

        # actual driver call would go here
        # if self.inverted ....

        self.post(MsgData(self.name, self.data))   # to make our state known

    def get_dash(self):
        return { 'State': 'ON' if self.data else 'OFF' }

    def get_settings(self):
        return { 'Inverted': self.inverted }


class SinglePWM(Device):
    ''' Analog PWM output, using input data as a percentage of full range.
          squared - perceptive brightness correction, close to linear
                      brightness perception
          minimum - set minimal duty cycle for input >0, fixes flicker of
                      poorly dimming devices, and motor start
          maximum - set maximum duty cycle, allows to limit
    '''
#TODO: currently a logging dummy, add a driver for the actual HW.
    def __init__(self, name, inputs, squared, minimum=0, maximum=100):
        super().__init__(name, inputs)
        self.squared = squared
        self.minimum = min(max( 0, minimum), 90)
        self.maximum = min(max( minimum + 1, maximum), 100)
        self.data = 0
        log.info('%s init to %r|%f|%f', self.name, squared,minimum,maximum)

    def __getstate__(self):
        state = super().__getstate__()
        state.update(squared=self.squared, minimum=self.minimum, maximum=self.maximum)
        log.debug('SinglePWM.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.warning('SinglePWM.setstate %r', state)
        self.__init__(state['name'], state['inputs'], state['squared'], state['minimum'], state['maximum'])

    def listen(self, msg):
        if isinstance(msg, MsgData):
            if self.data != float(msg.data):
                self.set_percent(float(msg.data))
        return super().listen(msg)

    def set_percent(self, percent):
        out_val = float(percent)
        log.debug('%s set to %f %%', self.name, round(out_val, 4))
        if out_val > 0:
            out_range = self.maximum - self.minimum
            out_val = out_val / 100 * out_range
            log.debug('  scale to %f %% [%f]', out_val, out_range)
            out_val += self.minimum
            if self.squared:
                out_val = (out_val ** 2) / (100 ** 2) * 100
                log.debug('  squared to %f %%', out_val)
        log.debug('    finally %f %%', out_val)
        self.data = out_val

        # actual driver call would go here

        self.post(MsgData(self.name, round(out_val, 4)))   # to make our state known

    def get_dash(self):
        return { 'Percent': round(self.data, 2) }

    def get_settings(self):
        return { 'Minimum [%]': self.minimum \
               , 'Maximum [%]': self.maximum \
               , 'Perceptive': self.squared }
