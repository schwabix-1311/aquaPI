#!/usr/bin/env python3

from abc import (ABC, abstractmethod)
import logging
import time
from queue import Queue
from enum import (Enum, Flag, auto)
from typing import (Iterable, Any)
from threading import (Condition, Thread)

from .msg_types import (Msg, MsgInfra, MsgBorn, MsgBye,
                        MsgReply, MsgReplyHello,
                        MsgData)


log = logging.getLogger('machineroom.msg_bus')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose


class BusRole(Flag):
    IN_ENDP = auto()  # data sources: sensor, switch, schedule
    OUT_ENDP = auto()  # output: relays, logs, mails
    CTRL = auto()  # the core of a controller: process IN -> OUT
    AUX = auto()  # helper func: 2:1/n:1, e.g. avg, delay
    HISTORY = auto()  # nodes recording the output of other nodes
    ALERTS = auto()  # nodes processing alert conditions
    UNDEF = 0


class DataRange(Enum):
    UNDEF = 0
    ANALOG = auto()   # float, any range, typically input sensors
    BINARY = auto()   # hard on=100 / off=0
    PERCENT = auto()  # normalized 0..100%, the bulk of data
    PERC_3 = auto()   # tupel of 3 percentages, e.g. RGB light
    STRING = auto()   # string , e.g. alert text


#############################


class BusNode(ABC):
    """ BusNode is a minimal bus participant
        It has little overhead, can only post messages.
        The bus protocol (MsgBorn/MsgBye/MsgReplyHello)
        is handled internally. Overload if you need one of them,
        but don't forget to call super().listen(...)
    """
    ROLE: BusRole = BusRole.UNDEF
    data_range = DataRange.UNDEF

    def __init__(self, name: str, _cont: bool = False):
        self.name = name
        self.id = name.lower()  # uuid.uuid4(uuid.NAMSPACE_OID,name)
        self.id = self.id.replace(' ', '').replace('.', '').replace(';', '')
        self.id = self.id.replace('Ä', 'Ae').replace('ä', 'ae')
        self.id = self.id.replace('Ö', 'Oe').replace('ö', 'oe')
        self.id = self.id.replace('Ü', 'Ue').replace('ü', 'ue')
        self.id = self.id.replace('-', '_').replace('ß', 'ss')
        # this is a bit of abuse: replace all non-ASCII with xml refs, then back to utf-8
        self.id = str(self.id.encode('ascii', 'xmlcharrefreplace'), errors='strict')
        self.identifier = self.__class__.__qualname__ + '.' + self.id
        log.debug(self.id)

        self.receives = ['*']
        self._bus: 'MsgBus' | None = None  # forward ref to class MsgBus
        if not _cont:
            self.data: Any = 0
        self.unit = ''
        self.alert: tuple[str, str] | None = None

    def __getstate__(self) -> dict[str, Any]:
        state = {'name': self.name}
        state.update(id=self.id)
        state.update(identifier=self.identifier)
        state.update(receives=self.receives)
        state.update(data=self.data)
        state.update(unit=self.unit)
        state.update(data_range=self.data_range.name)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        BusNode.__init__(self, state['name'], _cont=True)

    def __str__(self) -> str:
        return '{}({})'.format(type(self).__name__, ','.join(self.receives))

    def plugin(self, bus: 'MsgBus') -> None:
        if self._bus:
            self._bus.unregister(self)
            self._bus = None
        bus.register(self)
        self._bus = bus
        self.post(MsgBorn(self.id, self.data))
        log.info('%s plugged, role %s', str(self), str(self.ROLE))

    def pullout(self) -> bool:
        if not self._bus:
            return False
        self.post(MsgBye(self.id))
        self._bus.unregister(self)
        self._bus = None
        log.info('%s pulled', str(self))
        return True

    def post(self, msg: Msg) -> None:
        if self._bus:
            self._bus.post(msg)

    def listen(self, msg: Msg) -> bool:
        # standard reactions for unhandled messages
        log.debug('%s.listen %s', str(self), str(msg))
        if isinstance(msg, MsgBorn):
            self.post(MsgReplyHello(self.id, msg.sender))
            return True
        return False

    def get_receives(self, recurse: bool = False) -> list['BusNode']:
        receives: list['BusNode'] = []
        if self._bus:
            for rcv in self.receives:
                node = self._bus.get_node(rcv)
                if node:
                    log.debug('%s receives %r', self.name, rcv)
                    receives.append(node)
            if recurse:
                for s_node in receives:
                    receives = s_node.get_receives(recurse) + receives
        return receives

    def get_listeners(self, recurse: bool = False) -> list['BusNode']:
        listeners: list[BusNode] = []
        if self._bus:
            for node in self._bus.nodes:
                if node.ROLE in (BusRole.HISTORY, BusRole.ALERTS):
                    continue
                if self.id in node.receives:
                    listeners.append(node)
                    if recurse:
                        s_node = self._bus.get_node(node.id)
                        if s_node:
                            listeners = listeners + s_node.get_listeners(recurse)
        return listeners

    @abstractmethod
    def get_settings(self) -> list[tuple]:
        return []


class BusListener(BusNode, ABC):
    """ BusListener is an extension to BusNode.
        Listeners usually have one input they listen to
        and react by posting messages.
        A derived class must call super().listen(msg) to keep
        protocol intact! Bus protocol is handled there.
    """

    def __init__(self, name: str, receives: str | Iterable[str] = '*',
                 _cont=False):
        super().__init__(name, _cont=_cont)
        if receives:
            if isinstance(receives, str):
                self.receives = [receives]
            else:
                self.receives = [rcv for rcv in receives]

    # def __getstate__(self) -> dict[str, Any]:
    #     state = super().__getstate__()
    #     return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        BusListener.__init__(self, state['name'],
                             receives=state['receives'],
                             _cont=True)

    def listen(self, msg: Msg) -> bool:
        log.debug('%s.listen got %s', str(self), str(msg))
        return super().listen(msg)

    def get_settings(self) -> list[tuple]:
        settings = super().get_settings()
        settings.append((None, 'Receives',
                         ';'.join(MsgBus.to_names(self.get_receives())),
                         'type="text"'))
        return settings


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

    def __init__(self, threaded: bool = False):
        self._threaded = threaded
        self.nodes: set[BusNode] = set()
        self.dbg_cnt: int = 0
        self._changes: set[str] = set()
        self._changed = Condition()
        self._queue: Queue | None = None

        if threaded:
            self._queue = Queue(maxsize=10)
            Thread(target=self._dispatch, daemon=True).start()

    def __getstate__(self) -> dict[str, Any]:
        state = {'nodes': self.nodes, 'threaded': self._threaded}
        log.debug('MsgBus.getstate %r', state)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        log.debug('MsgBus.setstate %r', state)
        MsgBus.__init__(self, state['threaded'])
        for n in state['nodes']:
            n.plugin(self)

    def __str__(self) -> str:
        return '{}({} nodes)'.format(type(self).__name__, len(self.nodes))

    def register(self, node: BusNode) -> None:
        """ Add a BusNode to the bus. Do not call directly,
            use BusNode.plugin() instead!
            Raises exception if duplicate id.
        """
        # reject ambiguities in id or name
        if self.get_node(node.id):
            raise Exception(f'Duplicate node: name {node.name}, id {node.id}')

        if self._queue:
            # empty the queue before nodes change
            self._queue.join()
        self.nodes.add(node)

    def unregister(self, node: BusNode):
        """ Remove BusNode from bus. Do not call directly,
            use BusNode.plugin() instead!
        """
        if node:
            if self._queue:
                # empty the queue before nodes change
                self._queue.join()
            self.nodes.remove(node)

    def post(self, msg: Msg) -> None:
        """ Put message into the queue or dispatch in a
            blocking loop.
            Descendants of MsgReply contain the id of
            receiver (send_to) for 1:1 communication.
            This might change too to a send_to parameter.
        """
        self.dbg_cnt += 1
        msg.dbg_cnt = self.dbg_cnt
        log.debug('%s   + %s', str(self), str(msg))
        if self._queue:
            self._queue.put(msg, block=True, timeout=5)
        else:
            self._dispatch_one(msg)

    def _dispatch(self) -> None:
        """ Dispatch all queued messages in a worker thread
        """
        while self._queue:  # always True, make mypy happy
            msg = self._queue.get()
            self._dispatch_one(msg)
            self._queue.task_done()

    def _dispatch_one(self, msg: Msg) -> None:
        """ Dispatch one message to all listeners in a blocking loop.
        """
        if isinstance(msg, (MsgData, MsgBorn)):
            log.debug('  notify the change event about %s', str(msg))
            self.report_change(msg.sender)

        # dispatch the message
        log.debug('%s ->', str(msg))
        rcv_nodes: set[BusNode] = set()
        if isinstance(msg, MsgReply):
            # directed message sender -> receiver
            if node := self.get_node(msg.send_to):
                rcv_nodes = {node}
        else:
            # broadcast message: all but sender
            rcv_nodes = {n for n in self.nodes if n.id != msg.sender}
            # ... and apply each node's filter for non-Infra msgs
            if not isinstance(msg, MsgInfra):
                rcv_nodes = {n for n in rcv_nodes
                             if msg.sender in n.receives or '*' in n.receives}
        for n in rcv_nodes:
            log.debug('  -> %s', str(n))
            n.listen(msg)

    def teardown(self) -> None:
        """ Prepare for shutdown, e.g. unplug all.
        """
        for n in self.nodes.copy():
            log.debug('teardown %s', str(n))
            n.pullout()

    def get_node(self, id_or_name: str) -> BusNode | None:
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
    def to_names(node_list: Iterable[BusNode]) -> list[str]:
        """ return a list of names from whatever iterable container with nodes
        """
        return [node.name for node in node_list]

    def report_change(self, node_id: str) -> None:
        """ add ID to list of changed nodes and notify one (!) waiting thread
        """
        log.debug('report_change locked: %s', node_id)
        with self._changed:
            self._changes.add(node_id)
            self._changed.notify()
            log.debug('report_change notified & done: %s', node_id)
            time.sleep(.01)  # this is a hack, I don't find the race cond.

    def wait_for_changes(self) -> set[str]:
        """ block until at least one node reported data changes,
            then clear the internal list of changes
            return ids of modified nodes [id1, id2, ...]
        """
        log.debug('wait_for_changes')
        with self._changed:
            self._changed.wait_for(lambda: len(self._changes))
            change = {id for id in self._changes}
            log.debug('self._changes len: %d, report len %d', len(self._changes), len(change))
            self._changes.clear()
            log.debug('cleared change_list: %r', change)
        return change


#############################


if __name__ == "__main__":
    # This is your playground ... not used in the application

    mb = MsgBus()
    # mb = MsgBus(threaded=True)

    # relay = BusListener('TempRelay', msg_cbk=relay, inputs=temp_ctrl.id)
    # relay.plugin(mb)

    mb.teardown()
