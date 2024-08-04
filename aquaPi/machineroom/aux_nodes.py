#!/usr/bin/env python3

import logging

from .msg_bus import (BusListener, BusRole, DataRange, MsgData)


log = logging.getLogger('AuxNodes')
log.brief = log.warning  # alias, warning used as brief info, info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


# ========== auxiliary ==========


class AuxNode(BusListener):
    """ Auxiliary nodes are for advanced configurations where
        direct connections of input to controller or controller to
        output aren't sufficient.
    """
    ROLE = BusRole.AUX

    def __init__(self, name, inputs, _cont=False):
        super().__init__(name, inputs, _cont=_cont)
        self.data = -1


class ScaleAux(AuxNode):
    """ A 1:1 node rescaling via a graph defined by
        offset and factor, or by 2 points.
        Useful for calibrations of linear (!) sensors.
        And quite a few other creative use cases ...

        Options:
            offset - a simple offset:  in + offset = out
            factor - a scaling factor: in * factor = out
            points - alternate way to define offset and factor
                      by 2 points as [(in1 out1),(in2 out2)]
            limit  - if tupel, limit out to this range,
                     else if true-ish, limit to 0..100
    """
    data_range = DataRange.ANALOG

    def __init__(self, name, inputs, unit,
                 offset=0, factor=1.0, points=None,
                 limit=None,
                 _cont=False):
        super().__init__(name, inputs, _cont=_cont)
        self.unit = unit
        try:
            dX = points[1][0] - points[0][0]
            dY = points[1][1] - points[0][1]
            self.factor = dY / dX
            self.offset = points[0][1] - self.factor * points[0][0]
        except TypeError:
            log.info('No valid calibration points found')
            self.offset = offset
            self.factor = factor

        if limit:
            try:
                self.limit = (limit[0], limit[1])
            except (TypeError, IndexError):
                self.limit = (0, 100)
        else:
            self.limit = None

        log.info('ScaleAux %s: factor %f, offset %f, limiting %s',
                 name, self.factor, self.offset, str(self.limit))

    def __getstate__(self):
        state = super().__getstate__()
        state.update(unit=self.unit)
        state.update(offset=self.offset)
        state.update(factor=self.factor)
        state.update(limit=self.limit)
        return state

    def __setstate__(self, state):
        self.data = state['data']
        self.__init__(state['name'], state['inputs'], unit=state['unit'],
                      offset=state['offset'], factor=state['factor'],
                      limit=state['limit'],
                      _cont=True)

    def listen(self, msg):
        if isinstance(msg, MsgData):
            self.data = self.factor * float(msg.data) + self.offset
            if self.limit:
                self.data = min(max( self.limit[0], self.data), self.limit[1])
            log.info('ScaleAux %s: output %f', self.id, self.data)
            self.post(MsgData(self.id, self.data))
        return super().listen(msg)

    def get_settings(self):
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


class MultiInAux(AuxNode):
    """ subtype of AuxNodes listening to more than 1 input
    """

    def __init__(self, name, inputs, _cont=False):
        super().__init__(name, inputs, _cont=_cont)
        self.values = {}

    def __getstate__(self):
        state = super().__getstate__()
        for inp in self.get_inputs():
            self.unit = inp.unit
            self.data_range = inp.data_range  # depends on inputs
            break
        state.update(unit=self.unit)
        return state


class AvgAux(MultiInAux):
    """ Auxiliary node to build average of 2 or more inputs.
        Weighting can be fair - every sender's latest input accounts once -
        or unfair - the most active sender contributes most and dead inputs
        loose their influence on result quickly.
        For redundancy, unfair may be the better option.

        Options:
            name       - unique name of this auxiliar node in UI
            inputs     - collection of input ids
            unfair_avg - 0 = equally weights all inputs
                         >0 = moving average of received input values,
                              higher frequency increases weight

        Output:
            float - posts changes of arithmetic average of inputs
    """

    def __init__(self, name, inputs, unfair_avg=0, _cont=False):
        super().__init__(name, inputs, _cont=_cont)
        self.unfair_avg = 0 or int(unfair_avg)

    def __getstate__(self):
        state = super().__getstate__()
        state.update(unfair_avg=self.unfair_avg)
        return state

    def __setstate__(self, state):
        self.data = state['data']
        self.__init__(state['name'], state['inputs'],
                      unfair_avg=state['unfair_avg'], _cont=True)

    def listen(self, msg):
        if isinstance(msg, MsgData):
            if self.unfair_avg:
                if self.data == -1:
                    val = float(msg.data)
                else:
                    # unfair_avg-1 is the amount (count) of old data to keep
                    old_data = self.data * (self.unfair_avg - 1)
                    val = (float(msg.data) + old_data) / self.unfair_avg
            else:
                if self.values.get(msg.sender) != float(msg.data):
                    self.values[msg.sender] = float(msg.data)
                val = 0
                for k in self.values:
                    val += self.values[k] / len(self.values)

            if (self.data != val):
                self.data = val
                log.info('AvgAux %s: output %f', self.id, self.data)
                self.post(MsgData(self.id, round(self.data, 4)))
        return super().listen(msg)

    def get_settings(self):
        settings = super().get_settings()
        settings.append(('unfair_avg', 'Unweighted avg.',
                         self.unfair_avg, 'type="number" min="0" step="1"'))
        return settings


class MinAux(MultiInAux):
    """ Auxiliary node to post the lower of two or more inputs = boolenan AND.
        Can be used to let two controllers drive one output, or to have
        redundant inputs.

        Options:
            name    - unique name of this auxiliary node in UI
            inputs  - collection of input ids

        Output:
            float - posts changes of minimum value of all inputs
    """

    def listen(self, msg):
        if isinstance(msg, MsgData):
            if self.values.get(msg.sender) != float(msg.data):
                self.values[msg.sender] = float(msg.data)
            val = 100
            for k in self.values:
                val = min(val, self.values[k])
            val = round(val, 4)
            if self.data != val:
                self.data = val
##              log.info('MinAux %s: output %f', self.id, self.data)
                self.post(MsgData(self.id, self.data))
        return super().listen(msg)


class MaxAux(MultiInAux):
    """ Auxiliary node to post the higher of two or more inputs = boolean OR.
        Can be used to let two controllers drive one output, or to have
        redundant inputs.

        Options:
            name    - unique name of this auxiliary node in UI
            inputs  - collection of input ids

        Output:
            float - posts changes of maximum value of all inputs
    """

    def listen(self, msg):
        if isinstance(msg, MsgData):
            if self.values.get(msg.sender) != float(msg.data):
                self.values[msg.sender] = float(msg.data)
            val = 0
            for k in self.values:
                val = max(val, self.values[k])
            val = round(val, 4)
            if self.data != val:
                self.data = val
                log.info('MaxAux %s: output %f', self.id, self.data)
                self.post(MsgData(self.id, self.data))
        return super().listen(msg)
