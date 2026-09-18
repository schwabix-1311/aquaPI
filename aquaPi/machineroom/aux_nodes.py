#!/usr/bin/env python3

from abc import ABC
from collections import deque
import logging
import statistics
from time import monotonic
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
    """ Rolling standard deviation of a received signal over a trailing
        time window - e.g. flags reduced water flow via increased
        temperature volatility (heater cycling not mixed away fast
        enough when circulation is weak). Pair with an AlertAbove
        watching this node's output; its `duration` field should be
        sized well beyond any normal settling transient (e.g. a PID
        walking off drift after a disturbance), so only variance that
        stays elevated for longer than that trips the alert.

        Options:
            window - trailing time window (seconds) the standard
                     deviation is computed over
            scale  - plain output multiplier, default 1.0 (no rescaling).
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
    """
    data_range = DataRange.ANALOG

    # guards against a misleadingly-confident stddev (0.0, or a fluke)
    # right after start or with a too-short window
    _MIN_SAMPLES = 5

    def __init__(self, name: str, receives: str, window: float = 3600,
                 scale: float = 1.0, _cont: bool = False):
        super().__init__(name, receives, _cont=_cont)
        self.window: float = window
        self.scale: float = scale
        self._samples: deque[tuple[float, float]] = deque()

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
        state["window"] = self.window
        state["scale"] = self.scale
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        StdDevAux.__init__(self, state['name'], state['receives'],
                           window=state['window'], scale=state.get('scale', 1.0),
                           _cont=True)

    def listen(self, msg: Msg) -> None:
        if isinstance(msg, MsgData):
            now = monotonic()
            self._samples.append((now, float(msg.data)))
            while self._samples and self._samples[0][0] < now - self.window:
                self._samples.popleft()
            if len(self._samples) >= self._MIN_SAMPLES:
                self.data = round(statistics.pstdev(v for _, v in self._samples) * self.scale, 4)
                log.verbose('StdDevAux %s: output %f', self.id, self.data)
                self.post(MsgData(self.id, self.data))

        super().listen(msg)

    def get_settings(self) -> list[Setting]:
        settings = super().get_settings()
        schema = {s.key: s for s in type(self).get_settings_schema()}
        settings.append(self._fill_setting(schema['window']))
        settings.append(self._fill_setting(schema['scale']))
        return settings

    @classmethod
    def get_settings_schema(cls) -> list[Setting]:
        schema = super().get_settings_schema()
        schema.append(Setting('window', 'stdDevWindow', 3600,
                              type='duration', min=300, max=24 * 60 * 60,
                              step=60))
        schema.append(Setting('scale', 'stdDevScale', 1.0, type='number', min=0))
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
