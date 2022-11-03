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
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


def get_unit_limits(unit):
    if unit in ('°C'):
        limits = 'min="15" max="33"'
    elif unit in ('°F'):
        limits = 'min="59" max="90"'
    elif unit in ('pH'):
        limits = 'min="6.0" max="8.0"'
    elif unit in ('%'):
        limits = 'min="0" max="100"'
    else:
        limits = ''
    return limits


# ========== inputs AKA sensors ==========


class Sensor(BusNode):
    """ Base class for IN_ENDP delivering measurments,
        e.g. temperature, pH, water level switch
    """
    ROLE = BusRole.IN_ENDP

    # def __getstate__(self):
    #    return super().__getstate__()

    # def __setstate__(self, state):
    #    self.__init__(state, _cont=True)


class SensorTemp(Sensor):
    """ A temperature sensor, actually analog input for anything read from a port driver.
        Just name and labels refer to temperatures.
        Measurements taken in a worker thread$.

        Options:
            name     - unique name of this input node in UI
            port     - name of a IoRegistry port driver to read input
            interval - delay of reader loop, reader conversion time adds to this!
            unit     - unit of measurement for labels
            avg      - floating average, with 1=no average, 2..5=depth of averaging

        Output:
            float - posts stream of measurement in driver units, unchanged measurements are suppressed
    """
    def __init__(self, name, port, interval=10.0, unit='°C', avg=0, _cont=False):
        super().__init__(name, _cont=_cont)
        self._driver = None
        self.interval = min(1., float(interval))
        self.unit = unit
        self.avg = min(max( 1, avg), 5)
        self._reader_thread = None
        self._reader_stop = False
        self._read_err = False
        self.port = port
        self.data = self._driver.read()

    def __getstate__(self):
        state = super().__getstate__()
        state.update(port=self.port)
        state.update(interval=self.interval)
        state.update(unit=self.unit)
        state.update(avg=self.avg)
        log.debug('< SensorTemp.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('SensorTemp.setstate %r', state)
        self.__init__(state['name'], state['port'], interval=state['interval'], unit=state['unit'], avg=state['avg'], _cont=True)

    def __str__(self):
        return '{}({})'.format(type(self).__name__, self.port)

    @property
    def port(self):
        return self._port

    @port.setter
    def port(self, port):
        if self._driver:
            io_registry.driver_release(self.port)
        self._driver = io_registry.driver_factory(port, PortFunc.ADC)
        self._port = port

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
                val = self.data
                if self._driver:
                    val = self._driver.read()
                    val = (val + self.data * (self.avg - 1)) / self.avg
                    val = round(val, 2)
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
        settings.append(('avg', 'Mittelwert [1=direkt]', self.avg, 'type="number" min="1" max="5" step="1"'))
        settings.append(('port', 'Sensor', self.port, 'type="text"'))
        return settings


class Schedule(BusNode):
    """ A scheduler supporting monthly/weekly/daily/hourly(/per minute)
        trigger output (On=100 / Off=0).
        Internally working like cron; a spec is 'min hour day month weekday'.
        In contrast to cron we concatenate consecutive events to a long ON state,
        i,e.  '20-24 9 * * *' outputs 100 at 9:20 and 0 at 9:24,
        while '20,24 9 * * *' results in 100 at 9:20 & 9:24, and 0 at 9:21 & 9:25.
        Highres cron is supported, where a sixth field defines seconds, and the
        internal time base ("tick") changes from 1 minute to 1 second.
        NOTE: the concatenation makes shortest time between pulses 2min or 2sec

        Options:
            name     - unique name of this input node in UI
            cronspec - a cron-style definition with 5 or 6 fields

        Output:
            posts a single 100 at start time, a single 0 at end time.
    """
    # TODO: since cron specs are not always intuitive, and require more than 1 cron line to start or end long events at an odd minute (not yet supported!), this class should get simple start/end/repeat options.

    ROLE = BusRole.IN_ENDP
    # time [s] to stop the scheduler thread, lower value raises idle load
    STOP_DURATION = 5
    # This limits CPU usage to find rare events with long gaps,
    # such as '0 4 1 1 fri' = Jan. 1st 4pm and Friday -> very rare!
    CRON_YEARS_DEPTH = 2

    def __init__(self, name, cronspec, _cont=False):
        super().__init__(name, _cont=_cont)
        self._scheduler_thread = None
        self._scheduler_stop = False
        self.cronspec = cronspec
        self.hires = len(cronspec.split(' ')) > 5
        if not _cont:
            self.data = 0
        self.unit = '%'

    def __getstate__(self):
        state = super().__getstate__()
        state.update(cronspec=self.cronspec)
        log.debug('Schedule.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('Schedule.setstate %r', state)
        self.data = state['data']
        self.__init__(state['name'], state['cronspec'], _cont=True)

    @property
    def cronspec(self):
        return self._cronspec

    @cronspec.setter
    def cronspec(self, cronspec):
        # validate it here, since the exception would be raised in our thread.
        now = datetime.now().astimezone()  # = local tz, this enables DST
        validcron = croniter(cronspec, now, day_or=False, max_years_between_matches=self.CRON_YEARS_DEPTH)

        self._stop_thread()
        self._cronspec = cronspec
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
        1 input with output(s)he required core of each controller chain.
    """
    ROLE = BusRole.CTRL

    def __init__(self, name, inputs, _cont=False):
        super().__init__(name, inputs, _cont=_cont)
        self.data = 0

    # def __getstate__(self):
    #    return super().__getstate__()

    # def __setstate__(self, state):
    #    self.__init__(state, _cont=True)

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
    """ A controller switching an output to keep a minimum input value.
        Should usually drive an output changing the input in the appropriate
        direction. Can also be used to generate warning or error states.

        Options:
            name       - unique name of this controller node in UI
            inputs     - id of a single (!) input to receive measurements from
            threshold  - the minimum measurement to maintain
            hysteresis - a tolerance, to reduce switch frequency

        Output:
            posts a single 100 when input < (threshold-hysteresis), 0 when input >= /thgreshold+hysteresis)
    """
    # TODO: some controllers could have a threshold for max. active time -> warning

    def __init__(self, name, inputs, threshold, hysteresis=0, _cont=False):
        super().__init__(name, inputs, _cont=_cont)
        self.threshold = float(threshold)
        self.hysteresis = float(hysteresis)
        self._in_data = 0

    def __getstate__(self):
        state = super().__getstate__()
        state.update(threshold=self.threshold)
        state.update(hysteresis=self.hysteresis)

        for inp in self.get_inputs(True):
            if hasattr(inp,'unit'):
                unit = inp.unit
                break
        state.update(unit=unit)

        log.debug('CtrlMinimum.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('CtrlMinimum.setstate %r', state)
        self.data = state['data']
        self.__init__(state['name'], state['inputs'], state['threshold'], hysteresis=state['hysteresis'], _cont=True)

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
        if self._in_data < (self.threshold - self.hysteresis) * 0.95:
            ret.update(alert=('LOW', 'err'))
        elif self.data:
            ret.update(alert=('*', 'act'))
        return ret

    def get_settings(self):
        for inp in self.get_inputs(True):
            if hasattr(inp,'unit'):
                unit = inp.unit
                break
        limits = get_unit_limits(unit)

        settings = super().get_settings()
        settings.append(('threshold', 'Minimum [%s]' % unit,  self.threshold, 'type="number" %s step="0.1"' % limits))
        settings.append(('hysteresis', 'Hysteresis [%s]' % unit, self.hysteresis, 'type="number" min="0" max="5" step="0.01"'))
        return settings


class CtrlMaximum(Controller):
    """ A controller switching an output to keep a maximum input value.
        Should usually drive an output changing the input in the appropriate
        direction. Can also be used to generate warning or error states.

        Options:
            name       - unique name of this controller node in UI
            inputs     - id of a single (!) input to receive measurements from
            threshold  - the maximum measurement to maintain
            hysteresis - a tolerance, to reduce switch frequency

        Output:
            posts a single 100 when input > (threshold-hysteresis), 0 when input <= /thgreshold+hysteresis)
    """
    def __init__(self, name, inputs, threshold, hysteresis=0, _cont=False):
        super().__init__(name, inputs, _cont=_cont)
        self.threshold = float(threshold)
        self.hysteresis = float(hysteresis)
        self._in_data = 0

    def __getstate__(self):
        state = super().__getstate__()
        state.update(threshold=self.threshold)
        state.update(hysteresis=self.hysteresis)

        for inp in self.get_inputs(True):
            if hasattr(inp,'unit'):
                unit = inp.unit
                break
        state.update(unit=unit)

        log.debug('CtrlMaximum.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('CtrlMaximum.setstate %r', state)
        self.data = state['data']
        self.__init__(state['name'], state['inputs'], state['threshold'], hysteresis=state['hysteresis'], _cont=True)

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
        if self._in_data > (self.threshold + self.hysteresis) * 1.05:
            ret.update(alert=('HIGH', 'err'))
        elif self.data:
            ret.update(alert=('*', 'act'))
        return ret

    def get_settings(self):
        for inp in self.get_inputs(True):
            if hasattr(inp,'unit'):
                unit = inp.unit
                break
        limits = get_unit_limits(unit)

        settings = super().get_settings()
        settings.append(('threshold', 'Maximum [%s]' % unit, self.threshold, 'type="number" %s step="0.1"' % limits))
        settings.append(('hysteresis', 'Hysteresis [%s]' % unit, self.hysteresis, 'type="number" min="0" max="5" step="0.01"'))
        return settings


class CtrlLight(Controller):
    """ A single channel light controller with fader (dust/dawn).
        When input goes to >0, a fader will post a series of
        increasing values over the period of fade_time,
        to finally reach the target level. When input goes to 0
        the same fading period is appended (!) to reach 0.

        Options:
            name       - unique name of this controller node in UI
            inputs     - id of a single (!) input to receive measurements from
            fade_time  - time span in secs to transition to the target state

        Output:
            float - posts series of percentages after input state change
    """
    # TODO: add random variation, other profiles
    # TODO: overheat reduction driven from temperature - separate nodes!

    def __init__(self, name, inputs, fade_time=None, _cont=False):
        super().__init__(name, inputs, _cont=_cont)
        self.unit = '%'
        self.fade_time = fade_time
        if fade_time and isinstance(fade_time, timedelta):
            self.fade_time = fade_time.total_seconds()
        self._fader_thread = None
        self._fader_stop = False
        if not _cont:
            self.data = 0
        self

    def __getstate__(self):
        state = super().__getstate__()
        state.update(fade_time=self.fade_time)
        state.update(unit=self.unit)
        log.debug('CtrlLight.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('CtrlLight.setstate %r', state)
        self.data = state['data']
        self.__init__(state['name'], state['inputs'], fade_time=state['fade_time'], _cont=True)

    def listen(self, msg):
        if isinstance(msg, MsgData):
            log.info('CtrlLight: got %f', msg.data)
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
        # TODO: adjust the calculation, short fade_times need longer or show steps
        INCR = 0.1 if self.fade_time >= 30 else 1.0 if self.fade_time >= 2.9 else 2.0
        if self.target != self.data:
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
        if self.data > 0 and self.data < 100:
            # ret.update(alert=('%i' % self.data, 'act'))
            ret.update(alert=('+' if self.target > self.data else '-', 'act'))
        return ret

    def get_settings(self):
        settings = super().get_settings()
        settings.append(('fade_time', 'Fade time [s]', self.fade_time, 'type="number" min="0"'))
        return settings

# ========== auxiliary ==========


class Auxiliary(BusListener):
    """ Auxiliary nodes are for advanced configurations where
        direct connections of input to controller or controller to
        output aren't sufficient.
    """
    ROLE = BusRole.AUX

    def __init__(self, name, inputs, _cont=False):
        super().__init__(name, inputs, _cont=_cont)
        self.data = -1
        self.values = {}
        self.unit = ''

    # def get_settings(self):
    #     settings = super().get_settings()
    #     settings.append((None, 'Inputs', ';'.join(MsgBus.to_names(self.get_inputs())), 'type="text"'))
    #     return settings


class Average(Auxiliary):
    """ Auxiliary node to average 2 or more inputs together.
        The average weights either each input equally (where a dead source
        may factor in an incorrect old value),
        or an "unfair moving average", where the most active input is
        over-represented. In case an input fails its effect would
        decrease quickly, thus it's a better selection for sensor redundancy.

        Options:
            name       - unique name of this auxiliar node in UI
            inputs     - collection of input ids
            unfair_avg - 0 = equally weights all inputs in output
                         >0 = moving average of a received input values

        Output:
            float - posts arithmetic average of inputs whenever average changes
    """
    def __init__(self, name, inputs, unfair_avg=0, _cont=False):
        super().__init__(name, inputs, _cont=_cont)
        # 0 -> 1:1 average; >=2 -> moving average over 2..n values, weighted by reporting frequency
        self.unfair_avg = unfair_avg

    def __getstate__(self):
        state = super().__getstate__()
        state.update(unfair_avg=self.unfair_avg)
        log.debug('Average.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('Average.setstate %r', state)
        self.__init__(state['name'], state['inputs'], unfair_avg=state['unfair_avg'], _cont=True)


    def listen(self, msg):
        if isinstance(msg, MsgData):
            if self.unfair_avg:
                if self.data == -1:
                    self.data = float(msg.data)
                    # log.brief('Average %s: output %f', self.id, self.data)
                    self.post(MsgData(self.id, self.data))
                else:
                    val = round((self.data + float(msg.data)) / 2, self.unfair_avg)
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

    def get_settings(self):
        settings = super().get_settings()
        settings.append(('unfair_avg', 'Unweighted avg.', self.unfair_avg, 'type="number" min="0" step="1"'))
        return settings


class Max(Auxiliary):
    """ Auxiliary node to post the higher of two or more inputs.
        Can be used to let two controllers drive one output, or to have
        redundant inputs.

        Options:
            name       - unique name of this auxiliary node in UI
            inputs     - collection of input ids

        Output:
            float - posts maximum of inputs whenever this changes
    """
    # def __getstate__(self):
    #     return super().__getstate__()

    # def __setstate__(self, state):
    #     self.data = state['data']
    #     self.__init__(state, _cont=True)

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
                # log.brief('Max %s: output %f', self.id, self.data)
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
    #     return super().__getstate__()

    # def __setstate__(self, state):
    #     self.data = state['data']
    #     self.__init__(state, _cont=True)


class DeviceSwitch(Device):
    """ A binary output to a GPIO pin or relais.

        Options:
            name     - unique name of this output node in UI
            inputs   - id of a single (!) input to receive data from
            port     - name of a IoRegistry port driver to drive output
            inverted - swap the boolean interpretation for active low outputs

        Output:
            drive output with bool(input), possibly inverted
    """
    def __init__(self, name, inputs, port, inverted=0, _cont=False):
        super().__init__(name, inputs, _cont=_cont)
        self._driver = None
        self.port = port
        self.inverted = int(inverted)
        self.switch(self.data if _cont else 0)
        log.info('%s init to %r|%f|%f', self.name, _cont, self.data, inverted)

    def __getstate__(self):
        state = super().__getstate__()
        state.update(port=self.port)
        state.update(inverted=self.inverted)
        return state

    def __setstate__(self, state):
        self.data = state['data']
        self.__init__(state['name'], state['inputs'], state['port'], inverted=state['inverted'], _cont=True)

    @property
    def port(self):
        return self._port

    @port.setter
    def port(self, port):
        if self._driver:
            io_registry.driver_release(self.port)
        self._driver = io_registry.driver_factory(port, PortFunc.OUT)
        self._port = port

    @property
    def inverted(self):
        return self._inverted

    @inverted.setter
    def inverted(self, inverted):
       self._inverted = inverted
       self.switch(self.data)

    def listen(self, msg):
        if isinstance(msg, MsgData):
            if self.data != bool(msg.data):
                self.switch(msg.data)
        return super().listen(msg)

    def switch(self, on):
        self.data = 100 if bool(on) else 0

        log.info('DeviceSwitch %s: turns %s', self.id, 'ON' if self.data else 'OFF')
        if not self.inverted:
            self._driver.write(self.data)
        else:
            self._driver.write(not self.data)

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
          percept - brightness correction, close to linear perception
          minimum - set minimal duty cycle for input >0, fixes flicker of
                      poorly dimming devices, and motor start
          maximum - set maximum duty cycle, allows to limit
    """
    """ An analog output using PWM (or DAC), 0..100% input range is
        mapped to the pysical minimum...maximum range of this node.

        Options:
            name     - unique name of this output node in UI
            inputs   - id of a single (!) input to receive data from
            port     - name of a IoRegistry port driver to drive output
            minimum  - minimum percentage value to avoid flicker, or reliable start (motor!)
            maximum  - upper physical percentage limit (overload, brightness, ...)
            percept  - perceptive correction using in², close to linear brightness perception

        Output:
            drive analog output with minimum...maximum, optional perceptive correction
    """
    def __init__(self, name, inputs, port, percept=False, minimum=0, maximum=100, _cont=False):
        super().__init__(name, inputs, _cont=_cont)
        self._driver = None
        self.percept = bool(percept)
        self.minimum = min(max(0, minimum), 90)
        self.maximum = min(max(minimum + 1, maximum), 100)
        if not _cont:
            self.data = 0
        self.unit = '%'
        self.port = port
        self.set_percent(self.data)
        log.info('%s init to %r | pe %r | min %f | max %f', self.name, self.data, percept, minimum, maximum)


    def __getstate__(self):
        state = super().__getstate__()
        state.update(port=self.port)
        state.update(percept=self.percept)
        state.update(minimum=self.minimum)
        state.update(maximum=self.maximum)
        log.debug('SinglePWM.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('SinglePWM.setstate %r', state)
        self.data = state['data']
        self.__init__(state['name'], state['inputs'], state['port'], percept=state['percept'], minimum=state['minimum'], maximum=state['maximum'], _cont=True)

    @property
    def port(self):
        return self._port

    @port.setter
    def port(self, port):
        if self._driver:
            io_registry.driver_release(self.port)
        self._driver = io_registry.driver_factory(port, PortFunc.PWM)
        self._port = port

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
            if self.percept:
                out_val = (out_val ** 2) / (100 ** 2) * 100
                log.debug('  percept to %f %%', out_val)
        log.debug('    finally %f %%', out_val)
        self.data = out_val

        self._driver.write(out_val)

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
        settings.append(('percept', 'Perceptive', self.percept, 'type="number" min="0" max="1"'))   # 'type="checkbox"' )
        return settings
