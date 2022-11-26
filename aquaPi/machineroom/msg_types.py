#!/usr/bin/env python3

import logging


log = logging.getLogger('MsgBusMsgs')
log.setLevel(logging.WARNING)  # INFO)


class Msg:
    """ The base of all message classes, unusable by itself.
    """
    def __init__(self, sender):
        self.sender = sender
        self.dbg_cnt = 0

    def __str__(self):
        return '{}({})#{}'.format(type(self).__name__, self.sender, self.dbg_cnt)

# payload messages


class MsgPayload(Msg):
    """ Base class for custom BusNode communication,
        e.g. sensor data, output control, message transformers.
        Payloads may have any data, it is the receiver's task to interpret it.
    """
    def __init__(self, sender, data):
        Msg.__init__(self, sender)
        self.data = data

    def __str__(self):
        return '{}({})#{}:{}'.format(type(self).__name__, self.sender, self.dbg_cnt, self.data)


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
# class MsgCommand(MsgPayload): # for ctrl parameters, in contrast to data values
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
    def __init__(self, sender, send_to):
        Msg.__init__(self, sender)
        self.send_to = send_to

    def __str__(self):
        return Msg.__str__(self) + '->' + self.send_to


class MsgReplyHello(MsgReply, MsgInfra):
    """ Reply from plugged-in nodes to MsgBorn.
        Used to let new nodes see who's present.
    """


#############################


class MsgFilter:
    """ MsgFilter is used to select messages received
        by BusListener via a list of sender names.
        Empty list (actually an array) means no filtering.
        sender_list may be None=all, a string or a list of strings.
    """
    # TODO add filtering by other attributes (group, category, sender role/type)
    def __init__(self, sender):
        if isinstance(sender, str):
            self.sender = [sender]
        else:
            self.sender = sender

    def __str__(self):
        return '{}({})'.format(type(self).__name__, ','.join(self.sender))

    def filter(self, msg):
        if not self.sender:
            log.warning('%s has empty sender list, msg %s', str(), str(msg))
        if (self.sender == ['*']) or (msg.sender in self.sender):
            # TODO add categories and/or groups
            return True
        return False
