#!/usr/bin/env python3

from abc import ABC
import logging
from typing import Any
from time import (time, sleep)
import math
import random
from datetime import timedelta
from threading import Thread

from .msg_bus import (Msg, MsgData)
from .msg_bus import (BusListener, BusRole, DataRange)


log = logging.getLogger('machineroom.ctrl_nodes')
log.brief = log.warning  # alias, warning used as brief info, info is verbose


def get_unit_limits(unit: str) -> str:
    if ('°C') in unit:
        limits = 'min="15" max="35" step="0.1"'
    elif ('°F') in unit:
        limits = 'min="59" max="95" step="0.2"'
    elif ('pH') in unit:
        limits = 'min="5.0" max="9.0" step="0.05"'
    elif ('%') in unit:
        limits = 'min="0" max="100" step="1"'
    else:
        limits = ''
    return limits


# ========== controllers ==========


class ControllerNode(BusListener, ABC):
    """ The base class of all controllers, i.e. nodes that connect
        1 input to output(s).
        The required core of each controller chain.
    """
    ROLE = BusRole.CTRL
    data_range = DataRange.BINARY

    def __init__(self, name: str, receives: str, _cont: bool = False):
        super().__init__(name, receives, _cont=_cont)
        self.data: float = 0.0

    # def __getstate__(self) -> dict[str, Any]:
    #    return super().__getstate__()

    # def __setstate__(self, state: dict[str, Any]) -> None:
    #    ControllerNode.__init__(self, state, _cont=True)

    def is_advanced(self) -> bool:
        """ Advanced node chains include AUX nodes (or more than In->CTRL->OUT?)
            might become obsolete: the ctrl centric model doesn't hold
        """
        if not self._bus:
            return False
        for node in self.get_receives():
            if node.ROLE == BusRole.AUX:
                return True
        for node in self.get_listeners():
            if node.ROLE == BusRole.AUX:
                return True
        return False

    def get_settings(self) -> list[tuple]:
        return []  # don't inherit inputs!


class MinimumCtrl(ControllerNode):
    """ A controller switching an output to keep a minimum input value.
        Should usually drive an output changing the input in the appropriate
        direction. Can also be used to generate warning or error states.

        Options:
            name       - unique name of this controller node in UI
            receives   - id of a single (!) input to receive measurements from
            threshold  - the minimum measurement to maintain
            hysteresis - a tolerance, to reduce switch frequency

        Output:
            posts a single
              100 when input < (thr. - hyst./2),
              0 when input >= (thr. + hyst./2)
    """
    # TODO: could have a threshold for max. active time -> warning

    def __init__(self, name: str, receives: str, threshold: float,
                 hysteresis: float = 0, _cont: bool = False):
        super().__init__(name, receives, _cont=_cont)
        self.threshold: float = threshold
        self.hysteresis: float = hysteresis

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state.update(threshold=self.threshold)
        state.update(hysteresis=self.hysteresis)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        MinimumCtrl.__init__(self, state['name'], state['receives'],
                             state['threshold'], hysteresis=state['hysteresis'],
                             _cont=True)

    def listen(self, msg: Msg) -> bool:
        if isinstance(msg, MsgData):
            new_val = self.data
            if float(msg.data) < (self.threshold - self.hysteresis / 2):
                new_val = 100.0
            elif float(msg.data) >= (self.threshold + self.hysteresis / 2):
                new_val = 0.0

            if (self.data != new_val) or True:  #FIXME WAR a startup problem
                log.debug('MinimumCtrl: %d -> %d', self.data, new_val)
                self.data = new_val

                if msg.data < (self.threshold - self.hysteresis / 2) * 0.95:
                    self.alert = ('LOW', 'err')
                    log.brief('MinimumCtrl %s: output %f - alert %r',
                              self.id, self.data, self.alert)
                else:
                    self.alert = ('*', 'act')  if self.data else None
                    log.brief('MinimumCtrl %s: output %f', self.id, self.data)

                # only on data change? or always = 1 level outdented?
                self.post(MsgData(self.id, self.data))
        return super().listen(msg)

    def get_settings(self) -> list[tuple]:
        limits = get_unit_limits(self.unit)

        settings = super().get_settings()
        settings.append(('threshold', 'Minimum [%s]' % self.unit,
                         self.threshold, 'type="number" %s' % limits))
        settings.append(('hysteresis', 'Hysteresis [%s]' % self.unit,
                         self.hysteresis, 'type="number" min="0" max="5" step="0.01"'))
        return settings


class MaximumCtrl(ControllerNode):
    """ A controller switching an output to keep a maximum input value.
        Should usually drive an output changing the input in the appropriate
        direction. Can also be used to generate warning or error states.

        Options:
            name       - unique name of this controller node in UI
            receives   - id of a single (!) input to receive measurements from
            threshold  - the maximum measurement to maintain
            hysteresis - a tolerance, to reduce switch frequency

        Output:
            posts a single
              100 when input > (thr. - hyst./2),
              0 when input <= (thr. + hyst./2)
    """
    def __init__(self, name: str, receives: str, threshold: float,
                 hysteresis: float = 0, _cont: bool = False):
        super().__init__(name, receives, _cont=_cont)
        self.threshold: float = threshold
        self.hysteresis: float = hysteresis

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state.update(threshold=self.threshold)
        state.update(hysteresis=self.hysteresis)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        MaximumCtrl.__init__(self, state['name'], state['receives'],
                             state['threshold'], hysteresis=state['hysteresis'],
                             _cont=True)

    def listen(self, msg: Msg) -> bool:
        if isinstance(msg, MsgData):
            new_val = self.data
            if float(msg.data) > (self.threshold + self.hysteresis / 2):
                new_val = 100.0
            elif float(msg.data) <= (self.threshold - self.hysteresis / 2):
                new_val = 0.0

            if (self.data != new_val) or True:  #FIXME WAR a startup problem
                log.debug('MaximumCtrl: %d -> %d', self.data, new_val)
                self.data = new_val

                if msg.data > (self.threshold + self.hysteresis / 2) * 1.05:
                    self.alert = ('HIGH', 'err')
                    log.brief('MaximumCtrl %s: output %f - alert %r',
                              self.id, self.data, self.alert)
                else:
                    self.alert = ('*', 'act')  if self.data else None
                    log.brief('MaximumCtrl %s: output %f', self.id, self.data)

                # only on data change? or always = 1 level outdented?
                self.post(MsgData(self.id, self.data))
        return super().listen(msg)

    def get_settings(self) -> list[tuple]:
        limits = get_unit_limits(self.unit)

        settings = super().get_settings()
        settings.append(('threshold', 'Maximum [%s]' % self.unit,
                         self.threshold, 'type="number" %s' % limits))
        settings.append(('hysteresis', 'Hysteresis [%s]' % self.unit,
                         self.hysteresis, 'type="number" min="0" max="5" step="0.01"'))
        return settings


class PidCtrl(ControllerNode):
    """ A PID controller

        Options:
            name       - unique name of this controller node in UI
            receives   - id of a single (!) input to receive measurements from
            setpoint   - the target value
            p_fact/i_fact,d_fact - the PID factors, may be negative

        Output:
            posts percentage vakues (analog)
    """
    data_range = DataRange.PERCENT

    def __init__(self, name: str, receives: str, setpoint: float,
                 p_fact: float = 1.0, i_fact: float = 0.05, d_fact: float = 0.,
                 _cont: bool = False):
        super().__init__(name, receives, _cont=_cont)
        self.setpoint: float = setpoint
        self.p_fact: float = p_fact
        self.i_fact: float = i_fact
        self.d_fact: float = d_fact
        self._err_sum: float = 0
        self._err_old: float = 0
        self._tm_old: float = 0
        self.data: float = 0.

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state.update(setpoint=self.setpoint)
        state.update(p_fact=self.p_fact)
        state.update(i_fact=self.i_fact)
        state.update(d_fact=self.d_fact)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        log.debug('__SETstate__ %r', state)
        self.data = state['data']
        PidCtrl.__init__(self, state['name'], state['receives'], state['setpoint'],
                         p_fact=state['p_fact'], i_fact=state['i_fact'], d_fact=state['d_fact'],
                         _cont=True)

    def listen(self, msg) -> bool:
        if isinstance(msg, MsgData):
            log.debug('PID got %s', msg)
            now = time()
            ta = now - self._tm_old
            err = float(msg.data) - self.setpoint
            if self._tm_old >= 1.:
                self._err_sum = self._err_sum / 1 + err
                p_dev = self.p_fact * err
                i_dev = self.i_fact * ta * self._err_sum  / 100 #??
                d_dev = self.d_fact / ta * (err - self._err_old)
                val = p_dev + i_dev + d_dev

                log.warning('PID err %f, e-sum %f | P %+.1f%% / I %+.1f%% / D %+.1f %%, ',
                          err, self._err_sum,
                          100 * p_dev, 100 * i_dev, 100 * d_dev)
                self.data = min(max(0., 50. - val*100.), 100.)
                log.brief('PID -> %f (%+.1f)', self.data, -val * 100)
                self.post(MsgData(self.id, round(self.data, 4)))

                if self.data <= 0. or self.data >= 100.:
                    self._err_sum /= 2
            self._err_old = err
            self._tm_old = now

        return super().listen(msg)

    def get_settings(self) -> list[tuple]:
        settings = super().get_settings()
        settings.append(('setpoint', 'Sollwert [%s]' % self.unit,
                         self.setpoint, 'type="number" step="0.1"'))
        settings.append(('p_fact', 'P Faktor', self.p_fact, 'type="number" min="-10" max="10" step="0.1"'))
        settings.append(('i_fact', 'I Faktor', self.i_fact, 'type="number" min="-10" max="10" step="0.01"'))
        settings.append(('d_fact', 'D Faktor', self.d_fact, 'type="number" min="-10" max="10" step="0.1"'))
        return settings


class FadeCtrl(ControllerNode):
    """ Single channel linear fading controller, usable for light (dusk/dawn).
        A change of input value will start a ramp from current to new
        percentage. The duration of this ramp is deltaPerc / 100 * fade_time.
        Durations for fade-in and fade-out can be different and may be 0 for
        hard switches.
        The ramp steps by 0.1%, or more to keep step duration >= 100 ms.

        Options:
            name       - unique name of this controller node in UI
            receives   - id of a single (!) input to receive measurements from
            fade_time  - time span in secs to transition to the target state
            fade_out   - optional time span in secs to transition to off
                         defaults to fade_time

        Output:
            float - posts series of percentages after input state change
    """
    data_range = DataRange.PERCENT

    def __init__(self, name: str, receives: str,
                 fade_time: int | timedelta = 0,
                 fade_out: int | timedelta | None = 0, _cont: bool = False):
        super().__init__(name, receives, _cont=_cont)
        if isinstance(fade_time, timedelta):
            self.fade_time: int = int(fade_time.total_seconds())
        else:
            self.fade_time = fade_time

        if fade_out is None:
            self.fade_out: int = self.fade_time
        else:
            if isinstance(fade_out, timedelta):
                self.fade_out = int(fade_out.total_seconds())
            else:
                self.fade_out = fade_out
        self._fader_thread: Thread | None = None
        self._fader_stop: bool = False
        if not _cont:
            self.data = 0.0
        self.target: float = self.data
        self.unit: str = '%'

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state.update(fade_time=self.fade_time)
        state.update(fade_out=self.fade_out)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        FadeCtrl.__init__(self, state['name'], state['receives'],
                          fade_time=state['fade_time'], fade_out=state['fade_out'],
                          _cont=True)

    def listen(self, msg: Msg) -> bool:
        if isinstance(msg, MsgData):
            log.info('FadeCtrl: got %f', msg.data)
            self.target = float(msg.data)
            if self.data != self.target:
                if self._fader_thread:
                    self._fader_stop = True
                    self._fader_thread.join()
                    self.post(MsgData(self.id, round(self.data, 4)))  # start of new ramp

                # fade_time or fade_out can be 0 -> switch to target
                if (self.data < self.target and not self.fade_time) \
                 or (self.data > self.target and not self.fade_out):
                    self.data = self.target
                    log.brief('FadeCtrl %s: output %f', self.id, self.data)
                    self.post(MsgData(self.id, self.data))
                else:
                    log.debug('_fader %f -> %f', self.data, self.target)
                    self._fader_thread = Thread(name=self.id, target=self._fader, daemon=True)
                    self._fader_thread.start()
        return super().listen(msg)

    def _fader(self):
        """ This fader uses constant steps of 0.1% unless this would be >10 steps/sec
        """
        f_time = self.fade_time  if self.data < self.target else self.fade_out
        delta_d = self.target - self.data      # total change
        delta_t = abs(delta_d) / 100 * f_time  # total time for this change
        step_t = max(delta_t / 1000, 0.1)      # try 1000 steps, at most 10 steps per sec
        step_d = delta_d * step_t / delta_t
        log.brief('FadeCtrl %s: fading in %f s from %f -> %f, change by %f every %f s',
                  self.id, delta_t, self.data, self.target, step_d, step_t)

        next_t = time() + step_t
        while abs(self.target - self.data) > abs(step_d):
            self.data += step_d
            log.debug('_fader %f ...', self.data)

            self.alert = ('\u2197' if self.target > self.data else '\u2198', 'act')
            self.post(MsgData(self.id, round(self.data, 4)))
            sleep(max(0, next_t - time()))
            next_t += step_t
            if self._fader_stop:
                log.brief('FadeCtrl %s: fader stopped', self.id)
                break
        else:
            if self.data != self.target:
                self.data = self.target
                self.post(MsgData(self.id, self.data))  # end of ramp
            self.alert = None
            log.brief('FadeCtrl %s: fader DONE', self.id)

        self._fader_thread = None
        self._fader_stop = False

    def get_settings(self) -> list[tuple]:
        settings = super().get_settings()
        settings.append(('fade_time', 'Fade-In time [s]',
                         self.fade_time, 'type="number" min="0"'))
        settings.append(('fade_out', 'Fade-Out time [s]',
                         self.fade_out, 'type="number" min="0"'))
        return settings


class Cloud(object):
    """ Represents a single cloud
    """
    def __init__(self, cloudiness: int):
        self.born: float = time()
        if cloudiness & 1:  # odd weather types have shorter darker clouds
            self.duration: int = random.randint(1, 60 * 60)
            self.darkness: int = random.randint(1, 20)
        else:
            self.duration = random.randint(1, 8 * 60 * 60)
            self.darkness = random.randint(1, 8)

    def current_shadow(self) -> float:
        return self.halfsine(time() - self.born, self.duration, self.darkness)

    @staticmethod
    def halfsine(elapsed_t, wave_t, max_p):
        """ calculate value of a sine half-wave of amplitude max_p
            and duration wave_t at position elapsed_t

            For a more realistic transition from dark night to daylight and
            back, https://de.wikipedia.org/wiki/Sonnenaufgang offers a quite
            simple formula "Zeitabhängigkeit der Helligkeit".
            The formula is E = 80*POWER(1,15; (t [min])), aproximating
            -60 ... +30 min of sun rise for Germany.
            This does not work well with our Scheduler trigger, as at
            "sun rise" time the brightness is not 0.
            A trigger 60min before sunrise would be unexpected. Should we
            ignore this effect for sunrise, but implement it for sunset??
            t	E           1.15^t
           (-70	0,0045      0,0001)
            -60	0,0182      0,0002
            -50	0,0738      0,0009
            -40	0,2987      0,0037
            -30	1,2082      0,0151
            -20	4,8880      0,0611
            -10	19,7748     0,2472
            0	80,0000     1,0000 (sun rise!)
            10	323,6446	4,0456
            20	1309,3230	16,3665
            30	5296,9418	66,2118
           (40	21429,0837	267,8635)
            And how is this related to max brightness?
        """
        t = elapsed_t / wave_t * math.pi
        return math.sin(t) * max_p


class SunCtrl(ControllerNode):
    """ A single channel light controller, simulating ascend/descend
        aproximated by a sine wave (xscend).
        Any input change starts a new cycle; an ongoing cycle is aborted.
        Unlike FadeCtrl, SunCtrl starts ascend with darkness.
        As soon as a target level (>0) is reached the random cloud simulation
        will start. An input of 0 will stop this and trigger a descend.
        The ramp steps by >=0.1% to keep step duration >= 100 ms.

        Options:
            name     - unique name of this controller node in UI
            receives - id of a single (!) input to receive measurements from
            xscend   - duration of each of ascend and descend

        Output:
            float - posts series of percentages after input state change
    """
    data_range = DataRange.PERCENT

    def __init__(self, name: str, receives: str,
                 xscend: float = 1, _cont: bool = False):
        super().__init__(name, receives, _cont=_cont)
        self.xscend = xscend
        if xscend and isinstance(xscend, timedelta):
            self.xscend = xscend.total_seconds() / 60 / 60
        self._fader_thread: Thread | None = None
        self._fader_stop: bool = False
        self._high: float = 0.0
        if not _cont:
            self.data = 0.0
        self.target: float = self.data
        self.unit: str = '%'
        self.clouds: list[Cloud] = []
        self.cloudiness = 0

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state.update(xscend=self.xscend)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        SunCtrl.__init__(self, state['name'], state['receives'],
                         xscend=state['xscend'],
                         _cont=True)

    def listen(self, msg):
        if isinstance(msg, MsgData):
            log.info('SunCtrl: got %f', msg.data)
            if self._fader_thread:
                self._fader_stop = True
                self._fader_thread.join()
            self.target = float(msg.data)
            if self.target:
                self._high = self.target
                self.cloudiness = int(random.random() * 7.5)
                log.brief('SunCtrl: cloudiness %d', self.cloudiness)

            if self.target != self.data:
                log.debug('_fader %f -> %f', self.data, self.target)
                self._fader_thread = Thread(name=self.id, target=self._fader, daemon=True)
                self._fader_thread.start()

    def _make_next_step(self, phase, new_data):
        if abs(new_data - self.data) >= 0.1:
            self.data = new_data
            log.info('SunCtrl %s: %s %f%%', self.id, phase, self.data)
            self.post(MsgData(self.id, self.data))
        sleep(max(1, new_data/30))  # shorten steps for low values

    def _calculate_clouds(self) -> float:
        if random.random() < 0.002 and len(self.clouds) < self.cloudiness:
            cloud = Cloud(self.cloudiness)
            self.clouds.append(cloud)
            log.brief('SunCtrl %s: new cloud (%dmin | %d%%)', self.id, cloud.duration/60, cloud.darkness)

        shadow = 0.0
        for i, cloud in enumerate(self.clouds.copy()):
            if cloud.born + cloud.duration < time():
                self.clouds.remove(cloud)
            else:
                sh = cloud.current_shadow()
                log.debug('SunCtrl %s: cloud %d = %f%%', self.id, i, sh)
                shadow = min(shadow + sh, 80)
        shadow = (100.0 - shadow) / 100
        log.debug('SunCtrl %s: cloud factor %f', self.id, shadow)
        return shadow

    def _fader(self):
        """ This fader updates every second in low range, less often >30%
            Changes are delayed until <0.1%
        """
        xscend = self.xscend * 60 * 60
        start = now = time()
        if self.target:
            self.alert = ('\u2197', 'act')  # north east arrow
            self.data = 0  # sart of ascend
            self.post(MsgData(self.id, self.data))
            while now - start < xscend and not self._fader_stop:
                shadow = self._calculate_clouds()
                new_data = Cloud.halfsine(now - start, xscend * 2, self._high) * shadow
                self._make_next_step('ascend', new_data)
                now = time()

            # loop with clouds until fader_stop
            #FIXME: post some heartbeat values to keep diagram nice - could help everywhere ...
            while not self._fader_stop:
                shadow = self._calculate_clouds()
                self.alert = ('\u219d', 'act') if shadow else None  # rightwards wave arrow
                new_data = self._high * shadow
                self._make_next_step('cloudy', new_data)
                now = time()
        else:
            self.alert = ('\u2198', 'act')  # south east arrow
            while now - start < xscend and not self._fader_stop:
                shadow = self._calculate_clouds()
                new_data = Cloud.halfsine(now - start + xscend, xscend * 2, self._high) * shadow
                self._make_next_step('descend', new_data)
                now = time()
            self.data = 0  # end of descend


        log.brief('SunCtrl %s: fader %s', self.id, 'DONE' if not self._fader_stop else 'stopped')
        self.post(MsgData(self.id, self.data))
        self.alert = None
        self._fader_thread = None
        self._fader_stop = False

    def get_settings(self) -> list[tuple]:
        settings = super().get_settings()
        settings.append(('xscend', 'Ascend/descend hours [h]',
                         self.xscend, 'type="number" min="0.1" max="5" step="0.1"'))
        return settings
