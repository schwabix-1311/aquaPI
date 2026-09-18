#!/usr/bin/env python3

from abc import ABC
from collections import deque
import logging
import statistics
from typing import (Callable, Iterable, Any)

from .msg_types import (Msg, MsgData)
from .msg_bus import (BusListener, BusRole, DataRange, Setting)


log = logging.getLogger('machineroom.aux_nodes')


# ========== auxiliary bases ==========


class AuxNode(BusListener, ABC):
    """ Auxiliary nodes are for advanced configurations where
        direct connections of input to controller or controller to
        output aren't sufficient.
    """
    ROLE = BusRole.AUX


class SingleInAux(AuxNode, ABC):
    """ subtype of AuxNode listening to a single input
    """
    def __init__(self, name: str, receives: str, _cont: bool = False):
        super().__init__(name, receives, _cont=_cont)
        self.data = -1


class MultiInAux(AuxNode, ABC):
    """ subtype of AuxNode listening to more than 1 input
    """
    _receives_kind = 'multi'

    def __init__(self, name: str, receives: Iterable[str], _cont: bool = False):
        super().__init__(name, receives, _cont=_cont)
        self.values: dict[str, float] = {}
        self.rcv_unit: str = ''
        self.data = -1

    def __getstate__(self) -> dict[str, Any]:
        for rcv in self.get_receives():
            self.rcv_unit = rcv.unit
            self.unit = rcv.unit
            self.data_range = rcv.data_range  # depends on inputs
            break
        # update self.data_range/unit above before calling super(), since
        # BusNode.__getstate__() snapshots them into the returned state -
        # doing it after would report last call's stale data_range
        state = super().__getstate__()
        state["unit"] = self.unit
        # per-sender last-received values, keyed by sender node id - a
        # sender's own .data doesn't necessarily reflect every message
        # it posts (e.g. SlowPwmDevice._pulse() posts transient on/off
        # states without updating its own .data), so a consumer that
        # wants what THIS node actually received needs its own record,
        # not the sender's separately-fetched current state
        state["values"] = self.values
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        MultiInAux.__init__(self, state['name'], state['receives'],
                            _cont=True)
        self.values = state.get('values', {})


# ========== auxiliary ==========


class ScaleAux(SingleInAux):
    """ A 1:1 node rescaling via a graph defined by 2 calibration
        points - useful for calibrating linear (!) sensors, and quite
        a few other creative use cases.

        offset/factor (out = in * factor + offset) are the actual
        runtime math, but are never independently stored or settable -
        they're derived once from `points` here (in __init__, so
        listen() stays a cheap read of self.offset/self.factor, not a
        recompute per message) and again whenever `points` changes.
        `points` is the one thing a user actually calibrates against
        and can interpret later (e.g. "6.9 pH = 2.51 V"), unlike a bare
        offset/factor number - see [[project ScaleAux 2-point-only]].

        Options:
            unit   - the unit after scaling the received data
            points - exactly 2 calibration points, each
                     {'measured': <raw value>, 'reference': <target
                     value>} - required, no default: a ScaleAux with
                     no calibration is a modelling mistake, not a
                     valid state.
            limit  - limit result to this range,
                     defaults to 0.0 .. 100.0
    """
    data_range = DataRange.ANALOG

    def __init__(self, name: str, receives: str, unit: str,
                 points: list[dict[str, float]],
                 limit: tuple[float, float] = (0.0, 100.0),
                 _cont: bool = False):
        super().__init__(name, receives, _cont=_cont)
        self.unit: str = unit
        self.points: list[dict[str, float]] = points
        self.offset: float = 0.0
        self.factor: float = 1.0
        try:
            dX = points[1]['measured'] - points[0]['measured']
            dY = points[1]['reference'] - points[0]['reference']
            self.factor = dY / dX
            self.offset = points[0]['reference'] - self.factor * points[0]['measured']
        except (TypeError, IndexError, KeyError, ZeroDivisionError):
            log.error('ScaleAux %s: No valid calibration points found', self.name)

        self.limit: tuple[float, float] = limit
        try:
            self.limit = (limit[0], limit[1])
        except (TypeError, IndexError):
            log.error('ScaleAux %s: limit must be a tupel of floats', self.name)

        log.verbose('ScaleAux %s: factor %f, offset %f, limiting %s',
                    name, self.factor, self.offset, str(self.limit))

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state["unit"] = self.unit
        state["points"] = self.points
        state["limit"] = self.limit
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        ScaleAux.__init__(self, state['name'], state['receives'], unit=state['unit'],
                          points=state['points'], limit=state['limit'],
                          _cont=True)

    def listen(self, msg: Msg) -> None:
        if isinstance(msg, MsgData):
            self.data = self.factor * float(msg.data) + self.offset
            self.data = min(max(self.limit[0], self.data), self.limit[1])
            log.verbose('ScaleAux %s: output %f', self.id, self.data)
            self.post(MsgData(self.id, self.data))

        super().listen(msg)

    def get_settings(self) -> list[Setting]:
        settings = super().get_settings()
        schema = {s.key: s for s in type(self).get_settings_schema()}
        settings.append(self._fill_setting(schema['unit']))
        settings.append(schema['points'].with_value(self.points))
        # settings.append(Setting('limit', 'Grenzen', self.limit,
        #                         type='combo'))  #  None/0..100/(min,max)
        return settings

    @classmethod
    def get_settings_schema(cls) -> list[Setting]:
        schema = super().get_settings_schema()
        schema.append(Setting('unit', 'unit', ''))
        # not a generic-widget field - CalibrationHelper (a bespoke SPA
        # component, not the generic Setting dispatch) is the only editor;
        # 'required' is what makes /wiring's whole-draft save check reject
        # a newly-created ScaleAux until it's actually been calibrated
        schema.append(Setting('points', 'calibrationPoints', None,
                              type='calibration-points', required=True,
                              custom_widget=True))
        return schema


class StdDevAux(SingleInAux):
    """ Standard deviation of a signal's N most recent readings - e.g.
        flags reduced water flow via increased temperature volatility
        (heater cycling not mixed away fast enough when circulation is
        weak). Pair with an AlertAbove watching this node's output; its
        `duration` field should be sized well beyond any normal settling
        transient (e.g. a PID walking off drift after a disturbance), so
        only variance that stays elevated for longer than that trips the
        alert.

        Options:
            samples - number of most recent readings the standard
                      deviation is computed over - not a time span: how
                      much real time that covers depends entirely on the
                      source's own read interval. Deliberately count-
                      based, same pattern as AvgAux - a time-windowed
                      version was tried first, but a source's read
                      interval is a live Setting this node has no
                      visibility into (and isn't even guaranteed to
                      exist - a non-InputNode source has no fixed cadence
                      at all), so a too-short time window relative to a
                      slow source could never accumulate enough samples
                      before the oldest one aged back out - permanently,
                      not just slower. A plain sample count can't have
                      that problem: it always eventually fills for any
                      source cadence. Nothing here needs the extra
                      precision of "the last hour" vs. "the last 30
                      readings" anyway - there's no responsiveness
                      requirement (a fish tank's temperature is slow, and
                      the paired Alert's `duration` is already meant to
                      be hours).
            scale   - plain output multiplier, default 1.0 (no rescaling).
                     Charted next to its source, a source-unit stddev is
                     usually tiny next to the source's own magnitude (e.g.
                     0.05 °C next to a 25 °C reading) and lands on the same
                     auto-scaling chart axis as that source, so it reads as
                     a flat line near zero. A scale > 1 (e.g. 100) both
                     spreads it back into a visible range and - since the
                     result is no longer literally in the source's unit -
                     switches the reported unit to '%', which routes it
                     onto the dashboard's separate, fixed 0-100 axis
                     instead (see dashboard/comps.js's yAxisID logic).
                     Deliberately a plain multiplier, not a percentage of
                     the window's mean (coefficient of variation) - that
                     would divide by a value that can sit at/near zero for
                     some sources (e.g. a duty-cycle output at 0%, or a
                     sensor whose range straddles zero), blowing up for
                     reasons unrelated to actual variability.
            auto_scale - if set, `scale` is computed once (not
                     continuously - see below) from the first raw stddev
                     this node ever computes, targeting `_AUTO_SCALE_TARGET`,
                     then left alone; disable to set `scale` by hand
                     instead. Deliberately a *one-time* calibration, not
                     a continuously-adapting one: if `scale` kept being
                     recomputed from a recent/current value, the display
                     would auto-normalize toward a constant target
                     regardless of whether things are actually fine or
                     bad right now - exactly the kind of change this node
                     exists to surface, silently masked by the very
                     mechanism meant to make it visible. A one-time
                     calibration risks only its *starting* assumption (the
                     first window happens to be representative/"sane") -
                     accepted deliberately: if it isn't, the monitored
                     signal still has to get *worse than that* to raise
                     the flag, which is a materially smaller problem than
                     an alert that can never fire because it keeps
                     rescaling itself back to "normal".
    """
    data_range = DataRange.ANALOG

    # the same rule of thumb folded into the 'scale' field's own label
    # (i18n/locales/*.js's stdDevScale) - see that field's docstring bullet
    _AUTO_SCALE_TARGET = 10

    def __init__(self, name: str, receives: str, samples: int = 30,
                 scale: float = 1.0, auto_scale: bool = False,
                 _cont: bool = False):
        super().__init__(name, receives, _cont=_cont)
        self.samples: int = samples
        self.scale: float = scale
        # only ever transitions False -> True, once, for this node
        # instance's lifetime (see auto_scale's docstring) - a process
        # restart (a fresh __init__ via __setstate__) is the only way to
        # re-arm it, deliberately not persisted
        self._calibrated: bool = False
        # bypass the auto_scale property setter here - constructing/
        # restoring a node must NOT clear an already-calibrated (or
        # user-set) scale, only a live re-toggle should (see the setter)
        self._auto_scale: bool = auto_scale
        self._values: deque[float] = deque(maxlen=samples)

    @property
    def auto_scale(self) -> bool:
        return self._auto_scale

    @auto_scale.setter
    def auto_scale(self, value: bool) -> None:
        # a live re-enable (e.g. via /wiring, on an already-running node -
        # __init__ above sets self._auto_scale directly and never reaches
        # here) re-arms calibration and clears whatever scale currently
        # holds, so the dashboard doesn't keep showing a stale pre-toggle
        # value until the next reading happens to recalibrate it
        if value and not self._auto_scale:
            self._calibrated = False
            self.scale = 1.0
        self._auto_scale = value

    def __getstate__(self) -> dict[str, Any]:
        # a standard deviation carries its source's unit (a °C signal's
        # stddev is itself in °C) - unless rescaled, in which case it's no
        # longer literally in that unit, so report '%' instead (also what
        # routes it onto the dashboard's dedicated 0-100 axis, see class
        # docstring). Update self.unit before calling super(), since
        # BusNode.__getstate__() snapshots it into the returned state
        # (same pattern as MultiInAux.__getstate__, minus data_range: that
        # one stays statically ANALOG, see class docstring)
        for rcv in self.get_receives():
            self.unit = rcv.unit if self.scale == 1.0 else '%'
            break
        state = super().__getstate__()
        state["samples"] = self.samples
        state["scale"] = self.scale
        state["auto_scale"] = self.auto_scale
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        # a node saved before 'samples'/'auto_scale' existed (the old
        # time-windowed 'window' Setting) has no such keys - fall back to
        # the schema defaults rather than reinterpret an old seconds
        # value as a sample count (nonsensical, e.g. "3600 samples")
        StdDevAux.__init__(self, state['name'], state['receives'],
                           samples=state.get('samples', 30),
                           scale=state.get('scale', 1.0),
                           auto_scale=state.get('auto_scale', False),
                           _cont=True)

    def listen(self, msg: Msg) -> None:
        if isinstance(msg, MsgData):
            self._values.append(float(msg.data))
            if len(self._values) >= self.samples:
                raw = statistics.pstdev(self._values)
                if self.auto_scale and not self._calibrated:
                    # a perfectly flat first window (raw == 0) can't
                    # calibrate a scale from - retry on the next reading
                    # rather than lock in a divide-by-zero/nonsense value
                    if raw > 0:
                        self.scale = round(self._AUTO_SCALE_TARGET / raw, 4)
                        self._calibrated = True
                        log.verbose('StdDevAux %s: auto-calibrated scale to %f',
                                   self.id, self.scale)
                self.data = round(raw * self.scale, 4)
                log.verbose('StdDevAux %s: output %f', self.id, self.data)
                self.post(MsgData(self.id, self.data))

        super().listen(msg)

    def get_settings(self) -> list[Setting]:
        settings = super().get_settings()
        schema = {s.key: s for s in type(self).get_settings_schema()}
        settings.append(self._fill_setting(schema['samples']))
        settings.append(self._fill_setting(schema['scale']))
        settings.append(self._fill_setting(schema['auto_scale']))
        return settings

    @classmethod
    def get_settings_schema(cls) -> list[Setting]:
        schema = super().get_settings_schema()
        schema.append(Setting('samples', 'stdDevSamples', 30, type='number', min=2))
        schema.append(Setting('scale', 'stdDevScale', 1.0, type='number', min=0))
        schema.append(Setting('auto_scale', 'stdDevAutoScale', False, type='checkbox'))
        return schema


class AvgAux(MultiInAux):
    """ Auxiliary node to build average of 2 or more inputs.
        Weighting can be fair - every sender's latest input accounts once -
        or unfair - the most active sender contributes most and dead inputs
        loose their influence on result quickly.
        For redundancy, unfair may be the better option.

        Options:
            name       - unique name of this auxiliar node in UI
            receives   - collection of input ids
            unfair_avg - 0 = equally weights all inputs
                         >0 = moving average of received input values,
                              higher frequency increases weight,
                              thus unfair for unequally active senders

        Output:
            float - posts changes of arithmetic average of inputs
    """

    def __init__(self, name: str, receives: Iterable[str],
                 unfair_avg: int = 0, _cont: bool = False):
        super().__init__(name, receives, _cont=_cont)
        self.unfair_avg: int = unfair_avg

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state["unfair_avg"] = self.unfair_avg
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        AvgAux.__init__(self, state['name'], state['receives'],
                        unfair_avg=state['unfair_avg'], _cont=True)

    def listen(self, msg: Msg) -> None:
        if isinstance(msg, MsgData):
            if self.unfair_avg:
                if self.data == -1:
                    val = float(msg.data)
                else:
                    # unfair_avg-1 is the amount of old data to factor in
                    old_data = self.data * (self.unfair_avg - 1)
                    val = (float(msg.data) + old_data) / self.unfair_avg
            else:
                self.values[msg.sender] = float(msg.data)
                val = 0.
                for k in self.values:
                    val += self.values[k] / len(self.values)

            self.data = round(val, 4)
            log.verbose('AvgAux %s: output %f', self.id, self.data)
            self.post(MsgData(self.id, self.data))

        super().listen(msg)

    def get_settings(self) -> list[Setting]:
        settings = super().get_settings()
        schema = {s.key: s for s in type(self).get_settings_schema()}
        settings.append(self._fill_setting(schema['unfair_avg']))
        return settings

    @classmethod
    def get_settings_schema(cls) -> list[Setting]:
        schema = super().get_settings_schema()
        schema.append(Setting('unfair_avg', 'unfairAvg', 0, type='number', min=0, step=1))
        return schema


class _MinMaxAux(MultiInAux, ABC):
    """ shared implementation for MinAux/MaxAux - only the aggregate
        function differs between them
    """
    _AGGREGATE: Callable[[Iterable[float]], float]

    def listen(self, msg: Msg) -> None:
        if isinstance(msg, MsgData):
            val = float(msg.data)
            self.values[msg.sender] = val
            self.data = round(self._AGGREGATE(self.values.values()), 4)
            log.verbose('%s %s: output %f', type(self).__name__, self.id, self.data)
            self.post(MsgData(self.id, self.data))

        super().listen(msg)


class MinAux(_MinMaxAux):
    """ Auxiliary node to post the lower of two or more inputs = boolenan AND.
        Can be used to let two controllers drive one output, or to have
        redundant inputs.

        Options:
            name     - unique name of this auxiliary node in UI
            receives - collection of input ids

        Output:
            float - posts changes of minimum value of all inputs
    """
    _AGGREGATE = staticmethod(min)


class MaxAux(_MinMaxAux):
    """ Auxiliary node to post the higher of two or more inputs = boolean OR.
        Can be used to let two controllers drive one output, or to have
        redundant inputs.

        Options:
            name     - unique name of this auxiliary node in UI
            receives - collection of input ids

        Output:
            float - posts changes of maximum value of all inputs
    """
    _AGGREGATE = staticmethod(max)


# ========== user-facing visualization ==========


class UiDisplay(MultiInAux):
    """ Visualizes whatever it receives from other nodes on the
        dashboard - no aggregation/math, purely presentational (e.g.
        grouping a few related sensors/controls onto one card). Handles
        any mix of data ranges; the dashboard widget formats each
        received value according to its own data_range.

        Options:
            name     - unique name of this node in UI
            receives - collection of input ids

        Output:
            mirrors the most recently received value
    """

    def listen(self, msg: Msg) -> None:
        if isinstance(msg, MsgData):
            self.values[msg.sender] = msg.data
            self.data = msg.data
            self.post(MsgData(self.id, self.data))

        super().listen(msg)
