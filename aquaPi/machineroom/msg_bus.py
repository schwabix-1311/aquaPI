#!/usr/bin/env python3

import logging
import time
from queue import Queue
from enum import Flag, auto
from threading import Condition, Event, Lock, Thread

from .msg_types import *


log = logging.getLogger('MsgBus')
log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose


class BusRole(Flag):
    IN_ENDP = auto()    # data sources: sensor, switch, schedule
    OUT_ENDP = auto()   # output: relais, logs, mails
    CTRL = auto()       # the core of a controller: process IN -> OUT
    AUX = auto()        # helper func: 2:1/n:1, e.g. avg, delay, or

# This may help to fill selection lists/combos with the appropriate node types
# class PayloadType
    # TUPEL = auto()      # operates on data tupels, e.g. RGB light
    # ANALOG = auto()     # the receiver interprets MsgData according to his capabilites
    # BINARY = auto()     # interprets MsgData in a binary way (on/off)

#############################


class MsgBus:
    """ Communication channel between all registered
        BusNodes.
        Supports public and 1:1 messaging, plugin/pullout
        notification and message filtering for each listener.
        Msg dispatcher can run as blocking loop of post()
        or in a worker thread. Unthreaded is much faster
        and easier to debug, thus the default.
        Several get_* methods build the interface to Flask backend
    """
    def __init__(self, threaded=False):
        self._threaded = threaded
        self.nodes = []
        self._changes = set()
        self._changed = Condition()
        self._m_cnt = 0
        self._queue = None
        if threaded:
            self._queue = Queue(maxsize=10)
            Thread(target=self._dispatch, daemon=True).start()

    def __getstate__(self):
        state = {'nodes': self.nodes, 'threaded': self._threaded}
        log.debug('MsgBus.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('MsgBus.setstate %r', state)
        self.__init__(state['threaded'])
        for n in state['nodes']:
            n.plugin(self)

    def __str__(self):
        if not self._queue:
            return '{}({} nodes)'.format(type(self).__name__, len(self.nodes))
        return '{}({} nodes, {} queue\'d)'.format(type(self).__name__, len(self.nodes), self._queue.qsize())

    def _register(self, node):
        """ Add a BusNode to the bus.
            Raise exception if duplicate id.
        """
        lst = self.get_node(node.id)  # this rejects ambiguities in id or name
        if lst:
            raise Exception('Duplicate node: name ' + node.name + ', id ' + node.id)

        if self._queue:
            # empty the queue before nodes change
            self._queue.join()
        self.nodes.append(node)

    def _unregister(self, node):
        """ Remove BusNode from bus.
        """
        node = self.get_node(id)
        if node:
            if self._queue:
                # empty the queue before nodes change
                self._queue.join()
            self.nodes.remove(node)

    def post(self, msg):
        """ Put message into the queue or dispatch in a
            blocking loop.
            Descendants of MsgReply contain the id of
            receiver (send_to) for 1:1 communication.
            This might change too to a send_to parameter.
        """
        self._m_cnt += 1
        msg._m_cnt = self._m_cnt
        log.debug('%s   + %s', str(self), str(msg))
        if self._queue:
            self._queue.put(msg, block=True, timeout=5)
        else:
            self._dispatch_one(msg)

    def _dispatch(self):
        """ Dispatch all queued messages in a worker thread
        """
        while True:
            msg = self._queue.get()
            self._dispatch_one(msg)
            self._queue.task_done()

    def _dispatch_one(self, msg):
        """ Dispatch one message to all listeners in a blocking loop.
        """
        # FIXME report before or after dispatching? this might be too early, try at very end,
        if isinstance(msg, (MsgData, MsgBorn)):
            log.debug('  notify the change event about %s', str(msg))
            self.report_change(msg.sender)

        # dispatch the message
        log.debug('%s ->', str(msg))
        if isinstance(msg, MsgReply):
            # directed message sender -> receiver
            lst = [n for n in self.nodes if n.id == msg.send_to]
        else:
            # broadcast message, exclude sender
            lst = [n for n in self.nodes if n.id != msg.sender]
            # ... and apply each node's filter for non-Infra msgs
            if not isinstance(msg, MsgInfra):
                lst = [n for n in lst if n._inputs and n._inputs.filter(msg)]
        for n in lst:
            log.debug('  -> %s', str(n))
            n.listen(msg)

    def teardown(self):
        """ Prepare for shutdown, e.g. unplug all.
        """
        for n in self.nodes:
            log.debug('teardown %s', str(n))
            n.pullout()

    def get_node(self, id_or_name):
        """ Find BusNode by id or name.
            id is derived from name, and both are unique.
        """
        lst = [n for n in self.nodes if id_or_name in (n.id, n.name)]
        return lst[0] if len(lst) == 1 else None

    # former BusBroker functions, i.e. the interface for Flask backend

    def get_nodes(self, roles=None):
        """ return list of current nodes: { id:BusNode, ... }
            filtered by set of roles, or all
        """
        return [n for n in self.nodes if not roles or n.ROLE in roles]

    def get_controller_nodes(self):
        """ return list of controller nodes: { id:BusNode, ... }
            Jinja code has no access to BusRoles -> specialized get_nodes
        """
        return self.get_nodes(roles=BusRole.CTRL)

    def get_input_nodes(self):
        """ return list of input nodes: { id:BusNode, ... }
            Jinja code has no access to BusRoles -> specialized get_nodes
        """
        return self.get_nodes(roles=BusRole.IN_ENDP)

    def get_output_nodes(self):
        """ return list of output nodes: { id:BusNode, ... }
            Jinja code has no access to BusRoles -> specialized get_nodes
        """
        return self.get_nodes(roles=BusRole.OUT_ENDP)

    def get_auxiliary_nodes(self):
        """ return list of auxiliary nodes: { id:BusNode, ... }
            Jinja code has no access to BusRoles -> specialized get_nodes
        """
        return self.get_nodes(roles=BusRole.AUX)

    @staticmethod
    def to_names(node_list):
        """ return a list of names from whatever iterable container with nodes
        """
        return [node.name for node in node_list]

    def report_change(self, node_id):
        """ add ID to list of changed nodes and notify one (!) waiting thread
        """
        log.debug('report_change locked: ' + node_id)
        with self._changed:
            self._changes.add(node_id)
            self._changed.notify()
            log.debug('report_change notified & done: ' + node_id)
            time.sleep(.01)  # this is a hack, I don't find the race cond.

    def wait_for_changes(self):
        """ block until at least one node reported data changes,
            then clear the internal list of changes
            return ids of modified nodes [id1, id2, ...]
        """
        log.debug('wait_for_changes')
        with self._changed:
            self._changed.wait_for(lambda :len(self._changes))
            change = [id for id in self._changes]
            self._changes.clear()
            log.debug('cleared change_list: %r' % change)
        return change


#############################

class BusNode:
    """ BusNode is a minimal bus participant
        It has little overhead, can only post messages.
        Methods plugin/pullout can be redirected to a callback to
        let you know when to start or finish your task.
        Bus callback:
          bus_cbk(self: BusNode, bus|None: MsgBus) : None
        The bus protocol (MsgBorn/MsgBye/MsgReplyHello)
        is handled internally.
        The _inputs should always be None = listen to everbody!
    """
    ROLE = None

    def __init__(self, name, unit='', bus_cbk=None):
        self.name = name
        self.id = name.lower()  # uuid.uuid4(uuid.NAMSPACE_OID,name)
        self.id = self.id.replace(' ', '').replace('.', '').replace(';', '').replace('-','_')
        self.id = self.id.replace('ä', 'ae').replace('ö', 'oe').replace('ü','ue')
        self.id = self.id.replace('Ä', 'Ae').replace('Ö', 'Oe').replace('Ü','Ue')
        self.id = self.id.replace('-','_').replace('ß', 'ss')
        # this is a bit of abuse: replace all non-ASCII with xml refs, then back to utf-8
        self.id = str(self.id.encode('ascii', 'xmlcharrefreplace'), errors='strict')
        log.debug(self.id)

        self._inputs = None
        self._bus = None
        self.data = 0
        self.unit = unit
        self._bus_cbk = bus_cbk
        self._msg_cbk = None

    def __getstate__(self):
        state = {'name': self.name, 'inputs': self._inputs, 'data': self.data}
        log.debug('< BusNode.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('BusNode.setstate %r', state)
        self.__init__(state['name'])
        self.data = state['data']

    def __str__(self):
        snd = self._inputs.sender if self._inputs else []
        return '{}({})'.format(type(self).__name__, ','.join(snd))

    def plugin(self, bus):
        if self._bus:
            self._bus._unregister(self)
            self._bus = None
        bus._register(self)
        self._bus = bus
        if self._bus_cbk:
            self._bus_cbk(self, self._bus)
        self.post(MsgBorn(self.id, self.data))
        log.info('%s plugged, role %s', str(self), str(self.ROLE))

    def pullout(self):
        if not self._bus:
            return False
        if self._bus_cbk:
            self._bus_cbk(self, None)
        self.post(MsgBye(self.id))
        self._bus._unregister(self)
        self._bus = None
        log.info('%s pulled', str(self))
        return True

    def post(self, msg):
        if self._bus:
            self._bus.post(msg)

    def listen(self, msg):
        # standard reactions for unhandled messages
        log.debug('%s.listen %s', str(self), str(msg))
        if isinstance(msg, MsgBorn):
            self.post(MsgReplyHello(self.id, msg.sender))
            return True
        return False

    def get_inputs(self, recurse=False):
        inputs = []
        if self._bus and self._inputs:
            inputs = [self._bus.get_node(snd) for snd in self._inputs.sender]
            if recurse:
                for s_node in inputs:
                    inputs = s_node.get_inputs(recurse) + inputs 
        return inputs  # if self._inputs else ['-']

    def get_outputs(self, recurse=False):
        outputs = []
        if self._bus:
            for node in self._bus.nodes:
                if node._inputs and self.id in node._inputs.sender:
                    outputs.append(node)
                    if recurse:
                        s_node = self._bus.get_node(node.id)
                        if s_node:
                            outputs = outputs + s_node.get_outputs(recurse)
        return outputs  # if outputs else ['-']

    def get_renderdata(self):
        ret = {'pretty_data': '%.2f%s' % (self.data, self.unit)}
        return ret

    def get_settings(self):
        return []


class BusListener(BusNode):
    """ BusListener is an extension to BusNode.
        Listeners usually filter the messages they listen to.
        Bus protocol is handled internally.
        All (!) messages can be redirected to message callback,
        which returns True, for handled messages, False otherwise.
        message callback:
          message_cbk(self: BusListener, msg: Msg) : bool
        Listening to MsgBorn/MsgBye allows to adjust MsgFilters.
        A derived class must call BusListener.listen() to keep
        protocol intact!
    """
    def __init__(self, name, inputs=None, msg_cbk=None, bus_cbk=None):
        super().__init__(name, bus_cbk)
        if inputs:
            if not isinstance(inputs, MsgFilter):
                inputs = MsgFilter(inputs)
        else:
            inputs = MsgFilter('*')
        self._inputs = inputs
        self._msg_cbk = msg_cbk

    def __getstate__(self):
        state = super().__getstate__()
        state.update(inputs=self._inputs)
        log.debug('< BusListener.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('BusListener.setstate %r', state)
        self.__init__(state['name'], inputs=state['inputs'])

    def listen(self, msg):
        ret = False
        if self._msg_cbk:
            log.debug('%s._msg_cbk got %s', str(self), str(msg))
            ret = self._msg_cbk(self, msg)
        if not ret:
            log.debug('%s.listen got %s', str(self), str(msg))
            ret = BusNode.listen(self, msg)
        return ret

    def get_settings(self):
        settings = super().get_settings()
        settings.append((None, 'Inputs', ';'.join(MsgBus.to_names(self.get_inputs())), 'type="text"'))
        return settings


#############################

''' samples of low-level nodes using callbacks
    TODO: unclear whether callbacks will be used finally, for now keep 'em
          Currently all higher level nodes derive from BusNodes,
          derived classes overload methods and thus don't need callbacks
'''

t_avg = None


def temp_avg(self, msg):
    global t_avg
    if isinstance(msg, MsgData):
        if not t_avg:
            t_avg = msg.data
        else:
            print(str(msg))
            t_new = round((t_avg + msg.data) / 2, 2)
            if t_new != t_avg:
                t_avg = t_new
                # print(str(self) + ' = ' + str(t_avg))
                self.post(MsgData(self.id, t_avg))
        return True
    return False


def minThreshold(self, msg):
    if isinstance(msg, MsgData):
        # print(str(self) + ' got ' + str(msg))
        if msg.data < 25:
            self.post(MsgData(self.id, True))
        else:
            self.post(MsgData(self.id, False))


relais_state = False


def relais(self, msg):
    global relais_state
    if isinstance(msg, MsgData):
        # print('{} = {}'.format(msg.sender,msg.data))
        if msg.data != relais_state:
            # print('{} switching {}'.format(self.id,{True:'ON',False:'off'}[msg.data]))
            relais_state = msg.data
        return True
    return False


#############################

''' kind of unit tests and sample usage
'''

if __name__ == "__main__":

    import time
    import random

    mb = MsgBus()
    # mb = MsgBus(threaded=True)

    # these are primitive BusNodes, they are implemented as message callbacks of the basic types

    sensor1 = BusNode('TempSensor1')
    sensor1.plugin(mb)
    sensor2 = BusNode('TempSensor2')
    sensor2.plugin(mb)

    avg = BusListener('TempSensor', msg_cbk=temp_avg)
    avg.plugin(mb)

    temp_ctrl = BusListener('TempController', msg_cbk=minThreshold, inputs=MsgFilter(['TempSensor']))
    temp_ctrl.plugin(mb)

    relais = BusListener('TempRelais', msg_cbk=relais, inputs=[temp_ctrl.id])
    relais.plugin(mb)

    # mb.register(BusListener('BL3'))

    # for d in [42, 24.83, 'LOW', [1,2,3]]:
    for d in range(100):
        sensor1.post(MsgData(sensor1.id, round(random.random() * 3 + 23.5, 2)))
        if d % 3:
            sensor2.post(MsgData(sensor2.id, round(random.random() * 3 + 23.5, 2)))
        # time.sleep(.1)

    mb.teardown()
