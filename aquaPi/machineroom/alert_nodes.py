#!/usr/bin/env python3

from abc import ABC, abstractmethod
import logging
from typing import Any, Callable
import operator
from time import monotonic

from .msg_types import (Msg, MsgData)
from .msg_bus import (BusListener, BusRole, DataRange)
from ..driver import (IoRegistry, PortFunc, OutDriver)


log = logging.getLogger('machineroom.alert_nodes')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose


# ========== alert conditions ==========


OP_SYMBOL = {operator.ge: ">=", operator.le: "<=",
             operator.gt: ">", operator.lt: "<",
             operator.eq: "=="}


class AlertCond(ABC):
    """ Base class for all alerting conditions
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
    def _check(self, msg: MsgData) -> bool:
        """ evaluate alert condition
        """

    @abstractmethod
    def _text(self, msg: MsgData) -> str:
        """ build a human redable alert text
        """

    def check_for_change(self, msg: Msg) -> bool | None:
        """ Check for change in alert status, update alert_text,
            return state changed to, or None if inappropriate msg or no change
        """
        if isinstance(msg, MsgData) and msg.sender == self.node_id:
            old = self._alerted
            self._alerted = self._check(msg)
            self._alert_text = self._text(msg)

            return self._alerted if old != self._alerted else None
        return None


class AlertThreshold(AlertCond):
    """ Alert when source beyond limit for longer than duration.

        node_id  - id of node this condition applies to
        limit    - optional threshold to cause an alert [50%]
        duration - optional duration (mins) the limit must be exceeded [0]

        With both opt. params unset this alert will trigger instantly
        when the source is >= 50. This may not be what you intend.
        Either give a limit, e.g. for immediate temperature warnings,
        or a duration and maybe a limit, to be warned if e.g. the heating was
        active longer than expected (overload?) or your pH stays
        higher than specified for the given time span (CO2 bottle empty).
    """
    def __init__(self, node_id: str,
                 cmp: Callable[[float, float], bool], direction: str,
                 limit: float = 50., duration: int = 0):
        super().__init__(node_id, limit)
        self.duration: int = duration
        self._cmp = cmp
        self._direction = direction
        self._starttime: float | None = None

    def __str__(self) -> str:
        txt = f'{type(self).__name__}({OP_SYMBOL[self._cmp]}{self.limit}'
        if self.duration:
            txt += f' for {self.duration} min'
        return txt + ')'

    def _check(self, msg: MsgData) -> bool:
        log.debug("%s.check %s", type(self).__name__, msg)
        now = monotonic()
        if self._cmp(msg.data, self.limit):
            log.debug("  started")
            self._starttime = now
        else:
            log.debug("  ended")
            self._starttime = None
            return False

        if self.duration == 0:
            return True

        triggered = (now >= self._starttime + self.duration * 60)

        log.debug("  %.1f >= %.1f + %.1f = %r",
                  now, self._starttime, self.duration * 60, triggered)
        return triggered

    def _text(self, msg: MsgData) -> str:
        if self.alerted:
            if self.duration:
                minutes = (monotonic() - self._starttime) / 60
                return (f'{msg.sender}: Messwert zu {self._direction}: '
                        f'{msg.data:.2f} seit {minutes:.1f} min'
                        f'  [Grenzwert {self.limit:.2f} für max. {self.duration} min]')
            else:
                return (f'{msg.sender}: Messwert zu {self._direction}: '
                        f'{msg.data:.2f}  [Grenzwert {self.limit:.2f}]')
        else:
            return (f'{msg.sender}: Messwert OK: '
                    f'{msg.data:.2f}  [Grenzwert {self.limit:.2f}]')


class AlertAbove(AlertThreshold):
    def __init__(self, node_id: str, limit: float = 50., duration: int = 0):
        super().__init__(node_id, operator.ge, "HOCH", limit, duration)


class AlertBelow(AlertThreshold):
    def __init__(self, node_id: str, limit: float = 50., duration: int = 0):
        super().__init__(node_id, operator.le, "NIEDRIG", limit, duration)


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
        state["conditions"] = self.conditions
        state["port"] = self.port
        state["repeat"] = self.repeat
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        Alert.__init__(self, state['name'], state['conditions'], state['port'],
                       state['repeat'], _cont=True)

    @property
    def port(self) -> str:
        return self._port

    @port.setter
    def port(self, port: str) -> None:
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

    def _send_alert(self, alert_active: bool, alert_lst: list[str]):
        if self._driver:
            driver = self._driver
            if driver.func == PortFunc.Bout:
                driver.write(100 if alert_active else 0)
                log.info('Alert device "%s" set to %d',
                         driver.name, 100 if alert_active else 0)
            elif driver.func == PortFunc.Tout:
                driver.write(' \n'.join(alert_lst))
                log.info('Alert receiver "%s" will get msg:  "%s"',
                         driver.name, '\n'.join(alert_lst))

    def listen(self, msg: Msg) -> None:
        if isinstance(msg, MsgData) and self._bus:
            log.info("## Alert %s check %.4f from %s",
                     self.name, msg.data, msg.sender)
            any_alert = False
            any_change = False
            self.data = []
            for cond in self.conditions:
                # log.debug('## %s check %s', cond, msg)
                cond_change = cond.check_for_change(msg)
                if cond_change is not None:
                    any_change = True
                any_alert |= cond.alerted

                entry = f'Warnung: {cond}\n{cond.alert_text}'
                if cond.alerted:
                    if cond_change is None:   # is not None and True!
                        entry += '  ... besteht weiterhin'
                else:
                    if cond_change is False:
                        entry += '  ... beseitigt'
                if cond.alerted or cond_change is False:
                    self.data.insert(0, entry)
                log.info(f'## {cond} re-checked: "{cond.alert_text}",\nchange to: {cond_change}')

            if any_alert:
                log.warning('Alerts by %s:\n"%s"', self.name, '\n'.join(self.data))

            self.post(MsgData(self.id, '\n'.join(self.data)))

            now = monotonic()
            if any_change \
            or (self._repeat_time and (now > self._repeat_time)):
                self._send_alert(any_alert, self.data)
                self._repeat_time = now + self.repeat
            elif not any_alert:
                self._repeat_time = None

        super().listen(msg)

    def get_settings(self) -> list[tuple]:
        settings = super().get_settings()
        settings.append(('repeat', 'Wiederholung [s]', self.repeat,
                         'type="number" min="0" max="%d" step="60"' % (24*60*60)))
# ??        for cond in self.conditions:
#            settings.append(('cond.limit', f'{str(cond)} [min]', cond.limit,
#                             'type="number" min="1" max="%d" step="1"'))
        return settings
