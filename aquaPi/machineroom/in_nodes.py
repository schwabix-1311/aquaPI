#!/usr/bin/env python3

from abc import ABC
import logging
from typing import Any
import time
from datetime import datetime
from croniter import croniter
from threading import Thread

from .msg_bus import (MsgBus, BusNode, BusRole, DataRange, MsgData)
from ..driver import (IoRegistry, DriverReadError, InDriver)


log = logging.getLogger('machineroom.in_nodes')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose


# ========== inputs AKA sensors ==========


class InputNode(BusNode, ABC):
    """ Base class for IN_ENDP delivering measurments,
        e.g. temperature, pH, water level switch
        All use a reader thread, most reading from IoRegistry port
    """
    ROLE = BusRole.IN_ENDP

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
        state.update(port=self.port)
        state.update(interval=self.interval)
        return state

    # def __setstate__(self, state: dict[str, Any]) -> None:
    #     self.data = state['data']
    #     InputNode.__init__(self, state, _cont=True)

    def __str__(self) -> str:
        return '{}({})'.format(type(self).__name__, self.port)

    @property
    def port(self) -> str:
        return self._port

    @port.setter
    def port(self, port: str) -> None:
        if self._driver:
            IoRegistry.get().driver_destruct(self._port, self._driver)
        if port:
            driver = IoRegistry.get().driver_factory(port, self._driver_opts)
            if isinstance(driver, InDriver):
                self._driver = driver
            else:
                log.error('Port %s does not support reading data. %s will be ignored.',
                          port, self.name)
        self._port = port

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
        while not self._reader_stop:
            try:
                val = self.read()
                self.alert = None
                if self.data != val or True:
                    self.data = val
                    log.brief('%s: read %f', self.id, self.data)
                    self.post(MsgData(self.id, self.data))
            except (DriverReadError, Exception):
                log.exception('Reader exception')
                self.alert = ('Read error!', 'err')
            time.sleep(self.interval)

        self._reader_thread = None
        self._reader_stop = False

    def get_settings(self) -> list[tuple]:
        settings = super().get_settings()
        settings.append(('port', 'Input port',
                         self.port, 'type="text"'))
        settings.append(('interval', 'Leseintervall [s]',
                         self.interval, 'type="number" min="1" max="600" step="1"'))
        return settings


class SwitchInput(InputNode):
    """ A binary input from a port driver like GPIO.
        Port driver is read in a worker thread.

        Options:
            name     - unique name of this input node in UI
            port     - name of a IoRegistry port driver to read input
            interval - delay of reader loop
            inverted - swap the boolean interpretation of input

        Output:
            bool - posts state changes only
    """
    data_range = DataRange.BINARY

    def __init__(self, name: str, port: str, 
                 interval: float = 0.5, inverted: bool = False,
                 _cont: bool = False):
        super().__init__(name, port, interval, _cont=_cont)
        self.inverted: bool = inverted
        ##self.unit = '⏻'

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state.update(inverted=self.inverted)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        SwitchInput.__init__(self, state['name'], state['port'],
                             interval=state['interval'], inverted=state['inverted'],
                             _cont=True)

    def read(self) -> bool:
        val = self.data
        # TODO: reduce load & improve response time by using interrupt-driven IO, either here or in DriverGPIO
        if self._driver:
            val = bool(self._driver.read())
            log.debug('Bin.read %f', val)
        if self.inverted:
            val = not val
        return val

    def get_settings(self) -> list[tuple]:
        settings = super().get_settings()
        settings.append(('inverted', 'Invertiert', self.inverted))
        return settings


class AnalogInput(InputNode):
    """ An analog input for anything read from a port driver.
        Port driver reads measurements in a worker thread.

        Options:
            name     - unique name of this input node in UI
            port     - name of a IoRegistry port driver to read input
            initval  - initial value (for faked drivers!)
            interval - delay of reader loop, conversion time adds to this!
            unit     - unit of measurement for labels
            avg      - floating average, 1=no average, 2..5=depth of averaging

        Output:
            float - posts each change of measurement in driver units
    """
    data_range = DataRange.ANALOG

    def __init__(self, name: str, port: str, initval: float, unit: str,
                 interval: float = 10.0, avg: int = 0,
                 _cont: bool = False):
        super().__init__(name, port, interval, _cont=_cont)
        self.initval = initval
        if initval:
            self._driver_opts = {'initval': initval}
            self.port = self.port  # re-create with new opts!
        self.unit = unit
        self.avg = min(max(1, avg), 5)

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state.update(initval=self.initval)
        state.update(avg=self.avg)
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

    def get_settings(self) -> list[tuple]:
        settings = super().get_settings()
        settings.append(('unit', 'Einheit',
                         self.unit, 'type="text"'))
        settings.append(('avg', 'Mittelwert [1=direkt]',
                         self.avg, 'type="number" min="1" max="5" step="1"'))
        return settings


class ScheduleInput(BusNode):
    """ A scheduler supporting monthly/weekly/daily/hourly(/per minute)
        trigger output (On=100 / Off=0).
        Internally working like cron; a spec is 'min hour day month weekday'.
        In contrast to cron we concatenate events to a long ON state,
        i,e.  '20-24 9 * * *' outputs 100 at 9:20 and 0 at 9:24,
        while '20,24 9 * * *' posts 100 at 9:20 & 9:24, and 0 at 9:21 & 9:25.
        Highres cron is supported, where a sixth field defines seconds, and the
        internal time base ("tick") changes from 1 minute to 1 second.
        NOTE: the concatenation makes shortest time between pulses 2min or 2sec

        Options:
            name     - unique name of this input node in UI
            cronspec - a cron-style definition with 5 or 6 fields

        Output:
            posts a single 100 at start time, a single 0 at end time.
    """
    # TODO: since cron specs are not always intuitive, and require more than 1 cron line to start or end long events at an odd minute (not yet supported!), this class should get simple start/end/repeat options.

    ROLE = BusRole.IN_ENDP
    data_range = DataRange.BINARY

    # time [s] to stop the scheduler thread
    STOP_DURATION = 2
    # This limits CPU usage to find rare events with long gaps,
    # such as '0 4 1 1 fri' = Jan. 1st 4pm and Friday -> very rare!
    CRON_YEARS_DEPTH = 2

    def __init__(self, name: str, cronspec: str, _cont: bool = False):
        super().__init__(name, _cont=_cont)
        self._scheduler_thread: Thread | None = None
        self._scheduler_stop: bool = False
        self.cronspec = cronspec
        self.hires: bool = len(cronspec.split(' ')) > 5
        if not _cont:
            self.data: int = 0
        ##self.unit = '⏻'

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state.update(cronspec=self.cronspec)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        ScheduleInput.__init__(self, state['name'], state['cronspec'], _cont=True)

    def __str__(self) -> str:
        return '{}({})'.format(type(self).__name__, self.cronspec)

    @property
    def cronspec(self) -> str:
        return self._cronspec

    @cronspec.setter
    def cronspec(self, cronspec: str) -> None:
        # validate it here, since the exception would be raised in our thread.
        now = datetime.now().astimezone()  # = local tz, this enables DST
        croniter(cronspec, now, day_or=False,
                 max_years_between_matches=self.CRON_YEARS_DEPTH)

        self._stop_thread()
        self._cronspec = cronspec
        self._start_thread()

    def plugin(self, bus: MsgBus) -> None:
        super().plugin(bus)
        self._start_thread()

    def pullout(self) -> bool:
        self._stop_thread()
        return super().pullout()

    def _start_thread(self) -> None:
        if self._bus:
            self._scheduler_thread = Thread(name=self.id, target=self._scheduler, daemon=True)
            self._scheduler_thread.start()

    def _stop_thread(self) -> None:
        if self._scheduler_thread:
            self._scheduler_stop = True
            self._scheduler_thread.join()
            self._scheduler_thread = None

    def _scheduler(self) -> None:
        log.brief('ScheduleInput %s: start', self.id)

        now = datetime.now().astimezone()  # = local tz, this enables DST
        cron = croniter(self._cronspec, now, ret_type=float, day_or=False,
                        max_years_between_matches=self.CRON_YEARS_DEPTH)
        tick = 1 if self.hires else 60
        log.debug(' now  %s = %f, 1 tick = %d s', now, time.time(), tick)

        try:
            cron.get_next()
            while True:
                sec_now: float = time.time()  # reference for each loop to avoid drift
                sec_prev: float = cron.get_prev()  # look one event back
                log.debug(' prev %s = %f',
                          str(cron.get_current(ret_type=datetime)),
                          sec_prev - sec_now)

                sec_next: float = cron.get_next()  # seconds 'til future cron event
                log.debug(' next %s = %f',
                          str(cron.get_current(ret_type=datetime)),
                          sec_next - sec_now)

                if self._scheduler_stop:
                    return  # cleanup is done in finally!

                if sec_next - sec_prev > tick:
                    # as we concatenate events <1 tick apart, must be a pause
                    self.data = 0
                    log.info('ScheduleInput %s: output 0 for %f s',
                             self.id, sec_next - sec_now)
                    self.post(MsgData(self.id, self.data))

                    # while (sec_next > time.time()):
                    while (sec_next - time.time() > self.STOP_DURATION):
                        time.sleep(self.STOP_DURATION)
                        if self._scheduler_stop:
                            return  # cleanup is done in finally!

                # now look how many ticks to concatenate
                while True:
                    candidate = cron.get_next()
                    log.debug('  ? %s = + %f s',
                              str(cron.get_current(ret_type=datetime)),
                              candidate - sec_next)
                    if candidate - sec_next > tick:
                        log.debug('  ... busted!')
                        break
                    sec_next = candidate

                if self._scheduler_stop:
                    return  # cleanup is done in finally!

                self.data = 100
                log.info('ScheduleInput %s: output 100 for %f s',
                         self.id, sec_next - time.time())
                self.post(MsgData(self.id, self.data))

                while (sec_next > time.time()):
                    time.sleep(self.STOP_DURATION)
                    if self._scheduler_stop:
                        return  # cleanup is done in finally!
        finally:
            # turn off? Probably not, to avoid flicker when schedule is changed
            self._scheduler_thread = None
            self._scheduler_stop = False
            log.brief('ScheduleInput %s: end', self.id)

    def get_settings(self) -> list[tuple]:
        settings = super().get_settings()
        settings.append(('cronspec', 'CRON (m h DoM M DoW)',
                         self.cronspec, 'type="text"'))
        return settings
