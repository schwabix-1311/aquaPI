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


class LightCtrl(ControllerNode):
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
    data_range = DataRange.PERCENT

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
        self.target = self.data

    def __getstate__(self):
        state = super().__getstate__()
        state.update(fade_time=self.fade_time)
        log.debug('LightCtrl.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('LightCtrl.setstate %r', state)
        self.data = state['data']
        self.__init__(state['name'], state['inputs'], fade_time=state['fade_time'], _cont=True)

    def listen(self, msg):
        if isinstance(msg, MsgData):
            log.info('LightCtrl: got %f', msg.data)
            if self.data != float(msg.data):
                if not self.fade_time:
                    self.data = float(msg.data)
                    log.brief('LightCtrl %s: output %f', self.id, self.data)
                    self.post(MsgData(self.id, self.data))
                else:
                    if self._fader_thread:
                        self._fader_stop = True
                        self._fader_thread.join()
                    self.target = float(msg.data)
                    log.debug('_fader %f', self.target)
                    self._fader_thread = Thread(name=self.id, target=self._fader, daemon=True)
                    self._fader_thread.start()

    def _fader(self):
        # TODO: adjust the calculation, short fade_times need longer or show steps
        INCR = 0.1 if self.fade_time >= 30 else 1.0 if self.fade_time >= 2.9 else 2.0
        if self.target != self.data:
            step = (self.fade_time / abs(self.target - self.data) * INCR)
            log.brief('CtrLight %s: fading in %f s from %f -> %f, change every %f s', self.id, self.fade_time,
                      self.data, self.target, step)
            while abs(self.target - self.data) > INCR:
                if self.target >= self.data:
                    self.data += INCR
                else:
                    self.data -= INCR
                log.debug('_fader %f ...', self.data)

                self.alert = ('+' if self.target > self.data else '-', 'act')
                self.post(MsgData(self.id, round(self.data, 3)))
                time.sleep(step)
                if self._fader_stop:
                    break
            if self.data != self.target:
                self.data = self.target
                self.alert = None
                self.post(MsgData(self.id, self.data))
        log.brief('LightCtrl %s: fader DONE', self.id)
        self._fader_thread = None
        self._fader_stop = False

    def get_settings(self):
        settings = super().get_settings()
        settings.append(('fade_time', 'Fade time [s]', self.fade_time, 'type="number" min="0"'))
        return settings
