#!/usr/bin/env python3

import logging
import time
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

            if self.data != new_val:
                log.debug('MinimumCtrl: %d -> %d', self.data, new_val)
                self.data = new_val

                if msg.data < (self.threshold - self.hysteresis / 2) * 0.95:
                    self.alert = ('LOW', 'err')
                    log.brief('MinimumCtrl %s: output %f - alert %r', self.id, self.data, self.alert)
                elif self.data:
                    self.alert = ('*', 'act')
                else:
                    self.alert = None
                    log.brief('MinimumCtrl %s: output %f', self.id, self.data)

                self.post(MsgData(self.id, self.data))  # only on data change? or 1 level outdented?
        return super().listen(msg)

    def get_settings(self):
        limits = get_unit_limits(self.find_source_unit())

        settings = super().get_settings()
        settings.append(
            ('threshold', 'Minimum [%s]' % self.unit, self.threshold, 'type="number" %s step="0.1"' % limits))
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

            if self.data != new_val:
                log.debug('MaximumCtrl: %d -> %d', self.data, new_val)
                self.data = new_val

                if msg.data < (self.threshold - self.hysteresis / 2) * 0.95:
                    self.alert = ('HIGH', 'err')
                    log.brief('MaximumCtrl %s: output %f - alert %r', self.id, self.data, self.alert)
                elif self.data:
                    self.alert = ('*', 'act')
                else:
                    self.alert = None
                    log.brief('MaximumCtrl %s: output %f', self.id, self.data)

                self.post(MsgData(self.id, self.data))  # only on data change? or 1 level outdented?
        return super().listen(msg)

    def get_settings(self):
        limits = get_unit_limits(self.find_source_unit())

        settings = super().get_settings()
        settings.append(
            ('threshold', 'Maximum [%s]' % self.unit, self.threshold, 'type="number" %s step="0.1"' % limits))
        settings.append(
            ('hysteresis', 'Hysteresis [%s]' % self.unit, self.hysteresis, 'type="number" min="0" max="5" step="0.01"'))
        return settings


class FadeCtrl(ControllerNode):
    """ A single channel linear fading controller, usable for light (dust/dawn).
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
                    log.debug('_fader %f', self.target)
                    log.error('_fader %f -> %f', self.data, self.target)
                    self._fader_thread = Thread(name=self.id, target=self._fader, daemon=True)
                    self._fader_thread.start()

    def _fader(self):
        if self.target != self.data:
            f_time = self.fade_time  if self.data < self.target else self.fade_out
            delta_d = self.target - self.data      # total change
            delta_t = abs(delta_d) / 100 * f_time  # total time for this change
            step_t = max(delta_t / 1000, 0.1)      # try 1000 steps, at most 10 steps per sec
            step_d = delta_d * step_t / delta_t
            log.brief('CtrLight %s: fading in %f s from %f -> %f, change by %f every %f s'
                     , self.id, delta_t, self.data, self.target, step_d, step_t)

            next_t = time.time() + step_t
            while abs(self.target - self.data) > abs(step_d):
                self.data += step_d
                log.debug('_fader %f ...', self.data)

                self.alert = ('+' if self.target > self.data else '-', 'act')
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
