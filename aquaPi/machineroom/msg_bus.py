#!/usr/bin/env python

import logging
from queue import Queue
from enum import Flag, auto
from threading import Thread, Event

from .msg_types import *


log = logging.getLogger('MsgBus')
log.setLevel(logging.INFO) #WARNING)  # INFO)
#log.setLevel(logging.DEBUG)


class BusRole(Flag):
    IN_ENDP = auto()    # data sources: sensor, switch, schedule
    OUT_ENDP = auto()   # output: relais, logs, mails
    CTRL = auto() # the core of a controller: process IN -> OUT
    AUX = auto()        # helper func: 2:1/n:1, e.g. avg, delay, or
    BROKER = auto()     # listens to everything to provide current state

# This may help to fill selection lists/combos with the appropriate node types
#class PayloadType
    #TUPEL = auto()      # operates on data tupels, e.g. RGB light
    #ANALOG = auto()     # the receiver interprets MsgData according to his capabilites
    #BINARY = auto()     # interprets MsgData in a binary way (on/off)

#############################

class MsgBus:
    ''' Communication channel between all registered
        BusNodes.
        Supports public and 1:1 messaging, plugin/pullout
        notification and message filtering for each listener.
        Msg dispatcher can run as blocking loop of post()
        or in a worker thread. Unthreaded is much faster
        and easier to debug, thus the default.
    '''
    def __init__(self, threaded=False):
        self.nodes = []
        self._m_cnt = 0
        self._queue = None
        if threaded:
            self._queue = Queue(maxsize=10)  # or collections.deque?
            Thread(target=self._dispatch, daemon=True).start()

    def __str__(self):
        if not self._queue:
            return '{}({} nodes)'.format(type(self).__name__, len(self.nodes))
        return '{}({} nodes, {} queue\'d)'.format(type(self).__name__, len(self.nodes), self._queue.qsize())

    def get_node(self, name):
        ''' Find BusNode by its name.
        '''
        lst = [m for m in self.nodes if m.name == name]
        return lst[0] if lst else None

    def _register(self, node):
        ''' Add a BusNode to the bus.
            Return False if duplicate name.
        '''
        lst = self.get_node(node.name)
        if lst:
            return False

        if self._queue:
            # empty the queue before nodes change
            self._queue.join()
        self.nodes.append(node)
        return True

    def _unregister(self, name):
        ''' Remove BusNode from bus.
        '''
        node = self.get_node(name)
        if node:
            if self._queue:
                # empty the queue before nodess change
                self._queue.join()
            self.nodes.remove(node)

    def post(self, msg):
        ''' Put message into the queue or dispatch in a
            blocking loop.
            Descentants of MsgReply containy the name of
            receiver (send_to) for 1:1 communication.
            This might change too to a send_to parameter.
        '''
        self._m_cnt += 1
        msg._m_cnt = self._m_cnt
        log.debug('%s   + %s', str(self), str(msg))
        if self._queue:
            self._queue.put(msg, block=True, timeout=5)
        else:
            self._dispatch_one(msg)

    def _dispatch(self):
        ''' Dispatch all queued messages in a worker thread
        '''
        while True:
            msg = self._queue.get()
            self._dispatch_one(msg)
            self._queue.task_done()

    def _dispatch_one(self, msg):
        ''' Dispatch one message to all listeners in a blocking loop.
        '''
        log.debug('%s ->', str(msg))
        if isinstance(msg, MsgReply):
            # directed message sender -> receiver
            lst = [l for l in self.nodes if l.name == msg.send_to]
        else:
            # broadcast message, exclude sender
            lst = [l for l in self.nodes if l.name != msg.sender]
        if not isinstance(msg, MsgInfra):
            #lst = [l for l in lst if isinstance(l, BusListener)]
            lst = [l for l in lst if l.filter and l.filter.apply(msg)]
        for l in lst:
            log.debug('  -> %s', str(l))
            l.listen(msg)

    def teardown(self):
        ''' Prepare for shutdown, e.g. unplug all.
        '''
        for lst in [l for l in self.nodes]:
            log.debug('teardown %s', str(lst))
            lst.pullout()

#############################

class BusNode:
    ''' BusNode is a minimal bus participant
        It has little overhead, can only post messages.
        Methods plugin/pullout can be redirected to a callback to
        let you know when to start or finish your task.
        Bus callback:
          bus_cbk(self: BusNode, bus|None: MsgBus) : None
        The bus protocol (MsgBorn/MsgBye/MsgReplyHello)
        is handled internally.
        The filter should always be None!
    '''
    ROLE = None

    def __init__(self, name, bus_cbk=None):
        self.name = name
        self.filter = None
        self.bus = None
        self.data = None
        self._bus_cbk = bus_cbk
        self._msg_cbk = None

    #def store(self):
    #    return json.dumps({'name':self.name, 'filter':self.filter, 'ROLE':self.ROLE })

    def __str__(self):
        return '{}({})'.format(type(self).__name__, ','.join(self.get_inputs()))

    def get_inputs(self, recurse=False):
        inputs = []
        if self.filter:
            inputs = [snd for snd in self.filter.sender]
        if recurse and self.filter:
            for snd in self.filter.sender:
                s_node = self.bus.get_node(snd)
                if s_node:
                    #inputs.insert(0, s_node.get_inputs(recurse)) 
                    inputs = s_node.get_inputs(recurse) + inputs 
        return inputs # if self.filter else ['-']

    def get_outputs(self, recursive=False):
        outputs = []
        if self.bus:
            for n in self.bus.nodes:
                if n.filter and self.name in n.filter.sender:
                    outputs.append(n.name)
                    if recursive:
                        s_node = self.bus.get_node(n.name)
                        if s_node:
                            #outputs.append(s_node.get_outputs(recursive))
                            outputs += s_node.get_outputs(recursive)
        return outputs  # if outputs else ['-']

    def plugin(self, bus):
        if self.bus:
            self.bus._unregister(self.name)
            self.bus = None
        if bus._register(self):
            self.bus = bus
            if self._bus_cbk:
                self._bus_cbk(self, self.bus)
            self.post(MsgBorn(self.name, self.data))
            log.info('%s plugged, role %s', str(self), str(self.ROLE))
        else:
            log.warning('%s not plugged (name dupe?)', str(self))
        return self.bus

    def pullout(self):
        if not self.bus:
            return False
        if self._bus_cbk:
            self._bus_cbk(self, None)
        self.post(MsgBye(self.name))
        self.bus._unregister(self.name)
        self.bus = None
        log.info('%s pulled', str(self))
        return True

    def post(self, msg):
        if self.bus:
            self.bus.post(msg)

    def listen(self, msg):
        # standard reactions for unhandled messages
        log.debug('%s.listen %s', str(self), str(msg))
        if isinstance(msg, MsgBorn):
            self.post(MsgReplyHello(self.name, msg.sender))
            return True
        return False


class BusListener(BusNode):
    ''' BusListener is an extension to BusNode.
        Listeners usually filter the messages they listen to.
        Bus protocol is handled internally.
        All (!) messages can be redirected to message callback,
        which returns True, for handled messages, False otherwise.
        message callback:
          message_cbk(self: BusListener, msg: Msg) : bool
        Listening to MsgBorn/MsgBye allows to adjust MsgFilters.
        A derived class must call BusListener.listen() to keep
        protocol intact!
    '''
    def __init__(self, name, filter=None, msg_cbk=None, bus_cbk=None):
        super().__init__(name, bus_cbk)
        if filter:
            if not isinstance(filter, MsgFilter):
                filter = MsgFilter(filter)
        else:
            filter = MsgFilter('*')
        self.filter = filter
        self._msg_cbk = msg_cbk

    def listen(self, msg):
        ret = False
        if self._msg_cbk:
            log.debug('%s._msg_cbk got %s', str(self), str(msg))
            ret = self._msg_cbk(self, msg)
        if not ret:
            log.debug('%s.listen got %s', str(self), str(msg))
            ret = BusNode.listen(self, msg)
        return ret


class BusBroker(BusListener):
    ROLE = BusRole.BROKER

    def __init__(self):
        super().__init__('BusBroker')
        self.values = {}
        self.changed = Event()
        self.changed.clear()

    def listen(self, msg):
        if isinstance(msg, (MsgData,MsgBorn)):
            log.debug('broker got %s', str(msg))
            if self.values.setdefault(msg.sender) != msg.data:
                self.values[msg.sender] = msg.data
                self.changed.set()
        #TODO: MsgBye must remove nodes from self.values
        return BusListener.listen(self, msg)

    def get_nodes(self, roles=None):
        ''' return dict with current nodes: { name:BusNode, ... }
            filtered by set of roles, or all
        '''
        return { n.name:n  for n in self.bus.nodes if not roles or n.ROLE in roles }

    def get_node_names(self, roles=None):
        ''' return arr with current node names: [ name, ... ]
            filtered by set of roles, or all
        '''
        return [ n.name  for n in self.bus.nodes if not roles or n.ROLE in roles ]

    def values_by_names(self, names):
        return {n:self.values[n] for n in self.values if n in names}

    def values_by_role(self, roles):
        return {k:self.values[k] for k in self.values if self.bus.get_node(k).ROLE in roles}

#############################

''' samples of low-level nodes using callbacks
    TODO: unclear whether callbacks are used finally, for now keep 'em
          currently all higher level nodes derive from BusNodes
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
                #print(str(self) + ' = ' + str(t_avg))
                self.post(MsgData(self.name,t_avg))
        return True
    return False

def minThreshold(self, msg):
    if isinstance(msg, MsgData):
        #print(str(self) + ' got ' + str(msg))
        if msg.data < 25:
            self.post(MsgData(self.name, True))
        else:
            self.post(MsgData(self.name, False))

relais_state = False

def relais(self, msg):
    global relais_state
    if isinstance(msg, MsgData):
        #print('{} = {}'.format(msg.sender,msg.data))
        if msg.data != relais_state:
            #print('{} switching {}'.format(self.name,{True:'ON',False:'off'}[msg.data]))
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
    #mb = MsgBus(threaded=True)

    # this are primitive BusNodes, they don't play well with MsgBroker, they are implemented as message callbacks of the basic types

    sensor1 = BusNode('TempSensor1')
    sensor1.plugin(mb)
    sensor2 = BusNode('TempSensor2')
    sensor2.plugin(mb)

    avg = BusListener('TempSensor', msg_cbk=temp_avg)
    avg.plugin(mb)

    temp_ctrl = BusListener('TempController', msg_cbk=minThreshold, filter=msg_busmsgs.MsgFilter(['TempSensor']))
    temp_ctrl.plugin(mb)

    relais = BusListener('TempRelais', msg_cbk=relais, filter=[temp_ctrl.name])
    relais.plugin(mb)

    #mb.register(BusListener('BL3'))

    #for d in [42, 24.83, 'LOW', [1,2,3]]:
    for d in range(100):
        sensor1.post(MsgData(sensor1.name, round(random.random() * 3 + 23.5, 2)))
        if d % 3:
            sensor2.post(MsgData(sensor2.name, round(random.random() * 3 + 23.5, 2)))
        #time.sleep(.1)

    mb.teardown()
