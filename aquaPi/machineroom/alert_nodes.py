#!/usr/bin/env python3

from abc import ABC, abstractmethod
import logging
# from time import time

from .msg_bus import (BusListener, BusRole, MsgData, MsgFilter)
from ..driver import (PortFunc, io_registry, DriverReadError)


log = logging.getLogger('machineroom.alert_nodes')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose


# ========== alert conditions ==========


class AlertCond(ABC):
    """ Base class for all kind of alerting conditions

        node_id   - id of node this condition applies to
        threshold - the limit _check() will use
    """
    def __init__(self, node_id, threshold):
        self.node_id = node_id
        self.threshold = threshold
        self._alerted = False

    def check_change(self, msg):
        alerted = self._check(msg)
        if (alerted == self._alerted):
            return None
        self._alerted = alerted
        return self._alerted

    def is_alerted(self):
        return self._alerted

    @abstractmethod
    def _check(self, msg):
        pass

    def alert_text(self, msg, bus):
        name = bus.get_node(msg.sender).name or msg.sender
        return self._text(msg, name)

    @abstractmethod
    def _text(self, msg, name):
        pass


class AlertAbove(AlertCond):
    """ Alert when data above threshold
    """
    def _check(self, msg):
        return msg.data > self.threshold

    def _text(self, msg, name):
        return 'Value of %s is %s: %.4f  [limit %.4f]\n' \
               % (name, 'too high' if self._alerted else 'OK', msg.data, self.threshold)


class AlertBelow(AlertCond):
    """ Alert when data below threshold
    """
    def _check(self, msg):
        return msg.data < self.threshold

    def _text(self, msg, name):
        return 'Value of %s is %s: %.4f  [limit %.4f]\n' \
               % (name, 'too low' if self._alerted else 'OK', msg.data, self.threshold)


#class AlertLongActive    _check = now - _last_off > threshold, _text = "Overload/High utilization"
#class AlertLongInactive  _check = now - _last_on > threshold

# ========== alert node ==========


class Alert(BusListener):
    """ A multi-input node, checking alert conditions with output
        to email/telegram/etc.

        Options:
            name       - unique name of this output node in UI
            conditions - collection of alert conditions
            driver     - port name of driver of type S(tring)out or B(inary)out

        Output:
            - nothing -
    """
    ROLE = BusRole.ALERTS

    def __init__(self, name, conditions, port, _cont=False):
        super().__init__(name, _cont=_cont)
        self.data = 0  # just anything for MsgBorn
        self._driver = None
        self._port = None
        self.port = port
        if isinstance(conditions, AlertCond):
            conditions = [conditions]
        self.conditions = conditions
        self._inputs = MsgFilter({c.node_id for c in self.conditions})


    def __getstate__(self):
        state = super().__getstate__()
        state.update(conditions=self.conditions)
        state.update(port=self.port)
        return state

    def __setstate__(self, state):
        self.__init__(state['name'], state['conditions'], state['port'],
                      _cont=True)

    @property
    def port(self):
        return self._port

    @port.setter
    def port(self, port):
        if self._driver:
            io_registry.driver_destruct(self._port, self._driver)
        if port:
            self._driver = io_registry.driver_factory(port)
        self._port = port

    def listen(self, msg):
        if isinstance(msg, MsgData):
            any_alert = False
            any_change = False
            all_msgs = ''
            for cond in [c for c in self.conditions if c.node_id == msg.sender]:
                log.debug('## (%s) check %f against %f - %s', type(cond), msg.data, cond.threshold, cond.node_id)
                cond_change = cond.check_change(msg)

                cond_txt = cond.alert_text(msg, self._bus)
                if cond_change is not None:
                    all_msgs += cond_txt
                    any_alert |= cond_change
                    any_change = True
                    log.debug('## "%s" changed to "%s"', type(cond), cond_txt)
                elif cond.is_alerted():
                    all_msgs += cond_txt
                    any_alert |= True
                    log.debug('## "%s" still is "%s"', type(cond), cond_txt)

            if any_alert or any_change:
                log.warning(all_msgs)

            # IDEA might add a repeat interval here
            if any_change:
                if self._driver.func == PortFunc.Bout:
                    self._driver.write(100 if any_alert else 0)
                    log.info('Alert device "%s" set to %d', self._driver.name, 100 if any_alert else 0)
                elif self._driver.func == PortFunc.Sout:
                    self._driver.write(all_msgs)
                    log.info('Alert receiver "%s" will get msg:  "%s"', self._driver.name, all_msgs)
                self.post(MsgData(self.id, all_msgs))   #TODO MsgAlert ??

    def get_settings(self):
        return []
##        settings = super().get_settings()
##        settings.append(('duration', 'max. Dauer', self.duration,
##                         'type="number" min="0" max="%d"' % (24*60*60)))
##        return settings

