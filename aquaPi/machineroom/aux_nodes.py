#!/usr/bin/env python3

from abc import ABC
import logging
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
    """ A 1:1 node rescaling via a graph defined by
        offset and factor, or by 2 points.
        Useful for calibrations of linear (!) sensors.
        And quite a few other creative use cases ...

        Options:
            unit   - the unit after scaling the received data
            offset - a simple offset:  in + offset = out
            factor - a scaling factor: in * factor = out
            points - alternate way to define offset and factor
                      by 2 points as [(in1 out1),(in2 out2)]
            limit  - limit result to this range,
                     defaults to 0.0 .. 100.0
    """
    data_range = DataRange.ANALOG

    def __init__(self, name: str, receives: str, unit: str,
                 offset: float = 0, factor: float = 1.0,
                 points: list[tuple[float, float]] | None = None,
                 limit: tuple[float, float] = (0.0, 100.0),
                 _cont: bool = False):
        super().__init__(name, receives, _cont=_cont)
        self.unit: str = unit
        self.offset: float = offset
        self.factor: float = factor
        if points:
            try:
                dX = points[1][0] - points[0][0]
                dY = points[1][1] - points[0][1]
                self.factor = dY / dX
                self.offset = points[0][1] - self.factor * points[0][0]
            except (TypeError, IndexError):
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
        state["offset"] = self.offset
        state["factor"] = self.factor
        state["limit"] = self.limit
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        ScaleAux.__init__(self, state['name'], state['receives'], unit=state['unit'],
                          offset=state['offset'], factor=state['factor'],
                          limit=state['limit'],
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
        # TODO frontend should also offer 2-point calibration, this is most practical for pH
        settings.append(schema['offset'].with_value(round(self.offset, 4)))
        settings.append(schema['factor'].with_value(round(self.factor, 4)))
        # settings.append(Setting('limit', 'Grenzen', self.limit,
        #                         type='combo'))  #  None/0..100/(min,max)
        return settings

    @classmethod
    def get_settings_schema(cls) -> list[Setting]:
        schema = super().get_settings_schema()
        schema.append(Setting('unit', 'unit', ''))
        schema.append(Setting('offset', 'offset', 0.0, type='number', step=0.0001))
        schema.append(Setting('factor', 'scaleFactor', 1.0, type='number', step=0.0001))
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
