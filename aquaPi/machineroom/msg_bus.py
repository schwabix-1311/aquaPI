#!/usr/bin/env python

import logging
from queue import Queue
from enum import Flag, auto
from threading import Thread, Event

from .msg_types import *


log = logging.getLogger('MsgBus')
log.setLevel(logging.WARNING)  # INFO)
#log.setLevel(logging.DEBUG)


class BusRole(Flag):
    IN_ENDP = auto()    # data sources: sensor, switch, schedule
    OUT_ENDP = auto()   # output: relais, logs, mails
    CTRL = auto() # the core of a controller: process IN -> OUT
    AUX = auto()        # helper func: 2:1/n:1, e.g. avg, delay, or

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
        Several get_* methods build the interface to Flask backend
    '''
    def __init__(self, threaded=False):
        self._threaded = threaded
        self.nodes = []
        self.values = {}
        self.changed = Event()
        self.changed.clear()
        self._m_cnt = 0
        self._queue = None
        if threaded:
            self._queue = Queue(maxsize=10)
            Thread(target=self._dispatch, daemon=True).start()

    def __getstate__(self):
        state = {'nodes':self.nodes, 'threaded':self._threaded}
        log.debug('MsgBus.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.warning('MsgBus.setstate %r', state)
        self.__init__(state['threaded'])
        for n in state['nodes']:
            n.plugin(self)

    def __str__(self):
        if not self._queue:
            return '{}({} nodes)'.format(type(self).__name__, len(self.nodes))
        return '{}({} nodes, {} queue\'d)'.format(type(self).__name__, len(self.nodes), self._queue.qsize())

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
                # empty the queue before nodes change
                self._queue.join()
            self.nodes.remove(node)
            del self.values[name]

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
            Maintain a cache of MsgData values (is it worth the effort?)
        '''
        #FIXME cache before or after dispatching?
        if isinstance(msg, (MsgData,MsgBorn)):
            log.debug('  cache upd %s', str(msg))
            if self.values.setdefault(msg.sender) != msg.data:
                self.values[msg.sender] = msg.data
                self.changed.set()

        # dispatch the message
        log.debug('%s ->', str(msg))
        if isinstance(msg, MsgReply):
            # directed message sender -> receiver
            lst = [n for n in self.nodes if n.name == msg.send_to]
        else:
            # broadcast message, exclude sender
            lst = [n for n in self.nodes if n.name != msg.sender]
        if not isinstance(msg, MsgInfra):
            #lst = [l for l in lst if isinstance(l, BusListener)]
            lst = [n for n in lst if n._inputs and n._inputs.filter(msg)]
        for n in lst:
            log.debug('  -> %s', str(n))
            n.listen(msg)

    def teardown(self):
        ''' Prepare for shutdown, e.g. unplug all.
        '''
        for n in self.nodes:
            log.debug('teardown %s', str(n))
            n.pullout()

    def get_node(self, name):
        ''' Find BusNode by its name.
        '''
        lst = [n for n in self.nodes if n.name == name]
        return lst[0] if lst else None

    # former BusBroker functions, i.e. the interface for Flask backend

    def get_nodes(self, roles=None):
        ''' return dict with current nodes: { name:BusNode, ... }
            filtered by set of roles, or all
        '''
        return { n.name:n  for n in self.nodes if not roles or n.ROLE in roles }

    def get_node_names(self, roles=None):
        ''' return arr with current node names: [ name, ... ]
            filtered by set of roles, or all
        '''
        return [ n.name  for n in self.nodes if not roles or n.ROLE in roles ]

    def values_by_names(self, names):
        #TODO cache values{} seems unneccessary, access nodes.data directly!
        return { n:self.values[n]  for n in self.values if n in names }

    def values_by_role(self, roles):
        #TODO cache values{} seems unneccessary, access nodes.data directly!
        return { n:self.values[n]  for n in self.values if self.nodes[n].ROLE in roles }

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
        The _inputs should always be None = listen to everbody!
    '''
    ROLE = None

    def __init__(self, name, bus_cbk=None):
        self.name = name
        self._inputs = None
        self._bus = None
        self.data = None
        self._bus_cbk = bus_cbk
        self._msg_cbk = None

    def __getstate__(self):
        state = {'name':self.name, 'inputs':self._inputs, 'data':self.data}
        log.debug('< BusNode.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('BusNode.setstate %r', state)
        self.__init__(state['name'])
        self.data = state['data']

    def __str__(self):
        return '{}({})'.format(type(self).__name__, ','.join(self.get_inputs()))

    def plugin(self, bus):
        if self._bus:
            self._bus._unregister(self.name)
            self._bus = None
        if bus._register(self):
            self._bus = bus
            if self._bus_cbk:
                self._bus_cbk(self, self._bus)
            self.post(MsgBorn(self.name, self.data))
            log.info('%s plugged, role %s', str(self), str(self.ROLE))
        else:
            log.warning('%s not plugged (name dupe?)', str(self))
        return bool(self._bus != None)

    def pullout(self):
        if not self._bus:
            return False
        if self._bus_cbk:
            self._bus_cbk(self, None)
        self.post(MsgBye(self.name))
        self._bus._unregister(self.name)
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
            self.post(MsgReplyHello(self.name, msg.sender))
            return True
        return False

    def get_inputs(self, recurse=False):
        inputs = []
        if self._inputs:
            inputs = [snd for snd in self._inputs.sender]
        if recurse and self._inputs:
            for snd in self._inputs.sender:
                s_node = self._bus.get_node(snd)
                if s_node:
                    inputs = s_node.get_inputs(recurse) + inputs 
        return inputs # if self._inputs else ['-']

    def get_outputs(self, recursive=False):
        outputs = []
        if self._bus:
            for n in self._bus.nodes:
                if n._inputs and self.name in n._inputs.sender:
                    outputs.append(n.name)
                    if recursive:
                        s_node = self._bus.get_node(n.name)
                        if s_node:
                            outputs += s_node.get_outputs(recursive)
        return outputs  # if outputs else ['-']


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
        log.warning('BusListener.setstate %r', state)
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

    # this are primitive BusNodes, they are implemented as message callbacks of the basic types

    sensor1 = BusNode('TempSensor1')
    sensor1.plugin(mb)
    sensor2 = BusNode('TempSensor2')
    sensor2.plugin(mb)

    avg = BusListener('TempSensor', msg_cbk=temp_avg)
    avg.plugin(mb)

    temp_ctrl = BusListener('TempController', msg_cbk=minThreshold, inputs=MsgFilter(['TempSensor']))
    temp_ctrl.plugin(mb)

    relais = BusListener('TempRelais', msg_cbk=relais, inputs=[temp_ctrl.name])
    relais.plugin(mb)

    #mb.register(BusListener('BL3'))

    #for d in [42, 24.83, 'LOW', [1,2,3]]:
    for d in range(100):
        sensor1.post(MsgData(sensor1.name, round(random.random() * 3 + 23.5, 2)))
        if d % 3:
            sensor2.post(MsgData(sensor2.name, round(random.random() * 3 + 23.5, 2)))
        #time.sleep(.1)

    mb.teardown()
