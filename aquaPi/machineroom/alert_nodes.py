#!/usr/bin/env python3

from abc import ABC, abstractmethod
import logging
from typing import Any, Callable
import operator
from time import monotonic

from .msg_types import (Msg, MsgData)
from .msg_bus import (BusListener, BusRole, DataRange, Setting)
from .port_driver import PortDriverMixin
from ..driver import (IoRegistry, PortFunc, OutDriver)
from .. import db


log = logging.getLogger('machineroom.alert_nodes')


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
    def _text(self, msg: MsgData, snd_name: str) -> str:
        """ build a human redable alert text
        """

    def check_for_change(self, msg: Msg, snd_name: str) -> bool | None:
        """ Check for change in alert status, update alert_text,
            return state changed to, or None if inappropriate msg or no change
        """
        if isinstance(msg, MsgData) and msg.sender == self.node_id:
            old = self._alerted
            self._alerted = self._check(msg)
            self._alert_text = self._text(msg, snd_name)

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
            if self._starttime is None:
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

    def _text(self, msg: MsgData, snd_name: str) -> str:
        if self.alerted:
            if self.duration:
                minutes = (monotonic() - self._starttime) / 60
                return (f'{snd_name}: Messwert zu {self._direction}: '
                        f'{msg.data:.2f} seit {minutes:.1f} min'
                        f'  [Grenzwert {self.limit:.2f} für max. {self.duration} min]')
            else:
                return (f'{snd_name}: Messwert zu {self._direction}: '
                        f'{msg.data:.2f}  [Grenzwert {self.limit:.2f}]')
        else:
            return (f'{snd_name}: Messwert OK: '
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


class Alert(PortDriverMixin, BusListener):
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
    _port_funcs = [PortFunc.Tout]
    _DRIVER_BASE = OutDriver
    _PORT_CAPABILITY = 'writing alert messages'
    _receives_kind = 'multi'

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
        # Step 28: track how long an alert has been continuously active,
        # to notify a 2nd, escalation channel once it stays unresolved
        # longer than the admin-configured 'escalation_after_minutes'
        self._alert_since: float | None = None
        self._escalated: bool = False

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state["conditions"] = self.conditions
        state["port"] = self.port
        state["repeat"] = self.repeat
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        Alert.__init__(self, state['name'], state['conditions'], state['port'],
                       state['repeat'], _cont=True)

    def _send_alert(self, alert_active: bool, alert_lst: list[str]):
        text = ' \n'.join(alert_lst)
        if self._driver:
            driver = self._driver
            if driver.func == PortFunc.Bout:
                driver.write(100 if alert_active else 0)
                log.verbose('Alert device "%s" set to %d',
                            driver.name, 100 if alert_active else 0)
            elif driver.func == PortFunc.Tout:
                driver.write(text)
                log.verbose('Alert receiver "%s" will get msg:  "%s"',
                            driver.name, '\n'.join(alert_lst))

    def _notify_escalation(self, port_name: str, text: str) -> None:
        """ send an escalation message to a specific IoRegistry port, never
            raising - a missing/misconfigured driver must never break the
            alert loop.
        """
        try:
            driver = IoRegistry.get().driver_factory(port_name)
        except Exception:
            log.error('No port %r available for escalation of alert %s', port_name, self.id)
            return

        try:
            if isinstance(driver, OutDriver) and driver.func == PortFunc.Tout:
                driver.write(f'[ESKALATION] {text}')
                log.verbose('Alert %s escalated via %s', self.id, port_name)
        except Exception:
            log.exception('Failed to escalate alert %s via %s', self.id, port_name)
        finally:
            IoRegistry.get().driver_destruct(port_name, driver)

    def _check_escalation(self, now: float, text: str) -> None:
        """ Step 28: independently of the repeat/'any_change' throttling
            used for the primary notification, check on every message
            whether the shared, admin-configured escalation channel needs
            to be notified because the alert has been continuously active
            for at least its 'escalation_after_minutes'. Fires at most
            once per continuously-active episode (self._escalated, reset
            once the alert clears).
        """
        if self._alert_since is None or self._escalated:
            return

        users_db_path = db.get_current_users_db_path()
        if not users_db_path:
            return

        try:
            config = db.get_escalation_config(users_db_path, self.id)
        except Exception:
            log.exception('Failed to read escalation config for alert %s', self.id)
            return
        if not config:
            return

        escalation_channel = config.get('escalation_channel') or 'none'
        escalation_after = config.get('escalation_after_minutes') or 0
        active_minutes = (now - self._alert_since) / 60
        if (escalation_channel not in ('none', self.port)
                and escalation_after > 0 and active_minutes >= escalation_after):
            self._notify_escalation(escalation_channel, text)
            self._escalated = True

    @staticmethod
    def _format_entry(cond: AlertCond, cond_change: bool | None) -> str | None:
        """ Build this condition's display/notification entry for the
            current state (new/ongoing alert, or just-resolved), or None
            if it shouldn't be shown at all (not alerted, no change now).
        """
        if cond.alerted:
            suffix = '  ... besteht weiterhin' if cond_change is None else ''
            return f'Warnung: {cond}\n{cond.alert_text}{suffix}'
        if cond_change is False:
            return f'Entwarnung: {cond}\n{cond.alert_text}  ... beseitigt'
        return None

    def listen(self, msg: Msg) -> None:
        if isinstance(msg, MsgData) and self._bus:
            snd_name = self._bus.get_node(msg.sender).name or msg.sender
            log.verbose("## Alert %s check %.4f from %s",
                        self.name, msg.data, snd_name)
            any_alert = False
            any_change = False
            self.data = []
            for cond in self.conditions:
                # log.debug('## %s check %s', cond, msg)
                cond_change = cond.check_for_change(msg, snd_name)
                if cond_change is not None:
                    any_change = True
                any_alert |= cond.alerted

                entry = self._format_entry(cond, cond_change)
                if entry:
                    self.data.append(entry)
                log.verbose(f'## {cond} re-checked: "{cond.alert_text}",\nchange to: {cond_change}')

            if any_alert:
                log.warning('Alerts by %s:\n"%s"', self.name, '\n'.join(self.data))

            self.post(MsgData(self.id, '\n'.join(self.data)))

            now = monotonic()
            if any_alert:
                if self._alert_since is None:
                    self._alert_since = now
                self._check_escalation(now, '\n'.join(self.data))
            else:
                self._alert_since = None
                self._escalated = False

            if any_change \
                    or (self._repeat_time and (now > self._repeat_time)):
                self._send_alert(any_alert, self.data)
                self._repeat_time = now + self.repeat
            elif not any_alert:
                self._repeat_time = None

        super().listen(msg)

    def get_settings(self) -> list[Setting]:
        settings = super().get_settings()
        settings.append(self._port_setting('alertPort'))
        schema = {s.key: s for s in type(self).get_settings_schema()}
        settings.append(self._fill_setting(schema['repeat']))
        return settings

    @classmethod
    def get_settings_schema(cls) -> list[Setting]:
        schema = super().get_settings_schema()
        schema.append(cls.get_port_schema('alertPort'))
        schema.append(Setting('repeat', 'repeat', 60 * 60,
                              type='duration', min=0, max=24*60*60, step=60))
        return schema
