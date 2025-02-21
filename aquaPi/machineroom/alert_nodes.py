#!/usr/bin/env python3

from abc import ABC, abstractmethod
import logging
from typing import Any

from .msg_types import (Msg, MsgPayload, MsgData)
from .msg_bus import (BusListener, BusRole, DataRange)
from ..driver import (PortFunc, io_registry, OutDriver)


log = logging.getLogger('machineroom.alert_nodes')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose


# ========== alert conditions ==========


class AlertCond(ABC):
    """ Base class for all kind of alerting conditions

        node_id - id of node this condition applies to
        limit   - the limit _check() will use
    """
    def __init__(self, node_id: str, limit: float):
        self.node_id: str = node_id
        self.limit: float = limit
        self._alerted: bool = False

    @abstractmethod
    def _check(self, msg: MsgPayload) -> bool:
        """ evaluate alert condition
        """

    def check_for_change(self, msg: Msg) -> bool | None:
        """ Check for change in alert text, return new state or None
        """
        if isinstance(msg, (MsgData)):  # might add other MsgPayload types
            alerted = self._check(msg)
            if (alerted == self._alerted):
                log.debug('%s: alert unchanged %s', msg.sender, self._alerted)
                return None
            self._alerted = alerted
            log.debug('%s: alert changed to %s', msg.sender, self._alerted)
            return self._alerted
        return None

    def is_alerted(self) -> bool:
        """ return current alert state
        """
        return self._alerted

    def alert_text(self, msg: MsgPayload) -> str:
        """ build a human readable alert message
        """
        #if node := bus.get_node(msg.sender):
        #    name = node.name or msg.sender  #FIXME ?
        return self._text(msg, msg.sender)

    @abstractmethod
    def _text(self, msg: MsgPayload, name: str) -> str:
        """ build a human redable alert text
        """


class AlertAbove(AlertCond):
    """ Alert when data above limit
    """
    def _check(self, msg: MsgPayload) -> bool:
        return msg.data > self.limit

    def _text(self, msg: MsgPayload, name: str) -> str:
        return 'Value of %s is %s: %.2f  [limit %.2f]' \
               % (name, 'too high' if self._alerted else 'OK', msg.data, self.limit)


class AlertBelow(AlertCond):
    """ Alert when data below limit
    """
    def _check(self, msg: MsgPayload) -> bool:
        return msg.data < self.limit

    def _text(self, msg: MsgPayload, name: str) -> str:
        return 'Value of %s is %s: %.2f  [limit %.2f]' \
               % (name, 'too low' if self._alerted else 'OK', msg.data, self.limit)


#class AlertLongActive    _check = now - _last_off > limit, _text = "Overload/High utilization"
#class AlertLongInactive  _check = now - _last_on > limit

# ========== alert node ==========


class Alert(BusListener):
    """ A multi-input node, checking alert conditions with output
        to email/telegram/etc. One instance can handle several conditions as
        long as all have the same driver, e.g. all report thru email.

        Options:
            name       - unique name of this alert handler node in UI
            conditions - collection of alert conditions
            port       - port name of driver of type S(tring)out or B(inary)out

        Output:
            - nothing -
    """
    ROLE = BusRole.ALERTS
    data_range = DataRange.STRING

    def __init__(self, name: str, conditions: set[AlertCond] | AlertCond,
                 port: str, _cont: bool = False):
        super().__init__(name, _cont=_cont)
        self.data: list[str] = []
        self._driver: OutDriver | None = None
        self._port: str = ''
        self.port = port
        if isinstance(conditions, AlertCond):
            conditions = {conditions}
        self.conditions: set[AlertCond] = conditions
        self.receives: list[str] = [c.node_id for c in self.conditions]

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state.update(conditions=self.conditions)
        state.update(port=self.port)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        Alert.__init__(self, state['name'], state['conditions'], state['port'],
                       _cont=True)

    @property
    def port(self) -> str:
        return self._port

    @port.setter
    def port(self, port: str):
        if self._driver:
            io_registry.driver_destruct(self._port, self._driver)
            self._driver = None
        if port:
            driver = io_registry.driver_factory(port)
            if isinstance(driver, OutDriver):
                self._driver = driver
            else:
                log.error('Port %s does not support writing alert messages. Alert %s will be ignored.',
                          port, self.name)
        self._port = port

    def listen(self, msg: Msg):
        if isinstance(msg, MsgData) and self._bus:
            any_alert = False
            any_change = False
            self.data = []
            for cond in {c for c in self.conditions if c.node_id == msg.sender}:
                log.debug('## (%s) check %f against %f - %s', type(cond), msg.data, cond.limit, cond.node_id)
                cond_change = cond.check_for_change(msg)

                cond_txt = cond.alert_text(msg)
                if cond_change is not None:
                    self.data.append(cond_txt)
                    any_alert |= cond_change
                    any_change = True
                    log.debug('## "%s" changed to "%s"', type(cond), cond_txt)
                elif cond.is_alerted():
                    self.data.append(cond_txt + '  ... continued')
                    any_alert |= True
                    log.debug('## "%s" still is "%s"', type(cond), cond_txt)

            if any_alert or any_change:
                log.warning('Alerts for %s\n%s', self.name, '\n'.join(self.data))

            # IDEA might add a repeat interval here
            if any_change:
                if self._driver:
                    driver = self._driver
                    if driver.func == PortFunc.Bout:
                        driver.write(100 if any_alert else 0)
                        log.info('Alert device "%s" set to %d', driver.name, 100 if any_alert else 0)
                    elif driver.func == PortFunc.Sout:
                        driver.write('\n'.join(self.data))
                        log.info('Alert receiver "%s" will get msg:  "%s"', driver.name, '\n'.join(self.data))
                self.post(MsgData(self.id, '\n'.join(self.data)))   #TODO MsgAlert ??

    def get_settings(self) -> list[tuple]:
        return []
        # settings = super().get_settings()
        # settings.append(('duration', 'max. Dauer', self.duration,
        #                  'type="number" min="0" max="%d"' % (24*60*60)))
        # return settings
