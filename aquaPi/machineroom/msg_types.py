#!/usr/bin/env python3

from abc import ABC
import logging
from typing import Any


log = logging.getLogger('machineroom.msg_types')


class Msg(ABC):
    """ The base of all message classes, unusable by itself.
    """
    def __init__(self, sender: str):
        self.sender = sender
        self.dbg_cnt: int = 0

    def __str__(self) -> str:
        return f'{type(self).__name__}({self.sender})#{self.dbg_cnt}'


class MsgInfra(Msg, ABC):
    """ Inherit from this, to let a msg bypass filtering (node.receives)
    """


class MsgData(Msg):
    """ The workhorse on the bus: broadcast data values
        e.g. sensor data, output control, data transforms.
        Data may have any type, receiver must interpret it in
        an expectable way, close to Python truthness,
        Caveat: data='off' -> True
        Non-binary outputs should use 0=off, 100=full on (%)
    """
    def __init__(self, sender: str, data: Any):
        super().__init__(sender)
        self.data = data

    def __str__(self) -> str:
        return super().__str__() + f':{self.data}'


class MsgHello(MsgInfra):
    """ Announces a new node plugged into the bus.
        As a reaction nodes with role IN_ENDP (or with empty node.reiceives?)
        will post their data and by that update all their listeners.
        Once a node chain is complete, this will start the chain's function,
        usually processing the IN_ENDP up to the OUT_ENDP.
    """


class MsgBye(MsgInfra):
    """ Announces removal of a bus node.
        Dependant nodes can adjust their behavior.
    """


# possible further Msg types
# class MsgCommand(MsgData): # for ctrl params, in contrast to data values
