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
        return '{}({})#{}'.format(type(self).__name__,
                                  self.sender,
                                  self.dbg_cnt)


# payload messages

class MsgPayload(Msg):
    """ Base class for custom BusNode communication,
        e.g. sensor data, output control, message transformers.
        Payloads may have any data, it is the receiver's task to interpret it.
    """
    def __init__(self, sender: str, data: Any):
        super().__init__(sender)
        self.data = data

    def __str__(self) -> str:
        return '{}({})#{}:{}'.format(type(self).__name__,
                                     self.sender,
                                     self.dbg_cnt,
                                     self.data)


class MsgData(MsgPayload):
    """ Transport for data items
        Output of sensors and input for relays.
        All using same type allows to chain BusListeners
        Data can have any type, receiver must interpret it in
        an expectable way, close to Python truthness,
        Caveat: data='off' -> True
        Non-binary outputs should use 0=off, 100=full on (%)
    """


# TODO further Msg types
# class MsgCommand(MsgPayload): # for ctrl params, in contrast to data values
# class MsgLog(MsgPayload):  # needed? anything should be loggable -> MsgData
# class MsgWarning(MsgPayload):
# class MsgError(MsgPayload):


# infrastructure messages

class MsgInfra(Msg):
    """ Base for basic protocol msgs, may not be filtered
    """


class MsgBorn(MsgInfra, MsgPayload):
    """ Announces a new node plugged into the bus and
        make initial data known to others.
        All nodes return a MsgReplyHello to show their presence.
        Can be used to adjust MsgFilter.
    """


class MsgBye(MsgInfra):
    """ Announces removal of a bus node.
        Dependant nodes can adjust their behavior.
    """


# reply messages

class MsgReply(Msg):
    """ Base class for all reply messages, usually 1:1.
    """
    def __init__(self, sender: str, send_to: str):
        super().__init__(sender)
        self.send_to = send_to

    def __str__(self):
        return Msg.__str__(self) + '->' + self.send_to


class MsgReplyHello(MsgReply, MsgInfra):
    """ Reply from plugged-in nodes to MsgBorn.
        Used to let new nodes see who's present.
    """
