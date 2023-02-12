#!/usr/bin/env python3

import logging
import time
import math
import random
from datetime import timedelta
from threading import Thread

from .msg_bus import (BusListener, BusRole, DataRange, MsgData)


log = logging.getLogger('CtrlNodes')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


def get_unit_limits(unit):
    if unit in ('°C'):
        limits = 'min="15" max="33" step="0.1"'
    elif unit in ('°F'):
        limits = 'min="59" max="90" step="0.2"'
    elif unit in ('pH'):
        limits = 'min="6.0" max="8.0" step="0.05"'
        limits = 'min="2.0" max="8.0" step="0.01"'
    elif unit in ('%'):
        limits = 'min="0" max="100" step="1"'
    else:
        limits = ''
    return limits


# ========== controllers ==========


class ControllerNode(BusListener):
    """ The base class of all controllers, i.e. nodes that connect
        1 input to output(s).
        The required core of each controller chain.
    """
    ROLE = BusRole.CTRL

    def __init__(self, name, inputs, _cont=False):
        super().__init__(name, inputs, _cont=_cont)
        self.data = 0

    # def __getstate__(self):
    #    return super().__getstate__()

    # def __setstate__(self, state):
    #    self.__init__(state, _cont=True)

    def find_source_unit(self):
        for inp in self.get_inputs(True):
            self.unit = inp.unit
            break
        return self.unit

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


class MinimumCtrl(ControllerNode):
    """ A controller switching an output to keep a minimum input value.
        Should usually drive an output changing the input in the appropriate
        direction. Can also be used to generate warning or error states.

        Options:
            name       - unique name of this controller node in UI
            inputs     - id of a single (!) input to receive measurements from
            threshold  - the minimum measurement to maintain
            hysteresis - a tolerance, to reduce switch frequency

        Output:
            posts a single
              100 when input < (thr. - hyst./2),
              0 when input >= (thr. + hyst./2)
    """
    data_range = DataRange.BINARY

    # TODO: some controllers could have a threshold for max. active time -> warning

    def __init__(self, name, inputs, threshold, hysteresis=0, _cont=False):
        super().__init__(name, inputs, _cont=_cont)
        self.threshold = float(threshold)
        self.hysteresis = float(hysteresis)

    def __getstate__(self):
        state = super().__getstate__()
        state.update(threshold=self.threshold)
        state.update(hysteresis=self.hysteresis)
        state.update(unit=self.find_source_unit())

        log.debug('MinimumCtrl.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('MinimumCtrl.setstate %r', state)
        self.data = state['data']
        self.__init__(state['name'], state['inputs'], state['threshold'], hysteresis=state['hysteresis'], _cont=True)

    def listen(self, msg):
        if isinstance(msg, MsgData):
            new_val = self.data
            if float(msg.data) < (self.threshold - self.hysteresis / 2):
                new_val = 100.0
            elif float(msg.data) >= (self.threshold + self.hysteresis / 2):
                new_val = 0.0

            if (self.data != new_val) or True:  # WAR a startup problem
                log.debug('MinimumCtrl: %d -> %d', self.data, new_val)
                self.data = new_val

                if msg.data < (self.threshold - self.hysteresis / 2) * 0.95:
                    self.alert = ('LOW', 'err')
                    log.brief('MinimumCtrl %s: output %f - alert %r', self.id, self.data, self.alert)
                else:
                    self.alert = ('*', 'act')  if self.data else None
                    log.brief('MinimumCtrl %s: output %f', self.id, self.data)

                self.post(MsgData(self.id, self.data))  # only on data change? or 1 level outdented?
        return super().listen(msg)

    def get_settings(self):
        limits = get_unit_limits(self.find_source_unit())

        settings = super().get_settings()
        settings.append(
            ('threshold', 'Minimum [%s]' % self.unit, self.threshold, 'type="number" %s' % limits))
        settings.append(
            ('hysteresis', 'Hysteresis [%s]' % self.unit, self.hysteresis, 'type="number" min="0" max="5" step="0.01"'))
        return settings


class MaximumCtrl(ControllerNode):
    """ A controller switching an output to keep a maximum input value.
        Should usually drive an output changing the input in the appropriate
        direction. Can also be used to generate warning or error states.

        Options:
            name       - unique name of this controller node in UI
            inputs     - id of a single (!) input to receive measurements from
            threshold  - the maximum measurement to maintain
            hysteresis - a tolerance, to reduce switch frequency

        Output:
            posts a single
              100 when input > (thr. - hyst./2),
              0 when input <= (thr. + hyst./2)
    """
    data_range = DataRange.BINARY

    def __init__(self, name, inputs, threshold, hysteresis=0, _cont=False):
        super().__init__(name, inputs, _cont=_cont)
        self.threshold = float(threshold)
        self.hysteresis = float(hysteresis)

    def __getstate__(self):
        state = super().__getstate__()
        state.update(threshold=self.threshold)
        state.update(hysteresis=self.hysteresis)
        state.update(unit=self.find_source_unit())

        log.debug('MaximumCtrl.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('MaximumCtrl.setstate %r', state)
        self.data = state['data']
        self.__init__(state['name'], state['inputs'], state['threshold'], hysteresis=state['hysteresis'], _cont=True)

    def listen(self, msg):
        if isinstance(msg, MsgData):
            new_val = self.data
            if float(msg.data) > (self.threshold + self.hysteresis / 2):
                new_val = 100.0
            elif float(msg.data) <= (self.threshold - self.hysteresis / 2):
                new_val = 0.0

            if (self.data != new_val) or True:  # WAR a startup problem
                log.debug('MaximumCtrl: %d -> %d', self.data, new_val)
                self.data = new_val

                if msg.data > (self.threshold + self.hysteresis / 2) * 1.05:
                    self.alert = ('HIGH', 'err')
                    log.brief('MaximumCtrl %s: output %f - alert %r', self.id, self.data, self.alert)
                else:
                    self.alert = ('*', 'act')  if self.data else None
                    log.brief('MaximumCtrl %s: output %f', self.id, self.data)

                self.post(MsgData(self.id, self.data))  # only on data change? or 1 level outdented?
        return super().listen(msg)

    def get_settings(self):
        limits = get_unit_limits(self.find_source_unit())

        settings = super().get_settings()
        settings.append(
            ('threshold', 'Maximum [%s]' % self.unit, self.threshold, 'type="number" %s' % limits))
        settings.append(
            ('hysteresis', 'Hysteresis [%s]' % self.unit, self.hysteresis, 'type="number" min="0" max="5" step="0.01"'))
        return settings


class FadeCtrl(ControllerNode):
    """ A single channel linear fading controller, usable for light (dusk/dawn).
        A change of input value will start a ramp from current to new
        percentage. The duration of this ramp is deltaPerc / 100 * fade_time.
        Durations for fade-in and fade-out can be different and may be 0 for
        hard switches.
        The ramp steps by 0.1%, or more to keep step duration >= 100 ms.

        Options:
            name       - unique name of this controller node in UI
            inputs     - id of a single (!) input to receive measurements from
            fade_time  - time span in secs to transition to the target state
            fade_out   - optional time, defaults to fade_time

        Output:
            float - posts series of percentages after input state change
    """
    data_range = DataRange.PERCENT

    # TODO: add random variation, other profiles
    # TODO: overheat reduction driven from temperature - separate nodes!

    def __init__(self, name, inputs, fade_time=None, fade_out=None, _cont=False):
        super().__init__(name, inputs, _cont=_cont)
        self.unit = '%'
        self.fade_time = fade_time
        if fade_time and isinstance(fade_time, timedelta):
            self.fade_time = fade_time.total_seconds()
        self.fade_out = fade_out if fade_out else fade_time
        if fade_out and isinstance(fade_out, timedelta):
            self.fade_out = fade_out.total_seconds()
        self._fader_thread = None
        self._fader_stop = False
        if not _cont:
            self.data = 0
        self.target = self.data

    def __getstate__(self):
        state = super().__getstate__()
        state.update(fade_time=self.fade_time)
        state.update(fade_out=self.fade_out)
        log.debug('FadeCtrl.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('FadeCtrl.setstate %r', state)
        self.data = state['data']
        self.__init__(state['name'], state['inputs'], fade_time=state['fade_time'], fade_out=state['fade_out'], _cont=True)

    def listen(self, msg):
        if isinstance(msg, MsgData):
            log.info('FadeCtrl: got %f', msg.data)
            self.target = float(msg.data)
            if self.data != self.target:
                # our fade direction want's a hard switch
                if (self.data < self.target and not self.fade_time) \
                or (self.data > self.target and not self.fade_out):
                    self.data = self.target
                    log.brief('FadeCtrl %s: output %f', self.id, self.data)
                    self.post(MsgData(self.id, self.data))
                else:
                    if self._fader_thread:
                        self._fader_stop = True
                        self._fader_thread.join()
                    log.debug('_fader %f -> %f', self.data, self.target)
                    self._fader_thread = Thread(name=self.id, target=self._fader, daemon=True)
                    self._fader_thread.start()

    def _fader(self):
        """ This fader uses constant steps of 0.1% unless this would be >10 steps/sec
        """
        if self.target != self.data:
            f_time = self.fade_time  if self.data < self.target else self.fade_out
            delta_d = self.target - self.data      # total change
            delta_t = abs(delta_d) / 100 * f_time  # total time for this change
            step_t = max(delta_t / 1000, 0.1)      # try 1000 steps, at most 10 steps per sec
            step_d = delta_d * step_t / delta_t
            log.brief('FadeCtrl %s: fading in %f s from %f -> %f, change by %f every %f s'
                     , self.id, delta_t, self.data, self.target, step_d, step_t)

            next_t = time.time() + step_t
            while abs(self.target - self.data) > abs(step_d):
                self.data += step_d
                log.debug('_fader %f ...', self.data)

                self.alert = ('\u2197' if self.target > self.data else '\u2198', 'act')
                self.post(MsgData(self.id, round(self.data, 3)))
                time.sleep(next_t - time.time())
                next_t += step_t
                if self._fader_stop:
                    log.brief('FadeCtrl %s: fader stopped', self.id)
                    break
            else:
                if self.data != self.target:
                    self.data = self.target
                    self.post(MsgData(self.id, self.data))
                self.alert = None
                log.brief('FadeCtrl %s: fader DONE', self.id)
        self._fader_thread = None
        self._fader_stop = False

    def get_settings(self):
        settings = super().get_settings()
        settings.append(('fade_time', 'Fade-In time [s]', self.fade_time, 'type="number" min="0"'))
        settings.append(('fade_out', 'Fade-Out time [s]', self.fade_out, 'type="number" min="0"'))
        return settings


class SunCtrl(ControllerNode):
    """ A single channel light controller, simulating ascend/descend
        aproximated by a sine wave (xscend) and a streched maximium
        value (highnoon).
        Any input of non-0 starts a new cycle; an ongoing
        cycle is aborted. Input of 0 has never an effect.
        The ramp steps by 0.1%, or more to keep step duration >= 100 ms.
        The input value - usually 100 - is used daylight percentage..

        Options:
            name     - unique name of this controller node in UI
            inputs   - id of a single (!) input to receive measurements from
            highnoon - (unrealistic) duration of const high noon
            xscend   - duration of each of ascend and descend

        Output:
            float - posts series of percentages after input state change
    """
    data_range = DataRange.PERCENT

    def __init__(self, name, inputs, highnoon=4, xscend=2, _cont=False):
        super().__init__(name, inputs, _cont=_cont)
        self.unit = '%'
        self.highnoon = highnoon
        if highnoon and isinstance(highnoon, timedelta):
            self.highnoon = highnoon.total_seconds() / 60 / 60
        self.xscend = xscend
        if xscend and isinstance(xscend, timedelta):
            self.xscend = xscend.total_seconds() / 60 / 60
        self._fader_thread = None
        self._fader_stop = False
        if not _cont:
            self.data = 0
        self.target = self.data
        self.clouds = []

    def __getstate__(self):
        state = super().__getstate__()
        state.update(highnoon=self.highnoon)
        state.update(xscend=self.xscend)
        log.debug('SunCtrl.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('SunCtrl.setstate %r', state)
        self.data = state['data']
        self.__init__(state['name'], state['inputs'], highnoon=state['highnoon'], xscend=state['xscend'], _cont=True)

    def listen(self, msg):
        if isinstance(msg, MsgData):
            log.info('SunCtrl: got %f', msg.data)
            if msg.data:
                self.target = float(msg.data)
                if self._fader_thread:
                    log.brief('SunCtrl %s: abort current cycle', self.id)
                    self._fader_stop = True
                    self._fader_thread.join()
                log.debug('_fader %f', self.target)
                self._fader_thread = Thread(name=self.id, target=self._fader, daemon=True)
                self._fader_thread.start()

    @staticmethod
    def _halfsine(elapsed_t, wave_t, max_p):
        """ calculate value of a sine half-wave of amplitude max_p
            and duration wave_t at position elapsed_t
        """
        t = elapsed_t / wave_t * math.pi
        return math.sin(t) * max_p

    def _calculate_clouds(self, cloudiness):
        now = time.time()
        if random.random() < 0.01 and len(self.clouds) < cloudiness:
            # generate a cloud = (start, duration, darkness)
            cl = (now, int(random.random() * self.highnoon *60*60 / 2), int(random.random() * 10) + 2)
            self.clouds.append(cl)
            log.brief('SunCtrl %s: new cloud (%d | %d)', self.id, cl[1], cl[2])

        i = 0
        shadow = 0
        for cl in self.clouds.copy():
            self.alert = ('\u219d', 'act')  # rightwards wave arrow

            if cl[0] + cl[1] < now:
                self.clouds.remove(cl)
            else:
                # factor in a cloud = (start, duration, darkness)
                sh = self._halfsine(now - cl[0], cl[1], cl[2])
                log.debug('SunCtrl %s: cloud %d = %f%%', self.id, i, sh)
                shadow += sh
            i += 1
        return shadow

    def _make_next_step(self, phase, new_data):
        if abs(new_data - self.data) >= 0.1:
            self.data = new_data
            log.brief('SunCtrl %s: %s %f%%', self.id, phase, self.data)
            self.post(MsgData(self.id, self.data))
        time.sleep(max( 1, new_data/30))  # shorten steps for low values


    def _fader(self):
        """ This fader uses smaller increments for low bightness to
            avoid visible steps. For higher brightness steps may be larger.

            For a more realistic transition from dark night to daylight,
            https://de.wikipedia.org/wiki/Sonnenaufgang may offer a quite simple formula
            "Zeitabhängigkeit der Helligkeit" as current approach ignores twilight
            before sunrise and after sunset completely - that's the most
            interesting time to watch some fish!
            The formula is E = 80*POWER(1,15; (t [min])), aproximating
            -60 ... 30 min for Germany.
            This would need a trigger 60min before sunrise, counter-intuitive!
            Should we ignore this effect for sunrise, but implement it for sunset??
            This is a limitation of our node concept, where schedule and light profile
            know nothing about each other.
            t	E           1.15^t
           (-70	0,0045      0,0001)
            -60	0,0182      0,0002
            -50	0,0738      0,0009
            -40	0,2987      0,0037
            -30	1,2082      0,0151
            -20	4,8880      0,0611
            -10	19,7748     0,2472
            0	80,0000     1,0000
            10	323,6446	4,0456
            20	1309,3230	16,3665
            30	5296,9418	66,2118
           (40	21429,0837	267,8635)
        """
        xscend = self.xscend * 60 * 60
        self.alert = ('\u2197', 'act')  # north east arrow
        start = now = time.time()
        while now - start < xscend:
            new_data = self._halfsine(now - start, xscend * 2, self.target)
            self._make_next_step('ascend', new_data)
            now = time.time()

        cloudiness = int(random.random() * 5.9)
        log.brief('SunCtrl %s: highnoon %f for %fh, cloudiness %d', self.id, self.target, self.highnoon, cloudiness)
        self.alert = None
        self.data = self.target
        self.post(MsgData(self.id, self.data))
        if not cloudiness:
            time.sleep(self.highnoon * 60 * 60)
        else:
            while now - start < self.highnoon * 60 * 60:
                self.alert = None
                new_data = self.target - self._calculate_clouds(cloudiness)
                self._make_next_step('cloudy', new_data)
                now = time.time()

        xscend = self.xscend * 60 * 60
        self.alert = ('\u2198', 'act')  # south east arrow
        start = now = time.time()
        while now - start < xscend:
            new_data = self._halfsine(now - start + xscend, xscend * 2, self.target)
            self._make_next_step('descend', new_data)
            now = time.time()

        log.brief('SunCtrl %s: DONE', self.id)
        self.alert = None
        self.post(MsgData(self.id, 0.0))

        self._fader_thread = None
        self._fader_stop = False

    def get_settings(self):
        settings = super().get_settings()
        settings.append(('highnoon', 'High noon hours [h]', self.highnoon, 'type="number" min="0" step="0.1"'))
        settings.append(('xscend', 'Ascend/descend hours [h]', self.xscend, 'type="number" min="0.1" max="5" step="0.1"'))
        return settings
