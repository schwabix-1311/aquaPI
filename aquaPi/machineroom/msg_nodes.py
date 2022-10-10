#!/usr/bin/env python3

import sys
import logging
import time
from datetime import datetime, timedelta
from croniter import croniter
from threading import Thread

from .msg_bus import *
from ..driver import *


log = logging.getLogger('MsgNodes')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


# ========== inputs AKA sensors ==========


class Sensor(BusNode):
    """ Base class for IN_ENDP delivering measurments,
        e.g. temperature, pH, water level switch
    """
    ROLE = BusRole.IN_ENDP

    # def __getstate__(self):
    #    return super().__getstate__()

    # def __setstate__(self, state):
    #    self.__init__(state)


class SensorTemp(Sensor):
    """ A temperature sensor, utilizing a Driver class for
        different interface types.
        Measurements taken in a worker thread, reading at most every 'interval' secs.

        Output: float with temperature in °C, unchanged measurements are suppressed.
    """
    def __init__(self, name, driver, interval=10.0, unit='°C'):
        super().__init__(name)
        self.driver = driver
        self.unit = unit
        self.interval = min(1., float(interval))
        self.data = self.driver.read()
        self._reader_thread = None
        self._reader_stop = False
        self._read_err = False

    def __getstate__(self):
        state = super().__getstate__()
        state.update(driver=self.driver)
        state.update(interval=self.interval)
        state.update(unit=self.unit)
        log.debug('< SensorTemp.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('SensorTemp.setstate %r', state)
        self.__init__(state['name'], state['driver'], state['interval'], state['unit'])

    def __str__(self):
        return '{}({})'.format(type(self).__name__, self.driver.name)

    def plugin(self, bus):
        super().plugin(bus)
        self._reader_thread = Thread(name=self.id, target=self._reader, daemon=True)
        self._reader_thread.start()

    def pullout(self):
        if self._reader_thread:
            self._reader_stop = True
            self._reader_thread.join(timeout=5)
            self._reader_thread = None
        super().pullout()

    def _reader(self):
        log.debug('SensorTemp.reader started')
        self.data = 0  ##? None
        while not self._reader_stop:
            log.debug('SensorTemp.reader looping %r', self.data)
            try:
                val = round(self.driver.read(), 2)
                self._read_err = False
                if self.data != val:
                    self.data = val
                    log.brief('SensorTemp %s: output %f', self.id, self.data)
                    self.post(MsgData(self.id, self.data))
            except DriverReadError:
                self._read_err = True

            time.sleep(self.interval)
        self._reader_thread = None
        self._reader_stop = False

    def get_renderdata(self):
        ret = super().get_renderdata()
        ret.update(label='Messwert')
        if self._read_err:
            ret.update(alert=('Read error!', 'err'))
        return ret

    def get_settings(self):
        settings = super().get_settings()
        settings.append(('unit', 'Einheit', self.unit, 'type="text"'))
        settings.append((None, 'Sensor driver', self.driver.name, 'type="text"'))
        return settings


class Schedule(BusNode):
    """ A scheduler supporting monthly/weekly/daily/hourly(/per minute)
        trigger output (On=100 / Off=0).
        Internally working like cron; a spec is 'min hour day month weekday'.
        In contrast to cron we concatenate consecutive events to a long ON state,
        i,e.  '20-24 9 * * *' is a MsgData(100) at 9:20 and MsgData(0) at 9:24,
        while '20,24 9 * * *' sends two short On/Off pulses at 9:29 and 9:24.
        The cron spec supports a sixth field appened. This is for seconds and will
        switch the time base ("tick") from 1 minute to 1 second (hires cron).
        By concatenation the shortest time between pulses is 2min or 2sec

        Output: MsgData(100) at start time, MsgData)0) at end time.
    """
    # TODO: since cron specs are not always intuitive, and require more than 1 cron line to start or end long events at an odd minute (not yet supported!), this class should get simple start/end/repeat options.

    ROLE = BusRole.IN_ENDP
    # time [s] to stop the scheduler thread, lower value raises idle load
    STOP_DURATION = 5
    # This limits CPU usage to find rare events with long gaps,
    # such as '0 4 1 1 fri' = Jan. 1st 4pm and Friday -> very rare!
    CRON_YEARS_DEPTH = 2

    def __init__(self, name, cronspec):
        super().__init__(name)
        self._scheduler_thread = None
        self._scheduler_stop = False
        self.cronspec = cronspec
        self.hires = len(cronspec.split(' ')) > 5

    def __getstate__(self):
        state = super().__getstate__()
        state.update(cronspec=self.cronspec)
        log.debug('Schedule.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('Schedule.setstate %r', state)
        self.__init__(state['name'], state['cronspec'])

    @property
    def cronspec(self):
        return self._cronspec

    @cronspec.setter
    def cronspec(self, value):
        # validate it here, since the exception would be raised in our thread.
        now = datetime.now().astimezone()  # = local tz, this enables DST
        validcron = croniter(value, now, day_or=False, max_years_between_matches=self.CRON_YEARS_DEPTH)

        self._stop_thread()
        self._cronspec = value
        self._start_thread()

    def plugin(self, bus):
        super().plugin(bus)
        self._start_thread()

    def pullout(self):
        self._stop_thread()
        return super().pullout()

    def __str__(self):
        return '{}({})'.format(type(self).__name__, self.cronspec)

    def _start_thread(self):
        if self._bus:
            self._scheduler_thread = Thread(name=self.id, target=self._scheduler, daemon=True)
            self._scheduler_thread.start()

    def _stop_thread(self):
        if self._scheduler_thread:
            self._scheduler_stop = True
            self._scheduler_thread.join()
            self._scheduler_thread = None

    def _scheduler(self):
        log.brief('Schedule %s: start', self.id)
        self.data = 0

        now = datetime.now().astimezone()  # = local tz, this enables DST
        cron = croniter(self._cronspec, now, ret_type=float, day_or=False, max_years_between_matches=self.CRON_YEARS_DEPTH)
        tick = 1 if self.hires else 60
        log.debug(' now  %s = %f, 1 tick = %d s', now, time.time(), tick)

        try:
            cron.get_next()
            while True:
                sec_now = time.time()  # reference for each loop to avoid drift
                sec_prev = cron.get_prev()  # look one event back
                log.debug(' prev %s = %f', str(cron.get_current(ret_type=datetime)), sec_prev - sec_now)

                sec_next = cron.get_next()  # seconds 'til future cron event
                log.debug(' next %s = %f', str(cron.get_current(ret_type=datetime)), sec_next - sec_now)

                # just to be sure, croniter may need longer for sparse schedules with long pauses
                if self._scheduler_stop:
                    return  # cleanup is done in finally!

                if sec_next - sec_prev > tick:
                    # since we concatenate cron events <1 tick apart, this must be a pause
                    self.data = 0
                    log.brief('Schedule %s: output 0 for %f s', self.id, sec_next - sec_now)
                    self.post(MsgData(self.id, self.data))

                    while (sec_next > time.time()):
                        time.sleep(self.STOP_DURATION)
                        if self._scheduler_stop:
                            return  # cleanup is done in finally!

                # now look how many ticks to concatenate
                while True:
                    candidate = cron.get_next()
                    log.debug('  ? %s = + %f s', str(cron.get_current(ret_type=datetime)), candidate - sec_next)
                    if candidate - sec_next > tick:
                        log.debug('  ... busted!')
                        break
                    sec_next = candidate

                # just to be sure, croniter may need longer for sparse schedules with long pauses
                if self._scheduler_stop:
                    return  # cleanup is done in finally!

                self.data = 100
                log.brief('Schedule %s: output 100 for %f s', self.id, sec_next - sec_now)
                self.post(MsgData(self.id, self.data))

                while (sec_next > time.time()):
                    time.sleep(self.STOP_DURATION)
                    if self._scheduler_stop:
                        return  # cleanup is done in finally!
        except Exception as ex:
            # FIXME: how can such errors bubble up to the UI? Flask flash messages, but long way to there
            log.error('Failed to find next date for %s within the next %d years.', self._cronspec, self.CRON_YEARS_DEPTH)
        finally:
            # turn off? Probably not, to avoid flicker when schedule is changed
            self._scheduler_thread = None
            self._scheduler_stop = False
            log.brief('Schedule %s: end', self.id)

    def get_renderdata(self):
        ret = super().get_renderdata()
        ret.update(label='Status')
        ret.update(pretty_data='Ein' if self.data else 'Aus')
        return ret

    def get_settings(self):
        settings = super().get_settings()
        settings.append(('cronspec', 'CRON (m h DoM M DoW)', self.cronspec, 'type="text"'))
        return settings


# ========== controllers ==========


class Controller(BusListener):
    """ The base class of all controllers, i.e. BusNodes that connect
        inputs with outputs (same may be just forwarding data)
    """
    ROLE = BusRole.CTRL

    def __init__(self, name, inputs):
        super().__init__(name, inputs)
        self.data = 0

    # def __getstate__(self):
    #    return super().__getstate__()

    # def __setstate__(self, state):
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

    def get_settings(self):
        return []  # don't inherit inputs!


class CtrlMinimum(Controller):
    """ A controller switching an output to keep a minimum
        input measuremnt by an adjustable threshold and
        an optional hysteresis, e.g. for a heater.

        Output MsgData(100) when input falls below threshold-hyst.
               MsgData(0) when input passes threshold+hyst.
    """
    def __init__(self, name, inputs, threshold, hysteresis=0):
        super().__init__(name, inputs)
        self.threshold = float(threshold)
        self.hysteresis = float(hysteresis)
        self._in_data = 0

    def __getstate__(self):
        state = super().__getstate__()
        state.update(threshold=self.threshold)
        state.update(hysteresis=self.hysteresis)
        log.debug('CtrlMinimum.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('CtrlMinimum.setstate %r', state)
        self.__init__(state['name'], state['inputs'], state['threshold'], state['hysteresis'])

    def listen(self, msg):
        if isinstance(msg, MsgData):
            self._in_data = msg.data
            new_val = self.data
            if float(msg.data) < (self.threshold - self.hysteresis):
                new_val = 100.0
            elif float(msg.data) >= (self.threshold + self.hysteresis):
                new_val = 0.0

            if self.data != new_val:
                log.debug('CtrlMinimum: %d -> %d', self.data, new_val)
                self.data = new_val
                log.brief('CtrlMinimum %s: output %f', self.id, self.data)
                self.post(MsgData(self.id, self.data))
        return super().listen(msg)

    def get_renderdata(self):
        ret = super().get_renderdata()
        ret.update(pretty_data='Ein' if self.data else 'Aus')
        ret.update(label='Status')
        # TODO: see below @ CtrlMaximum
        # if self._in_data > (self.threshold + self.hysteresis) * 1.05:
        #     ret.update(alert=('HIGH', 'err'))
        if self._in_data < (self.threshold - self.hysteresis) * 0.95:
            ret.update(alert=('LOW', 'err'))
        elif self.data:
            ret.update(alert=('*', 'act'))
        return ret

    def get_settings(self):
        settings = super().get_settings()
        settings.append(('threshold', 'Minimum [°C]', self.threshold, 'type="number" min="15" max="30" step="0.1"'))
        settings.append(('hysteresis', 'Hysteresis [K]', self.hysteresis, 'type="number" min="0" max="5" step="0.01"'))
        return settings


class CtrlMaximum(Controller):
    """ A controller switching an output to keep a maximum
        input measuremnt by an adjustable threshold and
        an optional hysteresis, e.g. for a cooler, or pH

        Output MsgData(100) when input rises above threshold+hyst.
               MsgData(0) when input passes threshold-hyst.
    """
    def __init__(self, name, inputs, threshold, hysteresis=0):
        super().__init__(name, inputs)
        self.threshold = float(threshold)
        self.hysteresis = float(hysteresis)
        self._in_data = 0

    def __getstate__(self):
        state = super().__getstate__()
        state.update(threshold=self.threshold)
        state.update(hysteresis=self.hysteresis)
        log.debug('CtrlMaximum.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('CtrlMaximum.setstate %r', state)
        self.__init__(state['name'], state['inputs'], state['threshold'], state['hysteresis'])

    def listen(self, msg):
        if isinstance(msg, MsgData):
            self._in_data = msg.data
            new_val = self.data
            if float(msg.data) > (self.threshold + self.hysteresis):
                new_val = 100.0
            elif float(msg.data) <= (self.threshold - self.hysteresis):
                new_val = 0.0

            if self.data != new_val:
                self.data = new_val
                log.brief('CtrlMaximum: %d -> %d', self.data, self.data)
                self.post(MsgData(self.id, self.data))
        return super().listen(msg)

    def get_renderdata(self):
        ret = super().get_renderdata()
        ret.update(pretty_data='Ein' if self.data else 'Aus')
        ret.update(label='Status')
        if self._in_data > (self.threshold + self.hysteresis) * 1.05:
            ret.update(alert=('HIGH', 'err'))
        # TODO: instead Controller should have a threshold for max. active time -> warning
        #       as e.g. for a cooler LOW warning would be caused by its counterpart, the heating
        # elif self._in_data < (self.threshold - self.hysteresis) * 0.95:
        #     ret.update(alert=('LOW', 'err'))
        elif self.data:
            ret.update(alert=('*', 'act'))
        return ret

    def get_settings(self):
        settings = super().get_settings()
        settings.append(('threshold', 'Maximum [°C]', self.threshold, 'type="number" min="15" max="30" step="0.1"'))
        settings.append(('hysteresis', 'Hysteresis [K]', self.hysteresis, 'type="number" min="0" max="5" step="0.01"'))
        return settings


class CtrlLight(Controller):
    """ A single channel light controller with fader (dust/dawn).
        When input goes to >0, a fader will send a series of
        MsgData with increasing values over a period of fade_time,
        to finally reach the target level. When input goes to 0
        the same fading period is appended (!) to reach 0.

        Output: float 0...target  fade-in (or switch) when input goes to >0
                float target...0  fade-out (or switch) after input goes to 0
    """
    # TODO: could add random variation, other profiles, and overheat reduction driven from temperature ...

    def __init__(self, name, inputs, fade_time=None):
        super().__init__(name, inputs)
        self.unit = '%'
        self.fade_time = fade_time   # TODO: change to property, to allow immediate changes
        if fade_time and isinstance(fade_time, timedelta):
            self.fade_time = fade_time.total_seconds()
        self._fader_thread = None
        self._fader_stop = False

    def __getstate__(self):
        state = super().__getstate__()
        state.update(fade_time=self.fade_time)
        log.debug('CtrlLight.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('CtrlLight.setstate %r', state)
        self.__init__(state['name'], state['inputs'], state['fade_time'])

    def listen(self, msg):
        if isinstance(msg, MsgData):
            log.info('CtrlLight: got %f', self.data)
            if self.data != float(msg.data):
                if not self.fade_time:
                    self.data = float(msg.data)
                    log.brief('CtrlLight %s: output %f', self.id, self.data)
                    self.post(MsgData(self.id, self.data))
                else:
                    if self._fader_thread:
                        self._fader_stop = True
                        self._fader_thread.join()
                    self.target = float(msg.data)
                    log.debug("_fader %f" % self.target)
                    self._fader_thread = Thread(name=self.id, target=self._fader, daemon=True)
                    self._fader_thread.start()

    def _fader(self):
        # coarse INCR = 1.0
        INCR = 0.1
        step = (self.fade_time / abs(self.target - self.data) * INCR)
        log.brief("CtrLight %s: fading in %f s from %f -> %f, change every %f s", self.id, self.fade_time, self.data, self.target, step)
        while abs(self.target - self.data) > INCR:
            if self.target >= self.data:
                self.data += INCR
            else:
                self.data -= INCR
            log.debug("_fader %f ..." % self.data)

            self.post(MsgData(self.id, round(self.data, 3)))
            time.sleep(step)
            if self._fader_stop:
                break
        if self.data != self.target:
            self.data = self.target
            self.post(MsgData(self.id, self.data))
        log.brief("CtrlLight %s: fader DONE" % self.id)
        self._fader_thread = None
        self._fader_stop = False

    def get_renderdata(self):
        ret = super().get_renderdata()
        ret.update(pretty_data=('%.1f%s' % (self.data, self.unit)) if self.data else 'Aus')
        ret.update(label='Helligkeit')
        if self.data:
            ret.update(alert=('%i' % self.data, 'act'))
        return ret

    def get_settings(self):
        settings = super().get_settings()
        settings.append(('fade_time', 'Fade time [s]', self.fade_time, 'type="number" min="0"'))
        return settings

# ========== auxiliary ==========


class Auxiliary(BusListener):
    """ Auxiliary nodes are for advanced configurations where
        direct connections of input to controller or controller to
        output does not suffice.
    """
    ROLE = BusRole.AUX

    def __init__(self, name, inputs):
        super().__init__(name, inputs)
        self.data = -1
        self.values = {}
        self.unit = ''

    def get_settings(self):
        settings = super().get_settings()
        settings.append((None, 'Inputs', ';'.join(MsgBus.to_names(self.get_inputs())), 'type="text"'))
        return settings


class Average(Auxiliary):
    """ Auxiliary node to average 2 or more inputs together.
        The average wights either each input equally (where a dead source
        may factor in an incorrect old value),
        or an "unfair moving average", where the most active input is
        over-represented. In case an input fails its effect would
        decrease quickly, thus it's a good selection for sensor redundancy.

        Output: float arithmetic average of all sensors,
                of moving average of all delivering inputs.
    """
    def __init__(self, name, inputs):
        super().__init__(name, inputs)
        # 0 -> 1:1 average; >=2 -> moving average over 2..n values, weighted by reporting frequency
        self.unfair_moving = 0

    # def __getstate__(self):
    #    return super().__getstate__()

    # def __setstate__(self, state):
    #    self.__init__(state)

    def listen(self, msg):
        if isinstance(msg, MsgData):
            if self.unfair_moving:
                if self.data == -1:
                    self.data = float(msg.data)
                    # log.brief('Average %s: output %f', self.id, self.data)
                    self.post(MsgData(self.id, self.data))
                else:
                    val = round((self.data + float(msg.data)) / 2, self.unfair_moving)
                    if (self.data != val):
                        self.data = val
                        # log.brief('Average %s: output %f', self.id, self.data)
                        self.post(MsgData(self.id, round(self.data, 2)))
            else:
                if self.values.setdefault(msg.sender) != float(msg.data):
                    self.values[msg.sender] = float(msg.data)
                val = 0
                for k in self.values:
                    val += self.values[k] / len(self.values)
                if (self.data != val):
                    self.data = val
                    # log.brief('Average %s: output %f', self.id, self.data)
                    self.post(MsgData(self.id, round(self.data, 2)))
        return super().listen(msg)

    def get_renderdata(self):
        ret = super().get_renderdata()
        ret.update(label='Mittelwert')
        return ret


class Or(Auxiliary):
    """ Auxiliary node to output the hioger of two or more inputs.
        Can be used to let two controllers drive one output, or to have
        redundant inputs.

        Output: the maximum of all listened inputs.
    """
    # def __getstate__(self):
    #    return super().__getstate__()

    # def __setstate__(self, state):
    #    self.__init__(state)

    def listen(self, msg):
        if isinstance(msg, MsgData):
            if self.values.setdefault(msg.sender) != float(msg.data):
                self.values[msg.sender] = float(msg.data)
            val = -1  # 0
            for k in self.values:
                val = max(val, self.values[k])
            val = round(val, 2)
            if (self.data != val):
                self.data = val
                # log.brief('Or %s: output %f', self.id, self.data)
                self.post(MsgData(self.id, self.data))
        return super().listen(msg)

    def get_renderdata(self):
        ret = super().get_renderdata()
        ret.update(label='Maximum')
        return ret


# ========== outputs AKA Device ==========


class Device(BusListener):
    """ Base class for OUT_ENDP such as relais, PWM, GPIO pins.
        Receives float input from listened sender.
        The interpretation is device specific, recommendation is
        to follow pythonic truth testing to avoid surprises.
    """
    ROLE = BusRole.OUT_ENDP

    # def __getstate__(self):
    #    return super().__getstate__()

    # def __setstate__(self, state):
    #    self.__init__(state)


class DeviceSwitch(Device):
    """ A binary output to a relais or GPIO pin.
    """
    def __init__(self, name, inputs, driver, inverted=0):
        super().__init__(name, inputs)
        self.inverted = int(inverted)
        self.driver = driver
        self.data = 0

    def __getstate__(self):
        state = super().__getstate__()
        state.update(driver=self.driver)
        state.update(inverted=self.inverted)
        return state

    def __setstate__(self, state):
        self.__init__(state['name'], state['inputs'], state['driver'], state['inverted'])

    def listen(self, msg):
        if isinstance(msg, MsgData):
            if self.data != bool(msg.data):
                self.switch(msg.data)
        return super().listen(msg)

    def switch(self, on):
        self.data = bool(on)
        log.info('DeviceSwitch %s: turns %s', self.id, 'ON' if self.data else 'OFF')

        if not self.inverted:
            self.driver.write(self.data)
        else:
            self.driver.write(not self.data)

        self.post(MsgData(self.id, self.data))   # to make our state known

    def get_renderdata(self):
        ret = super().get_renderdata()
        ret.update(pretty_data='Ein' if self.data else 'Aus')
        ret.update(label='Schalter')
        return ret

    def get_settings(self):
        settings = super().get_settings()
        settings.append(('inverted', 'Inverted', self.inverted, 'type="number" min="0" max="1"'))   # FIXME   'class="uk-checkbox" type="checkbox" checked' fixes appearance, but result is always False )
        return settings


class SinglePWM(Device):
    """ Analog PWM output, using input data as a percentage of full range.
          squared - perceptive brightness correction, close to linear
                      brightness perception
          minimum - set minimal duty cycle for input >0, fixes flicker of
                      poorly dimming devices, and motor start
          maximum - set maximum duty cycle, allows to limit
    """
# TODO: currently a logging dummy, add a driver for the actual HW.
    def __init__(self, name, inputs, squared=False, minimum=0, maximum=100):
        super().__init__(name, inputs)
        self.squared = bool(squared)   # TODO: change to property, to allow immediate changes
        self.minimum = min(max(0, minimum), 90)
        self.maximum = min(max(minimum + 1, maximum), 100)
        self.data = 0
        self.unit = '%'
        log.info('%s init to %r|%f|%f', self.name, squared, minimum, maximum)

    def __getstate__(self):
        state = super().__getstate__()
        state.update(squared=self.squared)
        state.update(minimum=self.minimum)
        state.update(maximum=self.maximum)
        log.debug('SinglePWM.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('SinglePWM.setstate %r', state)
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

        self.post(MsgData(self.id, round(out_val, 4)))   # to make our state known

    def get_renderdata(self):
        ret = super().get_renderdata()
        ret.update(pretty_data=('%.2f%s' % (self.data, self.unit)) if self.data else 'Aus')
        ret.update(label='Helligkeit')
        return ret

    def get_settings(self):
        settings = super().get_settings()
        settings.append(('minimum', 'Minimum [%]', self.minimum, 'type="number" min="0" max="99"'))
        settings.append(('maximum', 'Maximum [%]', self.maximum, 'type="number" min="1" max="100"'))
        settings.append(('squared', 'Perceptive', self.squared, 'type="number" min="0" max="1"'))   # 'type="checkbox"' )
        return settings
