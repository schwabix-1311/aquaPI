#!/usr/bin/env python3

import logging

from .msg_bus import (BusListener, BusRole, MsgData)


log = logging.getLogger('AuxNodes')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

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
        self.values = {}

    def __getstate__(self):
        state = super().__getstate__()
        for inp in self.get_inputs(True):
            self.unit = inp.unit
            self.data_range = inp.data_range  # depends on inputs
            break
        state.update(unit=self.unit)
        return state

    # def get_settings(self):
    #     settings = super().get_settings()
    #     return settings


class AvgAux(AuxNode):
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
        self.__init__(state['name'], state['inputs'], unfair_avg=state['unfair_avg'], _cont=True)

    def listen(self, msg):
        if isinstance(msg, MsgData):
            if self.unfair_avg:
                if self.data == -1:
                    self.data = float(msg.data)
                    # log.brief('AvgAux %s: output %f', self.id, self.data)
                    self.post(MsgData(self.id, self.data))
                else:
                    val = (float(msg.data) + (self.unfair_avg - 1) * self.data) / self.unfair_avg
                    if (self.data != val):
                        self.data = val
                        # log.brief('AvgAux %s: output %f', self.id, self.data)
                        self.post(MsgData(self.id, round(self.data, 4)))
            else:
                if self.values.get(msg.sender) != float(msg.data):
                    self.values[msg.sender] = float(msg.data)
                val = 0
                for k in self.values:
                    val += self.values[k] / len(self.values)
                if (self.data != val):
                    self.data = val
                    # log.brief('AvgAux %s: output %f', self.id, self.data)
                    self.post(MsgData(self.id, round(self.data, 4)))
        return super().listen(msg)

    def get_settings(self):
        settings = super().get_settings()
        settings.append(('unfair_avg', 'Unweighted avg.', self.unfair_avg, 'type="number" min="0" step="1"'))
        return settings


class MaxAux(AuxNode):
    """ Auxiliary node to post the higher of two or more inputs.
        Can be used to let two controllers drive one output, or to have
        redundant inputs.

        Options:
            name    - unique name of this auxiliary node in UI
            inputs  - collection of input ids

        Output:
            float - posts changes of maximum value of all inputs
    """
    # def __getstate__(self):
    #     state = super().__getstate__()
    #     return state

    # def __setstate__(self, state):
    #     self.data = state['data']
    #     self.__init__(state, _cont=True)

    def listen(self, msg):
        if isinstance(msg, MsgData):
            if self.values.get(msg.sender) != float(msg.data):
                self.values[msg.sender] = float(msg.data)
            val = -1  # 0
            for k in self.values:
                val = max(val, self.values[k])
            val = round(val, 4)
            if self.data != val:
                self.data = val
                # log.brief('MaxAux %s: output %f', self.id, self.data)
                self.post(MsgData(self.id, self.data))
        return super().listen(msg)
