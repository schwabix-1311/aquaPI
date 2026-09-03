#!/usr/bin/env python3

from abc import ABC
import logging
from typing import Any
import time
from datetime import date, datetime, time as dt_time, timedelta
from threading import Event, Thread

from .msg_bus import (MsgBus, BusNode, BusRole, DataRange, HeartbeatMixin, MsgData, Setting)
from .port_driver import PortDriverMixin
from ..driver import (DriverReadError, InDriver, PortFunc)


log = logging.getLogger('machineroom.in_nodes')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose


# ========== inputs AKA sensors ==========


class InputNode(PortDriverMixin, BusNode, ABC):
    """ Base class for IN_ENDP delivering measurments,
        e.g. temperature, pH, water level switch
        All use a reader thread, most reading from IoRegistry port
    """
    ROLE = BusRole.IN_ENDP
    _DRIVER_BASE = InDriver
    _PORT_CAPABILITY = 'reading data'

    def __init__(self, name: str, port: str,
                 interval: float = 0.5, _cont: bool = False):
        super().__init__(name, _cont=_cont)
        self._driver: InDriver | None = None
        self._driver_opts = None
        self._port: str = ''
        self._reader_thread: Thread | None = None
        self._reader_stop: bool = False
        self.interval: float = max(0.1, float(interval))
        self.port: str = port

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state["port"] = self.port
        state["interval"] = self.interval
        return state

    def __str__(self) -> str:
        return f'{type(self).__name__}({self.name}/{self.port})'

    def _port_driver_opts(self):
        return self._driver_opts

    def _sync_driver(self) -> None:
        self.data = self.read()

    def plugin(self, bus: MsgBus) -> None:
        super().plugin(bus)
        self._reader_thread = Thread(name=self.id, target=self._reader, daemon=True)
        self._reader_thread.start()

    def pullout(self) -> bool:
        if self._reader_thread:
            self._reader_stop = True
            self._reader_thread.join(timeout=5)
            self._reader_thread = None
        self.port = ''
        return super().pullout()

    def read(self):
        raise NotImplementedError()

    def _reader(self) -> None:
        log.debug('InputNode.reader started')
        next_run = time.time()
        while not self._reader_stop:
            try:
                self.data = self.read()
                self.alert = None
                log.brief('%s: read %r', self.id, self.data)
                self.post(MsgData(self.id, self.data))
            except (DriverReadError, Exception):
                log.exception('Reader exception')
                self.alert = ('Read error!', 'err')
            # sleep against a fixed wall-clock schedule rather than a flat
            # post-read delay, so a slow read() (e.g. DS1820's ~1-2s 1-Wire
            # conversion, blocking inside DriverOneWire.read()) doesn't add
            # on top of the configured interval every single cycle. If a
            # read overran by more than a full interval, skip the missed
            # tick(s) instead of bursting to catch up.
            next_run += self.interval
            now = time.time()
            if next_run < now:
                next_run = now
            time.sleep(next_run - now)

        self._reader_thread = None
        self._reader_stop = False

    def get_settings(self) -> list[Setting]:
        settings = super().get_settings()
        settings.append(self._port_setting('inputPort'))
        schema = {s.key: s for s in type(self).get_settings_schema()}
        settings.append(self._fill_setting(schema['interval']))
        return settings

    @classmethod
    def get_settings_schema(cls) -> list[Setting]:
        schema = super().get_settings_schema()
        schema.append(cls.get_port_schema('inputPort'))
        schema.append(Setting('interval', 'readInterval', 10.0,
                              type='duration', min=1, max=600, step=1))
        return schema


class SwitchInput(InputNode):
    """ A binary input from a port driver like GPIO.
        Port driver is read in a worker thread.

        Options:
            name     - unique name of this input node in UI
            port     - name of a IoRegistry port driver to read input
            interval - delay of reader loop
            inverted - swap the boolean interpretation of input

        Output:
            BINARY (100/0, project convention: 100=True=on) - posts state
            changes only
    """
    data_range = DataRange.BINARY
    _port_funcs = [PortFunc.Bin]

    def __init__(self, name: str, port: str,
                 interval: float = 0.5, inverted: bool = False,
                 _cont: bool = False):
        self.inverted: bool = inverted
        super().__init__(name, port, interval, _cont=_cont)
        self.unit = '%'

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state["inverted"] = self.inverted
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        SwitchInput.__init__(self, state['name'], state['port'],
                             interval=state['interval'], inverted=state['inverted'],
                             _cont=True)

    def read(self) -> int:
        # TODO: reduce load & improve response time by using interrupt-driven IO, either here or in DriverGPIO
        val = self.data > 0
        if self._driver:
            val = bool(self._driver.read())
            log.debug('Bin.read %d', val)
        if self.inverted:
            val = not val
        return 100 if val else 0

    def get_settings(self) -> list[Setting]:
        settings = super().get_settings()
        schema = {s.key: s for s in type(self).get_settings_schema()}
        settings.append(self._fill_setting(schema['inverted']))
        return settings

    @classmethod
    def get_settings_schema(cls) -> list[Setting]:
        schema = super().get_settings_schema()
        # SwitchInput's own constructor default (0.5s) differs from
        # InputNode's shared 'interval' schema entry (10.0s, the majority
        # case for Analog/TextInput) - override just the suggested default.
        schema = [s.with_value(0.5) if s.key == 'interval' else s for s in schema]
        schema.append(Setting('inverted', 'inverted', False, type='checkbox'))
        return schema


class AnalogInput(InputNode):
    """ An analog input for anything read from a port driver.
        Port driver reads measurements in a worker thread.

        Options:
            name     - unique name of this input node in UI
            port     - name of a IoRegistry port driver to read input
            initval  - initial value (for faked drivers!)
            interval - delay of reader loop, conversion time adds to this!
            unit     - unit of posted data
            avg      - floating average, 1=no average, 2..5=depth of averaging

        Output:
            float - posts each change of measurement in driver units
    """
    data_range = DataRange.ANALOG
    _port_funcs = [PortFunc.Ain]

    def __init__(self, name: str, port: str, initval: float, unit: str,
                 interval: float = 10.0, avg: int = 0,
                 _cont: bool = False):
        self.avg = min(max(1, avg), 5)
        super().__init__(name, port, interval, _cont=_cont)
        self.unit = unit
        self.initval = initval
        if initval:
            self._driver_opts = {'initval': initval}
            self.port = self.port  # re-create with initval

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state["initval"] = self.initval
        state["avg"] = self.avg
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        AnalogInput.__init__(self, state['name'], state['port'],
                             state['initval'], state['unit'],
                             interval=state['interval'], avg=state['avg'],
                             _cont=True)

    def read(self) -> float:
        val = self.data
        if self._driver:
            val = float(self._driver.read())
            log.debug('Ain.read %f', val)
        val = (val + self.data * (self.avg - 1)) / self.avg
        val = round(val, 4)
        return val

    def get_settings(self) -> list[Setting]:
        settings = super().get_settings()
        schema = {s.key: s for s in type(self).get_settings_schema()}
        settings.insert(1, self._fill_setting(schema['unit']))
        settings.append(self._fill_setting(schema['avg']))
        return settings

    @classmethod
    def get_settings_schema(cls) -> list[Setting]:
        schema = super().get_settings_schema()
        # 'initval' is creation-only (seeds a faked/simulated driver, see
        # AInDriver.read()) - schema-only, get_settings() above doesn't
        # (and never did) surface it as an editable setting afterward.
        schema.insert(1, Setting('initval', 'initval', 0.0, type='number', creation_only=True))
        schema.insert(2, Setting('unit', 'unit', ''))
        schema.append(Setting('avg', 'avg', 1, type='number', min=1, max=5, step=1))
        return schema


class TextInput(InputNode):
    """ A text input for anything read from a Tin port driver, e.g. a
        now-playing/station name reported by a network audio device.
        Port driver is read in a worker thread.

        Options:
            name     - unique name of this input node in UI
            port     - name of a IoRegistry port driver to read input
            interval - delay of reader loop

        Output:
            STRING - posts each change of the driver-reported text
    """
    data_range = DataRange.STRING
    _port_funcs = [PortFunc.Tin]

    def __init__(self, name: str, port: str,
                 interval: float = 10.0, _cont: bool = False):
        super().__init__(name, port, interval, _cont=_cont)

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        TextInput.__init__(self, state['name'], state['port'],
                           interval=state['interval'], _cont=True)

    def read(self) -> str:
        val = self.data if isinstance(self.data, str) else ''
        if self._driver:
            val = str(self._driver.read())
            log.debug('Tin.read %r', val)
        return val


class ScheduleInput(BusNode):
    """ A scheduler producing a binary (On=100 / Off=0) output on a fixed
        elapsed-time cycle: On for `duration` seconds, Off for the rest
        of every `frequency`-second period, with the first On of each
        cycle pinned to a local time-of-day (`anchor`). Optionally
        restricted to a subset of weekdays.

        This replaced an earlier cron-based implementation (a raw
        'min hour day month weekday' cronspec, driven by croniter) -
        standard cron cannot express a true "every N days" without
        drift (verified: a day-of-month-step approximation silently
        loses a day at every month boundary), since a calendar month's
        length varies but cron's day-of-month field cycles as if it
        didn't. This implementation instead tracks pure elapsed time
        since a fixed reference instant, so any period from a couple of
        seconds up to any number of days is exact, with no calendar
        edge cases and no dependency on when the node was last
        (re)started - see _reference()/_phase().

        Options:
            name      - unique name of this input node in UI
            frequency - length of one full On+Off cycle, seconds (>= MIN_FREQUENCY)
            duration  - length of the On portion of each cycle, seconds;
                        duration >= frequency means permanently On - a
                        valid, deliberate configuration, not an error
            anchor    - local time-of-day ('HH:MM', 24h) at which a
                        cycle boundary (phase 0) falls, e.g. anchor='14:00'
                        with frequency=1 day means "On from 14:00 for
                        `duration` seconds, every day"
            weekdays  - None/empty = every day; else a set/list of
                        weekday numbers (Python's own datetime.weekday()
                        convention, Monday=0..Sunday=6) restricting which
                        days the independently phase-gated On state may
                        actually be reported

        Output:
            posts a single 100 at start time, a single 0 at end time.
    """
    ROLE = BusRole.IN_ENDP
    data_range = DataRange.BINARY

    # max sleep chunk in the scheduler thread, so pullout() and a live
    # settings change (see _wake) are both noticed promptly
    STOP_DURATION = 2
    # a plain constant now, with no algorithmic meaning attached (unlike
    # the old cron model's "2 ticks" floor, which was tied to its
    # tick-concatenation logic) - adjust freely if a different
    # hardware-safety floor is ever wanted
    MIN_FREQUENCY = 1.0

    # fixed reference date for phase 0 - see _reference()
    _REF_DATE = date(2000, 1, 1)

    def __init__(self, name: str, frequency: float, duration: float,
                 anchor: str = '00:00', weekdays: Any = None,
                 _cont: bool = False):
        super().__init__(name, _cont=_cont)
        self._scheduler_thread: Thread | None = None
        self._scheduler_stop: bool = False
        # the scheduler thread sleeps by waiting on this instead of a
        # plain time.sleep(), so both pullout() and a live property
        # change (setters below) interrupt a long sleep immediately -
        # deliberately NOT the old cronspec pattern of stop+join+restart
        # the whole thread on every change: with 4 independent fields, a
        # single /settings PUT changing several at once would otherwise
        # block the request for up to STOP_DURATION seconds *per changed
        # field* while join()ing the old thread each time.
        self._wake = Event()
        self.anchor = anchor
        self.frequency = frequency
        self.duration = duration
        self.weekdays = weekdays
        if not _cont:
            self.data: int = 0
        self.unit = '%'

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state["frequency"] = self.frequency
        state["duration"] = self.duration
        state["anchor"] = self.anchor
        state["weekdays"] = sorted(self.weekdays) if self.weekdays else None
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        ScheduleInput.__init__(self, state['name'], state['frequency'], state['duration'],
                               anchor=state['anchor'], weekdays=state['weekdays'], _cont=True)

    def __str__(self) -> str:
        return (f'{type(self).__name__}({self.name}/every {self.frequency}s '
                f'for {self.duration}s from {self.anchor})')

    @property
    def anchor(self) -> str:
        return self._anchor

    @anchor.setter
    def anchor(self, value: str) -> None:
        try:
            h_str, m_str = str(value).split(':')
            h, m = int(h_str), int(m_str)
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
        except (ValueError, AttributeError):
            raise ValueError(f"anchor must be 'HH:MM' (24h), got {value!r}")
        self._anchor = f'{h:02d}:{m:02d}'
        self._anchor_hm = (h, m)
        self._wake.set()

    @property
    def frequency(self) -> float:
        return self._frequency

    @frequency.setter
    def frequency(self, value: float) -> None:
        self._frequency = max(self.MIN_FREQUENCY, float(value))
        self._wake.set()

    @property
    def duration(self) -> float:
        return self._duration

    @duration.setter
    def duration(self, value: float) -> None:
        self._duration = max(0.0, float(value))
        self._wake.set()

    @property
    def weekdays(self) -> set[int] | None:
        return self._weekdays

    @weekdays.setter
    def weekdays(self, value: Any) -> None:
        if not value:
            self._weekdays = None
        else:
            days = {int(d) for d in value}
            if not days <= set(range(7)):
                raise ValueError(f'weekdays must each be 0..6 (Mon..Sun), got {value!r}')
            self._weekdays = days
        self._wake.set()

    def plugin(self, bus: MsgBus) -> None:
        super().plugin(bus)
        self._start_thread()

    def pullout(self) -> bool:
        self._stop_thread()
        return super().pullout()

    def _start_thread(self) -> None:
        if self._bus:
            self._scheduler_stop = False
            self._scheduler_thread = Thread(name=self.id, target=self._scheduler, daemon=True)
            self._scheduler_thread.start()

    def _stop_thread(self) -> None:
        if self._scheduler_thread:
            self._scheduler_stop = True
            self._wake.set()
            self._scheduler_thread.join()
            self._scheduler_thread = None

    def _reference(self) -> datetime:
        """ the NAIVE local instant of `anchor` on the fixed _REF_DATE -
            phase 0 of the schedule.

            Deliberately naive (no tzinfo), compared below against
            `now` with its own tzinfo stripped - i.e. phase is computed
            from plain wall-clock fields, not real elapsed absolute
            time. This isn't a shortcut - it's the only technique that
            actually keeps `anchor` meaning the same wall-clock reading
            every day, indefinitely.

            An earlier version of this method built an aware reference
            instead (correctly resolving _REF_DATE's own UTC offset via
            a bare .astimezone() call on the naive value) and computed
            phase from real elapsed absolute seconds since it. That is
            NOT equivalent to "same wall-clock time daily": verified
            directly - with _REF_DATE fixed in winter (CET, UTC+1) and
            "now" in summer (CEST, UTC+2), the absolute-seconds approach
            came out exactly one hour off from the stated anchor, e.g.
            an anchor='14:00' node reporting itself at phase 0 (i.e.
            "exactly at 14:00") when the real wall clock read 15:00.
            That's not a rare edge case - it's a permanent, systematic
            error for as long as "now" and _REF_DATE sit in different
            DST regimes, which is roughly half of every year.

            The naive/wall-clock approach's own tradeoff is smaller and
            far more standard: on the one or two calendar days a year
            the local clock actually jumps, a moment near the jump can
            read as skipped (spring forward) or repeated (fall back) -
            a well-understood, once-a-year discontinuity, not a
            systematic one. This is the same tradeoff every wall-clock
            scheduler already makes, including the cron/croniter
            implementation this one replaces (matching cron field
            values against local time is likewise a wall-clock, not an
            elapsed-absolute-time, operation).
        """
        h, m = self._anchor_hm
        return datetime.combine(self._REF_DATE, dt_time(h, m))

    def _phase(self, now: datetime) -> float:
        """ seconds elapsed into the current cycle, 0 <= phase < frequency.
            A pure function of `now` (and this node's settings) - no
            thread/sleep involved, so this and _is_on()/
            _seconds_to_next_wake() below are directly unit-testable
            with fixed datetimes, and are exact after any restart: the
            on/off state never depends on when the node itself was
            created/last (re)started, only on `now`'s own wall-clock
            reading relative to the fixed _reference().
        """
        elapsed = (now.replace(tzinfo=None) - self._reference()).total_seconds()
        return elapsed % self._frequency

    def _is_on(self, now: datetime) -> bool:
        """ the on/off state at a given instant, weekday gate included """
        on = self._phase(now) < self._duration
        if self._weekdays is not None:
            on = on and now.weekday() in self._weekdays
        return on

    def _seconds_to_next_local_midnight(self, now: datetime) -> float:
        now_naive = now.replace(tzinfo=None)
        next_midnight = datetime.combine(now_naive.date() + timedelta(days=1), dt_time(0, 0))
        return (next_midnight - now_naive).total_seconds()

    def _seconds_to_next_wake(self, now: datetime) -> float:
        """ how long the scheduler thread may sleep before it must
            re-evaluate _is_on() again: the next phase transition, or -
            while a weekday filter is active - the next local midnight
            if that comes sooner. The phase math alone has no reason to
            transition at every midnight (e.g. frequency=1 day has
            exactly one transition per day), but the *weekday* gate must
            also flip there.
        """
        phase = self._phase(now)
        wake = (self._duration - phase) if phase < self._duration else (self._frequency - phase)
        if self._weekdays is not None:
            wake = min(wake, self._seconds_to_next_local_midnight(now))
        return max(0.0, wake)

    def _scheduler(self) -> None:
        log.brief('ScheduleInput %s: start', self.id)
        try:
            while not self._scheduler_stop:
                self._wake.clear()
                now = datetime.now().astimezone()  # = local tz, this enables DST
                new_data = 100 if self._is_on(now) else 0
                if new_data != self.data:
                    self.data = new_data
                    log.info('ScheduleInput %s: output %d', self.id, self.data)
                    self.post(MsgData(self.id, self.data))

                remaining = self._seconds_to_next_wake(now)
                while remaining > 0 and not self._scheduler_stop:
                    chunk = min(self.STOP_DURATION, remaining)
                    if self._wake.wait(chunk):
                        break  # a setting changed (or pullout()) - recompute from the top
                    remaining -= chunk
        finally:
            self._scheduler_thread = None
            self._scheduler_stop = False
            log.brief('ScheduleInput %s: end', self.id)

    def get_settings(self) -> list[Setting]:
        settings = super().get_settings()
        schema = {s.key: s for s in type(self).get_settings_schema()}
        settings.append(self._fill_setting(schema['frequency']))
        settings.append(self._fill_setting(schema['duration']))
        settings.append(self._fill_setting(schema['anchor']))
        settings.append(schema['weekdays'].with_value(
            [str(d) for d in sorted(self.weekdays)] if self.weekdays else []))
        return settings

    @classmethod
    def get_settings_schema(cls) -> list[Setting]:
        schema = super().get_settings_schema()
        schema.append(Setting('frequency', 'frequency', 86400, type='duration',
                              min=cls.MIN_FREQUENCY))
        schema.append(Setting('duration', 'duration', 3600, type='duration', min=0))
        schema.append(Setting('anchor', 'anchor', '00:00', type='time'))
        schema.append(Setting('weekdays', 'weekdays', [], type='multiselect',
                              options=[str(i) for i in range(7)], optional=True))
        return schema


# ========== user-driven virtual inputs ==========


class UiInput(HeartbeatMixin, BusNode, ABC):
    """ Base for nodes whose value is set directly by the user via
        get_settings()/PUT .../settings (dashboard or /settings), not
        read from a hardware/simulated port driver. Posts MsgData
        immediately when set, plus a periodic heartbeat (see HeartbeatMixin)
        since nobody touching the widget for a long time is the normal
        case, not an exception.
    """
    ROLE = BusRole.IN_ENDP

    def plugin(self, bus: MsgBus) -> None:
        super().plugin(bus)
        self._start_heartbeat()

    def pullout(self) -> bool:
        self._stop_heartbeat()
        return super().pullout()

    @property
    def value(self):
        return self.data

    @value.setter
    def value(self, val) -> None:
        self.data = val
        self.post(MsgData(self.id, self.data))


class UiSwitchInput(UiInput):
    """ A checkbox the user sets directly, e.g. from a dashboard
        widget - for direct manual control, testing, or overriding
        automation.

        Options:
            name    - unique name of this input in UI
            initval - initial state

        Output:
            BINARY (100/0, project convention: 100=True=on) - posts on
            every change. value/get_settings() present this as a plain
            bool for the checkbox widget; self.data/MsgData stay 100/0
            like every other BINARY-range sender (e.g. ThresholdCtrl),
            so downstream *Device nodes' `data > 50` checks keep working
            without needing to special-case a sender-specific type.
    """
    data_range = DataRange.BINARY

    def __init__(self, name: str, initval: bool = False, _cont: bool = False):
        super().__init__(name, _cont=_cont)
        if not _cont:
            self.data = 100 if initval else 0

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        UiSwitchInput.__init__(self, state['name'], _cont=True)

    @property
    def value(self) -> bool:
        return self.data > 0

    @value.setter
    def value(self, val: bool) -> None:
        self.data = 100 if val else 0
        self.post(MsgData(self.id, self.data))

    def get_settings(self) -> list[Setting]:
        settings = super().get_settings()
        # label is a placeholder here - the frontend overrides it with
        # this node's own name for this specific Setting, mirroring the
        # Dashboard widget (see NodeSettingsFields' settings computed)
        schema = {s.key: s for s in type(self).get_settings_schema()}
        settings.append(self._fill_setting(schema['value']))
        return settings

    @classmethod
    def get_settings_schema(cls) -> list[Setting]:
        schema = super().get_settings_schema()
        # 'initval' is creation-only - consumed once into self.data, never
        # stored back, so it can't be (and never was) part of get_settings().
        # 'value' is the live toggle itself - meant to be flipped one at a
        # time (Dashboard widget, or /settings' own per-field PUT), never
        # through /config's batched create/edit dialog, see Setting.live_only.
        schema.append(Setting('initval', 'initval', False, type='checkbox', creation_only=True))
        schema.append(Setting('value', 'value', type='checkbox', live_only=True))
        return schema


class UiAnalogInput(UiInput):
    """ A numeric slider the user sets directly, e.g. from a dashboard
        widget - for a manual setpoint override or a simulated input
        for testing. Posts its value on every change.

        Options:
            name    - unique name of this input in UI
            unit    - unit of posted data
            initval - initial value
            vmin    - lower bound offered by the slider/settings widget
            vmax    - upper bound offered by the slider/settings widget
            step    - step size offered by the slider/settings widget

        Output:
            float - posts on every change
    """
    data_range = DataRange.ANALOG

    def __init__(self, name: str, unit: str = '', initval: float = 0.0,
                 vmin: float = 0.0, vmax: float = 100.0, step: float = 1.0,
                 _cont: bool = False):
        super().__init__(name, _cont=_cont)
        self.unit = unit
        self.min = vmin
        self.max = vmax
        self.step = step
        if not _cont:
            self.data = float(initval)

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state["min"] = self.min
        state["max"] = self.max
        state["step"] = self.step
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        UiAnalogInput.__init__(self, state['name'], unit=state['unit'],
                               vmin=state['min'], vmax=state['max'],
                               step=state['step'], _cont=True)

    def get_settings(self) -> list[Setting]:
        settings = super().get_settings()
        # label is a placeholder here - the frontend overrides it with
        # this node's own name for this specific Setting, mirroring the
        # Dashboard widget (see NodeSettingsFields' settings computed)
        schema = {s.key: s for s in type(self).get_settings_schema()}
        settings.append(schema['value'].with_value(float(self.value),
                        min=self.min, max=self.max, step=self.step))
        settings.append(self._fill_setting(schema['min']))
        settings.append(self._fill_setting(schema['max']))
        settings.append(self._fill_setting(schema['step']))
        return settings

    @classmethod
    def get_settings_schema(cls) -> list[Setting]:
        schema = super().get_settings_schema()
        # 'initval'/'unit' are creation-only - like UiSwitchInput's initval,
        # never exposed as an editable setting afterward (unlike
        # AnalogInput, this unit is never even read back into get_settings()
        # today). 'value' is the live slider itself - see Setting.live_only,
        # same reasoning as UiSwitchInput's own 'value'.
        schema.append(Setting('initval', 'initval', 0.0, type='number', creation_only=True))
        schema.append(Setting('unit', 'unit', '', creation_only=True))
        schema.append(Setting('value', 'value', type='number', live_only=True))
        # keyed 'min'/'max'/'step' (not the constructor's 'vmin'/'vmax') to
        # match the real attribute names - the /settings PUT handler does a
        # plain setattr(node, key, value).
        schema.append(Setting('min', 'minimum', 0.0, type='number'))
        schema.append(Setting('max', 'maximum', 100.0, type='number'))
        schema.append(Setting('step', 'step', 1.0, type='number'))
        return schema
