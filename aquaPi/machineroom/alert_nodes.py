#!/usr/bin/env python3

from abc import ABC, abstractmethod
import logging
from typing import Any
from time import time

from .msg_types import (Msg, MsgPayload, MsgData)
from .msg_bus import (BusListener, BusRole, DataRange)
from ..driver import (IoRegistry, PortFunc, OutDriver)


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
        self._alert_text: str = ''

    def __str__(self) -> str:
        return f'{type(self).__name__}({self.limit})'

    @property
    def alerted(self) -> bool:
        """ return current alert state, RO
        """
        return self._alerted

    @property
    def alert_text(self) -> str:
        """ return current human readable alert state
        """
        return self._alert_text

    @abstractmethod
    def _check(self, msg: MsgPayload) -> bool:
        """ evaluate alert condition
        """

    @abstractmethod
    def _text(self, msg: MsgPayload) -> str:
        """ build a human redable alert text
        """

    def check_for_change(self, msg: Msg) -> bool | None:
        """ Check for change in alert status, update alert_text,
            return state changed to, or None if inappropriate msg or no change
        """
        # might add other MsgPayload types
        if isinstance(msg, (MsgData)) and msg.sender == self.node_id:
            old_alerted = self._alerted
            self._alerted = self._check(msg)
            self._alert_text = self._text(msg)

            return self._alerted if old_alerted != self._alerted else None
        return None


class AlertAbove(AlertCond):
    """ Alert when data above limit
    """
    def _check(self, msg: MsgPayload) -> bool:
        return msg.data > self.limit

    def _text(self, msg: MsgPayload) -> str:
        #return f'Value of {msg.sender} is {"HIGH" if self._alerted else "OK"}: ' \
        #       + f'{msg.data:.2f}  [limit {self.limit:.2f}]'
        return f'{msg.sender}: Messwert {"zu HOCH" if self._alerted else "OK"}: ' \
               + f'{msg.data:.2f}  [Grenzwert {self.limit:.2f}]'


class AlertBelow(AlertCond):
    """ Alert when data below limit
    """
    def _check(self, msg: MsgPayload) -> bool:
        return msg.data < self.limit

    def _text(self, msg: MsgPayload) -> str:
        #return f'Value of {msg.sender} is {"LOW" if self._alerted else "OK"}: ' \
        #       + f'{msg.data:.2f}  [limit {self.limit:.2f}]'
        return f'{msg.sender}: Messwert {"zu NIEDRIG" if self._alerted else "OK"}: ' \
               + f'{msg.data:.2f}  [Grenzwert {self.limit:.2f}]'


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
            repeat     - interval to repeat alert message [sec], or 0

        Output:
            - nothing -
    """
    ROLE = BusRole.ALERTS
    data_range = DataRange.STRING

    def __init__(self, name: str, conditions: set[AlertCond] | AlertCond,
                 port: str, repeat: int = 60 * 60, _cont: bool = False):
        super().__init__(name, _cont=_cont)
        self.data: list[str] = []
        self.repeat: int = repeat  # default is 1 hour
        self._repeat_time: float | None = None
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
        state.update(repeat=self.repeat)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        Alert.__init__(self, state['name'], state['conditions'], state['port'],
                       state['repeat'], _cont=True)

    @property
    def port(self) -> str:
        return self._port

    @port.setter
    def port(self, port: str):
        if self._driver:
            IoRegistry.get().driver_destruct(self._port, self._driver)
            self._driver = None
        if port:
            driver = IoRegistry.get().driver_factory(port)
            if isinstance(driver, OutDriver):
                self._driver = driver
            else:
                log.error('Port %s does not support writing alert messages. Alert %s will be ignored.',
                          port, self.name)
        self._port = port

    def listen(self, msg: Msg):
        if isinstance(msg, MsgData) and self._bus:
            log.debug("## Alert %s check %.4f from %s",
                      self.name, msg.data, msg.sender)
            any_alert = False
            any_change = False
            self.data = []
            for cond in {c for c in self.conditions}:
                # log.debug('## %s check %s', cond, msg)
                cond_change = cond.check_for_change(msg)
                if cond.alerted:
                    any_alert |= True
                    if cond_change is True:   # is not None and True!
                        log.debug('## %s changed to "%s"',
                                  cond, cond.alert_text)
                        any_change |= True
                        #self.data.insert(0, f'{cond.node_id} Alert: {cond}\n'
                        #                    f'{cond.alert_text}')
                        self.data.insert(0, f'{cond.node_id} Warnung: {cond}\n'
                                            f'{cond.alert_text}')
                    else:
                        log.debug('## %s still is "%s"', cond, cond.alert_text)
                        #self.data.append(f'{cond.node_id} Alert: {cond}\n'
                        #                 f'{cond.alert_text}  ... continues')
                        self.data.append(f'{cond.node_id} Warnung: {cond}\n'
                                         f'{cond.alert_text}  ... besteht weiterhin')
                else:
                    if cond_change is False:
                        log.debug('## %s cleared "%s"', cond, cond.alert_text)
                        any_change |= True
                        #self.data.insert(0, f'{cond.node_id} Alert: {cond}\n'
                        #                    f'{cond.alert_text}  ... cleareed')
                        self.data.insert(0, f'{cond.node_id} Warnung: {cond}\n'
                                            f'{cond.alert_text}  ... beseitigt')

            # log.debug("%s : finally anyAlrt %r, anyChng %r: %r",
            #           self.name, any_alert, any_change, self.data)

            if any_alert:
                log.warning('Alerts by %s\n"%s"', self.name, '\n'.join(self.data))
            self.post(MsgData(self.id, '\n'.join(self.data)))

            if any_change \
               or (self._repeat_time and (time() > self._repeat_time)):
                self._repeat_time = time() + self.repeat
                if self._driver:
                    driver = self._driver
                    if driver.func == PortFunc.Bout:
                        driver.write(100 if any_alert else 0)
                        log.info('Alert device "%s" set to %d',
                                 driver.name, 100 if any_alert else 0)
                    elif driver.func == PortFunc.Tout:
                        driver.write(' \n'.join(self.data))
                        log.info('Alert receiver "%s" will get msg:  "%s"',
                                 driver.name, '\n'.join(self.data))
            else:
                self._repeat_time = None

    def get_settings(self) -> list[tuple]:
        settings = super().get_settings()
        settings.append(('repeat', 'Wiederholung [s]', self.repeat,
                         'type="number" min="0" max="%d" step="60"' % (24*60*60)))
        return settings
