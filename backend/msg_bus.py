#!/usr/bin/env python

import time
from queue import Queue, Empty
import threading
import random
#TODO: import typing and use it for parameters; only useful for linters!!


class Msg:
    ''' The base of all message classes, unusable by itself.
    '''
    def __init__(self, sender):
        self.sender = sender
        self._m_cnt = 0

    def __str__(self):
        return '{}({})#{}'.format(type(self).__name__, self.sender,self._m_cnt)

# payload messages

class MsgPayload(Msg):
    ''' Base class for custom BusMember communication,
        e.g. sensor data, output control, message transformers.
        Payloads may have any data, it is the receiver's task to interpret it.
    '''
    def __init__(self, sender, data):
        Msg.__init__(self, sender)
        self.data = data

    def __str__(self):
        return '{}({})#{}:{}'.format(type(self).__name__, self.sender,self._m_cnt,self.data)

class MsgValue(MsgPayload):
    ''' Transport for data items
        Output of sensors and input for relais.
        All using same type allows to chain BusListeners
        Value can have any type, receiver must interpret it in
        an expectable way, close to Python truthness,
        Caveat: data='off' -> True
        Non-binary outputs should use 0=off, 100=full on (%)
    '''
    pass

# infrastructure messages

class MsgInfra(Msg):
    ''' Base for basic protocol msgs, may not be filtered
    '''
    pass

class MsgBorn(MsgInfra, MsgPayload):
    ''' Announces a new member plugged into the bus and
        make initial value known to others.
        Members return a MsgReplyHello to show their presence.
        Can be used to adjust MsgFilter.
    '''
    pass

class MsgBye(MsgInfra):
    ''' Announces removal of a bus member.
        Dependant members can adjust their behavior.
    '''
    pass

# reply messages

class MsgReply(Msg):
    ''' Base class for all reply messages, usually 1:1.
    '''
    def __init__(self, sender, send_to):
        Msg.__init__(self, sender)
        self.send_to = send_to

    def __str__(self):
        return Msg.__str__(self) + '->' + self.send_to

class MsgReplyHello(MsgReply, MsgInfra):
    ''' Reply from plugged-in members to MsgBorn.
        Used to let new members see who's present.
    '''
    pass

#############################

class MsgBus:
    ''' Communication channel between all registered
        BusMembers.
        Supports public and 1:1 messaging, plugin/pullout
        notification and message filtering for each listener.
        Msg dispatcher can run as blocking loop of post()
        or in a worker thread. Unthreaded is much faster
        and easier to debug, thus the default.
    '''
    def __init__(self, threaded=False):
        self.listeners = []
        self._m_cnt = 0
        self._queue = None
        if threaded:
            self._queue = Queue(maxsize=10)  # or collections.deque?
            threading.Thread(target=self._dispatch, daemon=True).start()

    def __str__(self):
        if not self._queue:
            return '{}({} lst)'.format(type(self).__name__, len(self.listeners))
        return '{}({} q''d, {} lst)'.format(type(self).__name__, self._queue.qsize(), len(self.listeners))

    def get_member(self, name):
        ''' Find BusMember by its name.
        '''
        lst = [l for l in self.listeners if l.name == name]
        return lst[0] if lst else None

    def _register(self, listener):
        ''' Add a BusMember to the bus.
            Return False if duplicate name.
        '''
        lst = self.get_member(listener.name)
        if lst:
            return False

        if self._queue:
            # empty the queue before listeners change
            self._queue.join()
        self.listeners.append(listener)
        return True

    def _unregister(self, name):
        ''' Remove BusMember from bus.
        '''
        listener = self.get_member(name)
        if listener:
            if self._queue:
                # empty the queue before listeners change
                self._queue.join()
            self.listeners.remove(listener)

    def post(self, msg):
        ''' Put message into the queue or dispatch in a
            blocking loop.
            Descentants of MsgReply containy the name of
            receiver (send_to) for 1:1 communication.
            This might change too to a send_to parameter.
        '''
        self._m_cnt += 1
        msg._m_cnt = self._m_cnt
        print(str(self) + '   + ' + str(msg))
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
        #print(str(msg) + ' ->')
        if isinstance(msg, MsgReply):
            # directed message sender -> receiver
            lst = [l for l in self.listeners if l.name == msg.send_to]
        else:
            # broadcast message, exclude sender
            lst = [l for l in self.listeners if l.name != msg.sender]
        if not isinstance(msg, MsgInfra):
            lst = [l for l in lst if isinstance(l, BusListener)]
            lst = [l for l in lst if not l.filter or l.filter.apply(msg)]
        for l in lst:
            #print('  -> ' + str(l))
            l.listen(msg)

    def teardown(self):
        ''' Prepare for shutdown, e.g. unplug all.
        '''
        for lst in [l for l in self.listeners]:
            #print('teardown ' + str(lst))
            lst.pullout()

#############################

class BusMember:
    ''' BusMember is a minimal bus participant
        It has little overhead, can only post messages.
        Methods plugin/pullout can be redirected to a callback to
        let you know when to start or finish your task.
        Bus callback:
          bus_cbk(self: BusMember, bus|None: MsgBus) : None
        The bus protocol (MsgBorn/MsgBye/MsgReplyHello)
        is handled internally.
    '''
    def __init__(self, name, func=None, bus_cbk=None):
        self.name = name
        self.func = func
        self.bus = None
        self.data = None
        self._bus_cbk = bus_cbk
        self._msg_cbk = None

    def __str__(self):
        return '{}({})'.format(type(self).__name__, self.name)

    def plugin(self, bus):
        if self.bus:
            self.bus._unregister(self.name)
            self.bus = None
        if bus._register(self):
            self.bus = bus
            if self._bus_cbk:
                self._bus_cbk(self, self.bus)
            self.post(MsgBorn(self.name, self.data))
            #print(str(self) + ' plugged')
        else:
            pass
            #print(str(self) + ' not plugged (name dupe?')
        return self.bus

    def pullout(self):
        if not self.bus:
            return False
        if self._bus_cbk:
            self._bus_cbk(self, None)
        self.post(MsgBye(self.name))
        self.bus._unregister(self.name)
        self.bus = None
        #print(str(self) + ' pulled')
        return True

    def post(self, msg):
        if self.bus:
            self.bus.post(msg)

    def listen(self, msg):
        # standard reactions for unhandled messages
        #print('{}.listen {}\n'.format(str(self), str(msg)))
        if isinstance(msg, MsgBorn):
            self.post(MsgReplyHello(self.name, msg.sender))
            return True
        return False


class BusListener(BusMember):
    ''' BusListener is an extension to BusMember.
        Bus protocol is handled internally.
        All (!) messages can be redirected to message callback,
        which returns True, for handled messages, False otherwise.
        message callback:
          message_cbk(self: BusListener, msg: Msg) : bool
        Listening to MsgBorn/MsgBye allows to adjust MsgFilters.
        A derived class must call MsgBus.listen() to keep
        protocol intact!
    '''
    def __init__(self, name, func=None, filter=None, msg_cbk=None, bus_cbk=None):
        BusMember.__init__(self, name, func, bus_cbk)
        if filter and not isinstance(filter, MsgFilter):
            filter = MsgFilter(filter)
        self.filter = filter
        self._msg_cbk = msg_cbk

    def listen(self, msg):
        ret = False
        if self._msg_cbk:
            #print('{}._msg_cbk got {}\n'.format(str(self), str(msg)))
            ret = self._msg_cbk(self, msg)
        if not ret:
            #print('{}.listen got {}\n'.format(str(self), str(msg)))
            ret = BusMember.listen(self, msg)
        return ret

#############################

class MsgFilter():
    ''' MsgFilter is used to select messages received
        by BusListener via a list of sender names.
        Empty list (actually an array) means no filtering.
        sender_list may be None=all, a string or a list of strings.
    '''
    #TODO add filtering by other attributes (group, category, sender type)
    def __init__(self, sender_lst):
        if (isinstance(sender_lst, str)):
            self.sender_lst = [sender_lst]
        else:
            self.sender_lst = sender_lst

    def __str__(self):
        return '{}({})'.format(type(self).__name__, ','.join(self.sender_lst))

    def apply(self, msg):
        if not self.sender_lst or msg.sender in self.sender_lst:
            #TODO add categories and/or groups
            return True
        return False

#############################

t_avg = None

def temp_avg(self, msg):
    global t_avg
    if isinstance(msg, MsgValue):
        if not t_avg:
            t_avg = msg.data
        else:
            print(str(msg))
            t_new = round((t_avg + msg.data) / 2, 2)
            if t_new != t_avg:
                t_avg = t_new
                #print(str(self) + ' = ' + str(t_avg))
                self.post(MsgValue(self.name,t_avg))
        return True
    return False

def minThreshold(self, msg):
    if isinstance(msg, MsgValue):
        #print(str(self) + ' got ' + str(msg))
        if msg.data < 25:
            self.post(MsgValue(self.name, True))
        else:
            self.post(MsgValue(self.name, False))

relais_state = False

def relais(self, msg):
    global relais_state
    if isinstance(msg, MsgValue):
        #print('{} = {}'.format(msg.sender,msg.data))
        if msg.data != relais_state:
            #print('{} switching {}'.format(self.name,{True:'ON',False:'off'}[msg.data]))
            relais_state = msg.data
        return True
    return False

#############################

if __name__ == "__main__":
    mb = MsgBus()
    #mb = MsgBus(threaded=True)

    # this are primitive BusMembers, they don't play well with MsgBroker, they are implemented as message callbacks of the basic types

    sensor1 = BusMember('TempSensor1', 'sensor.temp')
    sensor1.plugin(mb)
    sensor2 = BusMember('TempSensor2', 'sensor.temp')
    sensor2.plugin(mb)

    avg = BusListener('TempSensor', 'sensor.aggregate.temp', msg_cbk=temp_avg)
    avg.plugin(mb)

    temp_ctrl = BusListener('TempController', 'controller.temp', msg_cbk=minThreshold, filter=MsgFilter(['TempSensor']))
    temp_ctrl.plugin(mb)

    relais = BusListener('TempRelais', 'device.temp.heat', msg_cbk=relais, filter=[temp_ctrl.name])
    relais.plugin(mb)

    #mb.register(BusListener('BL3'))

    #for d in [42, 24.83, 'LOW', [1,2,3]]:
    for d in range(100):
        sensor1.post(MsgValue(sensor1.name, round(random.random() * 3 + 23.5, 2)))
        if d % 3:
            sensor2.post(MsgValue(sensor2.name, round(random.random() * 3 + 23.5, 2)))
        #time.sleep(.1)

    mb.teardown()
