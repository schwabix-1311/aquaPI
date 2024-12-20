#!/usr/bin/env python3

from abc import ABC
import logging
from typing import (Iterable, Any)

from .msg_types import (Msg, MsgData)
from .msg_bus import (BusListener, BusRole, DataRange)


log = logging.getLogger('machineroom.aux_nodes')
log.brief = log.warning  # alias, warning used as brief info, info is verbose


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
    def __init__(self, name: str, receives: Iterable[str], _cont: bool = False):
        super().__init__(name, receives, _cont=_cont)
        self.values: dict[str, float] = {}

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        for rcv in self.get_receives():
            self.unit = rcv.unit
            self.data_range = rcv.data_range  # depends on inputs
            break
        state.update(unit=self.unit)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        MultiInAux.__init__(self, state['name'], state['receives'],
                            _cont=True)


# ========== auxiliary ==========


class ScaleAux(SingleInAux):
    """ A 1:1 node rescaling via a graph defined by
        offset and factor, or by 2 points.
        Useful for calibrations of linear (!) sensors.
        And quite a few other creative use cases ...

        Options:
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

        log.info('ScaleAux %s: factor %f, offset %f, limiting %s',
                 name, self.factor, self.offset, str(self.limit))

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state.update(unit=self.unit)
        state.update(offset=self.offset)
        state.update(factor=self.factor)
        state.update(limit=self.limit)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        ScaleAux.__init__(self, state['name'], state['receives'], unit=state['unit'],
                          offset=state['offset'], factor=state['factor'],
                          limit=state['limit'],
                          _cont=True)

    def listen(self, msg: Msg) -> bool:
        if isinstance(msg, MsgData):
            self.data = self.factor * float(msg.data) + self.offset
            self.data = min(max(self.limit[0], self.data), self.limit[1])
            log.info('ScaleAux %s: output %f', self.id, self.data)
            self.post(MsgData(self.id, self.data))
        return super().listen(msg)

    def get_settings(self) -> list[tuple]:
        settings = super().get_settings()
        settings.append(('unit', 'Einheit',
                         self.unit, 'type="text"'))
        # TODO frontend should also offer 2-point calibration, this is most practical for pH
        settings.append(('offset', 'Offset', round(self.offset, 4),
                         'type="number" step="0.0001"'))
        settings.append(('factor', 'Skalierfaktor', round(self.factor, 4),
                         'type="number" step="0.0001"'))
        # settings.append(('limit', 'Grenzen', self.limit,
        #                  'type="combo"'))  #  None/0..100/(min,max)
        return settings


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
        self.unfair_avg: int = 0 or int(unfair_avg)

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state.update(unfair_avg=self.unfair_avg)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        AvgAux.__init__(self, state['name'], state['receives'],
                        unfair_avg=state['unfair_avg'], _cont=True)

    def listen(self, msg: Msg) -> bool:
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

            val = round(val, 4)
            if True or (self.data != val):  #FIXME
                self.data = val
                log.info('AvgAux %s: output %f', self.id, self.data)
                self.post(MsgData(self.id, round(self.data, 4)))
        return super().listen(msg)

    def get_settings(self) -> list[tuple]:
        settings = super().get_settings()
        settings.append(('unfair_avg', 'Unweighted avg.',
                         self.unfair_avg, 'type="number" min="0" step="1"'))
        return settings


class MinAux(MultiInAux):
    """ Auxiliary node to post the lower of two or more inputs = boolenan AND.
        Can be used to let two controllers drive one output, or to have
        redundant inputs.

        Options:
            name     - unique name of this auxiliary node in UI
            receives - collection of input ids

        Output:
            float - posts changes of minimum value of all inputs
    """

    def listen(self, msg: Msg) -> bool:
        if isinstance(msg, MsgData):
            val = float(msg.data)
            self.values[msg.sender] = val
            for v in self.values.values():
                val = min(val, v)
            val = round(val, 4)
            if True or (self.data != val):  #FIXME
                self.data = val
##                log.info('MinAux %s: output %f', self.id, self.data)
                self.post(MsgData(self.id, self.data))
        return super().listen(msg)


class MaxAux(MultiInAux):
    """ Auxiliary node to post the higher of two or more inputs = boolean OR.
        Can be used to let two controllers drive one output, or to have
        redundant inputs.

        Options:
            name     - unique name of this auxiliary node in UI
            receives - collection of input ids

        Output:
            float - posts changes of maximum value of all inputs
    """

    def listen(self, msg: Msg) -> bool:
        if isinstance(msg, MsgData):
            val = float(msg.data)
            self.values[msg.sender] = val
            for v in self.values.values():
                val = max(val, v)
            val = round(val, 4)
            if True or (self.data != val):  #FIXME
                self.data = val
                log.info('MaxAux %s: output %f', self.id, self.data)
                self.post(MsgData(self.id, self.data))
        return super().listen(msg)
