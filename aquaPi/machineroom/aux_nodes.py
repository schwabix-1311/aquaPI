#!/usr/bin/env python3

from abc import ABC
from collections import deque
import logging
import statistics
import time
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


class VolatilityAux(SingleInAux):
    """ Standard deviation or variance (see `metric`) of a signal's N most
        recent readings - e.g. flags reduced water flow via increased
        temperature volatility (heater cycling not mixed away fast enough
        when circulation is weak). Pair with an AlertAbove watching this
        node's output; its `duration` field should be sized well beyond
        any normal settling transient (e.g. a PID walking off drift after
        a disturbance), so only volatility that stays elevated for longer
        than that trips the alert.

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
                     continuously - see below) from the 90th percentile of
                     every raw stddev this node computes over the first
                     `_AUTO_SCALE_DURATION` of real time, targeting
                     `_AUTO_SCALE_TARGET`, then left alone; disable to set
                     `scale` by hand instead. Deliberately a *one-time*
                     calibration, not a continuously-adapting one: if
                     `scale` kept being recomputed from a recent/current
                     value, the display would auto-normalize toward a
                     constant target regardless of whether things are
                     actually fine or bad right now - exactly the kind of
                     change this node exists to surface, silently masked
                     by the very mechanism meant to make it visible.
                     Originally captured from a single instant (the very
                     first raw stddev) rather than a window - dropped
                     after real tank telemetry showed that instant landing
                     anywhere from the 0th to ~100th percentile of a
                     normal day's variation depending purely on luck, once
                     inflating `scale` ~2.7x and making entirely ordinary
                     readings look alarming. A 24h window was chosen
                     specifically because it's the shortest span that
                     can't be biased by *which half of the day* it starts
                     in - anything shorter (checked empirically down to 1h)
                     still swings 1.5x-3x+ depending on start time, and a
                     window that happens to land exactly on half a day is
                     *worse* than a somewhat shorter one because it always
                     captures either the day or the night half, never a
                     mix. The 90th percentile (not the mean) targets the
                     same intent as the original single-sample capture -
                     "a representative ceiling of ordinary variation", not
                     "the middle of it" - a plain mean sits at the
                     distribution's median, which would put roughly half
                     of all ordinary quiet-tank readings above the
                     `_AUTO_SCALE_TARGET` reference line, defeating the
                     point of having a stable reference at all. A
                     calibration risks only its *starting* assumption (the
                     first day happens to be representative/"sane") -
                     accepted deliberately: if it isn't, the monitored
                     signal still has to get *worse than that* to raise
                     the flag, which is a materially smaller problem than
                     an alert that can never fire because it keeps
                     rescaling itself back to "normal".
            metric  - which statistic to compute over the window:
                     'stddev' (population standard deviation, the
                     original/default) or 'variance' (population
                     variance, i.e. stddev²). Added after checking both
                     against real tank telemetry from an actual ~3h
                     flow-blockage event: variance separated that event
                     from ordinary quiet-tank noise by ~17.8x (its
                     quiet-period p90 vs. its peak during the event),
                     vs. stddev's ~4.2x - squaring punishes a large,
                     sustained excursion much harder than ordinary small
                     jitter, whereas stddev's square root partly undoes
                     that emphasis. Shares the same `scale`/`auto_scale`
                     machinery unchanged; variance's raw values are just
                     much smaller (squared units), so its calibrated
                     `scale` ends up correspondingly larger for the same
                     `_AUTO_SCALE_TARGET` - no special-casing needed.
                     Switching `metric` on a live, already-calibrated
                     node re-arms auto_scale (see the property setter) -
                     a scale tuned for stddev is meaningless for
                     variance's very different numeric range, and vice
                     versa.
    """
    data_range = DataRange.ANALOG

    _METRICS = ('stddev', 'variance')

    # the same rule of thumb folded into the 'scale' field's own label
    # (i18n/locales/*.js's stdDevScale) - see that field's docstring bullet
    _AUTO_SCALE_TARGET = 10
    # real (wall-clock) seconds to accumulate raw metric readings over
    # before freezing `scale` from their 90th percentile - see
    # auto_scale's docstring bullet for why 24h and not shorter
    _AUTO_SCALE_DURATION = 24 * 60 * 60

    def __init__(self, name: str, receives: str, samples: int = 30,
                 metric: str = 'stddev', scale: float = 1.0,
                 auto_scale: bool = False, _cont: bool = False):
        super().__init__(name, receives, _cont=_cont)
        self.samples = samples   # via the property below - always int
        # bypass the metric property setter here - see its docstring,
        # same "construction must not re-arm" reasoning as auto_scale
        self._metric: str = metric
        self.scale: float = scale
        # only ever transitions False -> True, once, for this node
        # instance's lifetime (see auto_scale's docstring). Unlike the
        # single-instant design this replaced, calibration is no longer
        # cheap (up to 24h of real time), so - unlike that design's
        # comment used to say - a process restart must NOT re-arm it:
        # __setstate__ below restores _calibrated/_calib_start/
        # _calib_samples exactly as they were, so an ordinary service
        # restart during normal operation (a deploy, an update) neither
        # throws away a completed calibration nor loses progress on one
        # still running. Only a live False->True re-toggle of auto_scale
        # (the setter below) re-arms it.
        self._calibrated: bool = False
        # wall-clock (time.time(), NOT monotonic - must survive a
        # restart's clock reset) timestamp of when the current
        # calibration attempt armed; None while auto_scale is off
        self._calib_start: float | None = time.time() if auto_scale else None
        # raw stddev readings accumulated since _calib_start; p90'd and
        # discarded once _AUTO_SCALE_DURATION elapses (_finish_calibration)
        self._calib_samples: list[float] = []
        # bypass the auto_scale property setter here - constructing/
        # restoring a node must NOT clear an already-calibrated (or
        # user-set) scale, only a live re-toggle should (see the setter)
        self._auto_scale: bool = auto_scale

    @property
    def samples(self) -> int:
        return self._samples

    @samples.setter
    def samples(self, value: int) -> None:
        # every 'number'-type Setting travels the wire as a float
        # (api.py's _validate_and_cast casts uniformly - correct for
        # 'scale', not for a count), and a live /wiring or /settings edit
        # sets this via plain setattr(), bypassing __init__/build_node()'s
        # own int() cast entirely - persisting that float and later
        # restoring it crashed deque(maxlen=<float>) in production. Coerce
        # unconditionally here instead of only at the few call sites that
        # happened to remember to.
        #
        # Also rebuild self._values at the new maxlen every time - deque
        # .maxlen is fixed at construction, so a live edit that only
        # updated self._samples left a too-small deque in place: GROWING
        # samples this way made len(self._values) >= self.samples
        # permanently unsatisfiable (the deque can never hold more than
        # its original, smaller maxlen), silently killing the node until
        # a full process restart - observed in production, VolatilityAux
        # stopped posting for 22+ hours after exactly this kind of edit.
        # deque(iterable, maxlen=N) keeps only the last N items for free,
        # correctly handling both directions (and __init__ calling this
        # before self._values exists yet, via the getattr fallback).
        new_samples = int(round(value))
        self._values = deque(getattr(self, '_values', ()), maxlen=new_samples)
        self._samples = new_samples

    @property
    def auto_scale(self) -> bool:
        return self._auto_scale

    @auto_scale.setter
    def auto_scale(self, value: bool) -> None:
        # a live re-enable (e.g. via /wiring, on an already-running node -
        # __init__ above sets self._auto_scale directly and never reaches
        # here) re-arms calibration and clears whatever scale currently
        # holds, so the dashboard doesn't keep showing a stale pre-toggle
        # value until calibration completes again
        if value and not self._auto_scale:
            self._rearm_calibration()
        self._auto_scale = value

    @property
    def metric(self) -> str:
        return self._metric

    @metric.setter
    def metric(self, value: str) -> None:
        # a live edit (e.g. via /wiring, on an already-running node -
        # __init__ above sets self._metric directly and never reaches
        # here) re-arms auto_scale exactly like re-enabling it does - a
        # scale calibrated for stddev is meaningless for variance's very
        # different numeric range (and vice versa), so keeping it would
        # silently misapply an old scale to a metric it was never tuned
        # for. Manual (non-auto_scale) scale is left alone, same as any
        # other setting change while auto_scale is off - the user is in
        # charge of it then.
        if value != self._metric and self.auto_scale:
            self._rearm_calibration()
        self._metric = value

    def _rearm_calibration(self) -> None:
        """ reset to "just armed, nothing calibrated yet" - shared by
            auto_scale's and metric's setters, see their docstrings
        """
        self._calibrated = False
        self._calib_start = time.time()
        self._calib_samples = []
        self.scale = 1.0

    def __getstate__(self) -> dict[str, Any]:
        # a standard deviation (or variance) carries its source's unit (a
        # °C signal's stddev is itself in °C, its variance in °C²) -
        # unless rescaled, in which case it's no longer literally in that
        # unit, so report '%' instead (also what routes it onto the
        # dashboard's dedicated 0-100 axis, see class docstring). Update
        # self.unit before calling super(), since BusNode.__getstate__()
        # snapshots it into the returned state (same pattern as
        # MultiInAux.__getstate__, minus data_range: that one stays
        # statically ANALOG, see class docstring)
        for rcv in self.get_receives():
            if self.scale != 1.0:
                self.unit = '%'
            else:
                self.unit = rcv.unit + '²' if self.metric == 'variance' else rcv.unit
            break
        state = super().__getstate__()
        state["samples"] = self.samples
        state["metric"] = self.metric
        state["scale"] = self.scale
        state["auto_scale"] = self.auto_scale
        # internal calibration bookkeeping, persisted (via the same
        # save_wiring()/REST-API state dict as everything else - this
        # node has no separate private-state channel) so a restart mid-
        # calibration resumes instead of restarting, see __init__'s
        # comment. calib_samples can grow to a few hundred/thousand
        # floats over the run - accepted, this is a low-traffic local
        # controller, not worth a bespoke streaming-percentile structure
        # just to shave that off.
        state["calibrated"] = self._calibrated
        state["calib_start"] = self._calib_start
        state["calib_samples"] = self._calib_samples
        # frontend-facing: /wiring and the dashboard show "still
        # calibrating..." instead of a (still meaningless) data value
        # while this is true, see comps.js's AnyNode.value(). Computed
        # here (not left to the frontend) so the frontend doesn't need
        # to know _AUTO_SCALE_DURATION - None whenever there's nothing
        # to show yet (not calibrating, or calibrating but the clock
        # hasn't started - e.g. right after loading an old pre-24h-
        # design save with no persisted calib_start, see __setstate__)
        state["calibrating"] = self.auto_scale and not self._calibrated
        state["calib_remaining_seconds"] = (
            max(0.0, self._AUTO_SCALE_DURATION - (time.time() - self._calib_start))
            if state["calibrating"] and self._calib_start is not None else None)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        # a node saved before 'samples'/'auto_scale' existed (the old
        # time-windowed 'window' Setting) has no such keys - fall back to
        # the schema defaults rather than reinterpret an old seconds
        # value as a sample count (nonsensical, e.g. "3600 samples")
        VolatilityAux.__init__(self, state['name'], state['receives'],
                           samples=state.get('samples', 30),
                           metric=state.get('metric', 'stddev'),
                           scale=state.get('scale', 1.0),
                           auto_scale=state.get('auto_scale', False),
                           _cont=True)
        # restore calibration progress exactly as it was (see __init__'s
        # comment) - overrides the fresh defaults __init__ just set
        self._calibrated = state.get('calibrated', False)
        self._calib_start = state.get('calib_start')
        self._calib_samples = list(state.get('calib_samples', []))

    def _finish_calibration(self) -> None:
        """ freeze `scale` from the 90th percentile of every raw metric
            (stddev or variance) value accumulated since auto_scale
            armed - see auto_scale's docstring bullet for why
            p90-over-24h, not mean or a shorter window.
        """
        samples = sorted(self._calib_samples)
        if len(samples) < 2:
            return  # essentially can't happen (24h at any real read
                     # interval), but don't divide by nothing if it does
        idx = 0.90 * (len(samples) - 1)
        lo = int(idx)
        hi = min(lo + 1, len(samples) - 1)
        p90 = samples[lo] + (samples[hi] - samples[lo]) * (idx - lo)
        if p90 > 0:
            self.scale = round(self._AUTO_SCALE_TARGET / p90, 4)
            self._calibrated = True
            self._calib_samples = []  # done with these, don't keep them around
            log.verbose('VolatilityAux %s: auto-calibrated scale to %f from %d samples',
                       self.id, self.scale, len(samples))
        # else: the whole window was perfectly flat (p90 == 0) - can't
        # calibrate from that, keep accumulating and retry on the next
        # reading (same reasoning as the old single-instant raw>0 guard)

    def listen(self, msg: Msg) -> None:
        if isinstance(msg, MsgData):
            self._values.append(float(msg.data))
            if len(self._values) >= self.samples:
                raw = (statistics.pvariance(self._values) if self.metric == 'variance'
                       else statistics.pstdev(self._values))
                if self.auto_scale and not self._calibrated:
                    self._calib_samples.append(raw)
                    if self._calib_start is None:
                        self._calib_start = time.time()
                    elif time.time() - self._calib_start >= self._AUTO_SCALE_DURATION:
                        self._finish_calibration()
                self.data = round(raw * self.scale, 4)
                log.verbose('VolatilityAux %s: output %f', self.id, self.data)
                self.post(MsgData(self.id, self.data))

        super().listen(msg)

    def get_settings(self) -> list[Setting]:
        settings = super().get_settings()
        schema = {s.key: s for s in type(self).get_settings_schema()}
        settings.append(self._fill_setting(schema['samples']))
        settings.append(self._fill_setting(schema['metric']))
        settings.append(self._fill_setting(schema['scale']))
        settings.append(self._fill_setting(schema['auto_scale']))
        return settings

    @classmethod
    def get_settings_schema(cls) -> list[Setting]:
        schema = super().get_settings_schema()
        schema.append(Setting('samples', 'stdDevSamples', 30, type='number', min=2))
        schema.append(Setting('metric', 'stdDevMetric', 'stddev', type='select',
                               options=list(cls._METRICS),
                               option_label_prefix='misc.stdDevMetric.'))
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
