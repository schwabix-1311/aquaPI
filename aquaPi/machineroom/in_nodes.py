#!/usr/bin/env python3

import logging
import time
from datetime import datetime
from croniter import croniter
from threading import Thread

from .msg_bus import (BusNode, BusRole, MsgData)
from ..driver import (PortFunc, io_registry, DriverReadError)


log = logging.getLogger('InNodes')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


# ========== inputs AKA sensors ==========


class InputNode(BusNode):
    """ Base class for IN_ENDP delivering measurments,
        e.g. temperature, pH, water level switch
    """
    ROLE = BusRole.IN_ENDP

    # def __getstate__(self):
    #    return super().__getstate__()

    # def __setstate__(self, state):
    #    self.__init__(state, _cont=True)


class AnalogInput(InputNode):
    """ An analog input for anything read from a port driver.
        Just name and labels auto-adjust to unit (for the known ones).
        Measurements taken in a worker thread$.

        Options:
            name     - unique name of this input node in UI
            port     - name of a IoRegistry port driver to read input
            interval - delay of reader loop, reader conversion time adds to this!
            unit     - unit of measurement for labels
            avg      - floating average, with 1=no average, 2..5=depth of averaging

        Output:
            float - posts stream of measurement in driver units, unchanged measurements are suppressed
    """

    def __init__(self, name, port, interval=10.0, unit='°C', avg=0, _cont=False):
        super().__init__(name, _cont=_cont)
        self._driver = None
        self.interval = min(1., float(interval))
        self.unit = unit
        self.avg = min(max(1, avg), 5)
        self._reader_thread = None
        self._reader_stop = False
        self.port = port
        self.data = self._driver.read()

    def __getstate__(self):
        state = super().__getstate__()
        state.update(port=self.port)
        state.update(interval=self.interval)
        state.update(avg=self.avg)
        log.debug('< AnalogInput.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('AnalogInput.setstate %r', state)
        self.__init__(state['name'], state['port'], interval=state['interval'], unit=state['unit'], avg=state['avg'],
                      _cont=True)

    def __str__(self):
        return '{}({})'.format(type(self).__name__, self.port)

    @property
    def port(self):
        return self._port

    @port.setter
    def port(self, port):
        if self._driver:
            io_registry.driver_release(self.port)
        self._driver = io_registry.driver_factory(port, PortFunc.ADC)
        self._port = port

    def plugin(self, bus):
        super().plugin(bus)
        self._reader_thread = Thread(name=self.id, target=self._reader, daemon=True)
        self._reader_thread.start()

    def pullout(self):
        if self._reader_thread:
            self._reader_stop = True
            self._reader_thread.join(timeout=5)
            self._reader_thread = None
        super().pullout()

    def _reader(self):
        log.debug('AnalogInput.reader started')
        self.data = 0  # ? None
        while not self._reader_stop:
            log.debug('AnalogInput.reader looping %r', self.data)
            try:
                val = self.data
                if self._driver:
                    val = self._driver.read()
                    val = (val + self.data * (self.avg - 1)) / self.avg
                    val = round(val, 2)
                    self.alert = None
                if self.data != val:
                    self.data = val
                    log.brief('AnalogInput %s: output %f', self.id, self.data)
                    self.post(MsgData(self.id, self.data))
            except DriverReadError:
                self.alert = ('Read error!', 'err')

            time.sleep(self.interval)
        self._reader_thread = None
        self._reader_stop = False

    def get_settings(self):
        settings = super().get_settings()
        settings.append(('unit', 'Einheit', self.unit, 'type="text"'))
        settings.append(('avg', 'Mittelwert [1=direkt]', self.avg, 'type="number" min="1" max="5" step="1"'))
        settings.append(('port', 'Input', self.port, 'type="text"'))
        return settings


class ScheduleInput(BusNode):
    """ A scheduler supporting monthly/weekly/daily/hourly(/per minute)
        trigger output (On=100 / Off=0).
        Internally working like cron; a spec is 'min hour day month weekday'.
        In contrast to cron we concatenate consecutive events to a long ON state,
        i,e.  '20-24 9 * * *' outputs 100 at 9:20 and 0 at 9:24,
        while '20,24 9 * * *' results in 100 at 9:20 & 9:24, and 0 at 9:21 & 9:25.
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
    # time [s] to stop the scheduler thread
    STOP_DURATION = 2
    # This limits CPU usage to find rare events with long gaps,
    # such as '0 4 1 1 fri' = Jan. 1st 4pm and Friday -> very rare!
    CRON_YEARS_DEPTH = 2

    def __init__(self, name, cronspec, _cont=False):
        super().__init__(name, _cont=_cont)
        self._scheduler_thread = None
        self._scheduler_stop = False
        self.cronspec = cronspec
        self.hires = len(cronspec.split(' ')) > 5
        if not _cont:
            self.data = 0
        self.unit = '%'

    def __getstate__(self):
        state = super().__getstate__()
        state.update(cronspec=self.cronspec)
        log.debug('ScheduleInput.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('ScheduleInput.setstate %r', state)
        self.data = state['data']
        self.__init__(state['name'], state['cronspec'], _cont=True)

    @property
    def cronspec(self):
        return self._cronspec

    @cronspec.setter
    def cronspec(self, cronspec):
        # validate it here, since the exception would be raised in our thread.
        now = datetime.now().astimezone()  # = local tz, this enables DST
        croniter(cronspec, now, day_or=False,
                 max_years_between_matches=self.CRON_YEARS_DEPTH)  # created for validation, then discarded

        self._stop_thread()
        self._cronspec = cronspec
        self._start_thread()

    def plugin(self, bus):
        super().plugin(bus)
        self._start_thread()

    def pullout(self):
        self._stop_thread()
        return super().pullout()

    def __str__(self):
        return '{}({})'.format(type(self).__name__, self.cronspec)

    def _start_thread(self):
        if self._bus:
            self._scheduler_thread = Thread(name=self.id, target=self._scheduler, daemon=True)
            self._scheduler_thread.start()

    def _stop_thread(self):
        if self._scheduler_thread:
            self._scheduler_stop = True
            self._scheduler_thread.join()
            self._scheduler_thread = None

    def _scheduler(self):
        log.brief('ScheduleInput %s: start', self.id)

        now = datetime.now().astimezone()  # = local tz, this enables DST
        cron = croniter(self._cronspec, now, ret_type=float, day_or=False,
                        max_years_between_matches=self.CRON_YEARS_DEPTH)
        tick = 1 if self.hires else 60
        log.debug(' now  %s = %f, 1 tick = %d s', now, time.time(), tick)

        try:
            cron.get_next()
            while True:
                sec_now = time.time()  # reference for each loop to avoid drift
                sec_prev = cron.get_prev()  # look one event back
                log.debug(' prev %s = %f', str(cron.get_current(ret_type=datetime)), sec_prev - sec_now)

                sec_next = cron.get_next()  # seconds 'til future cron event
                log.debug(' next %s = %f', str(cron.get_current(ret_type=datetime)), sec_next - sec_now)

                # just to be sure, croniter may need longer for sparse schedules with long pauses
                if self._scheduler_stop:
                    return  # cleanup is done in finally!

                if sec_next - sec_prev > tick:
                    # since we concatenate cron events <1 tick apart, this must be a pause
                    self.data = 0
                    log.brief('ScheduleInput %s: output 0 for %f s', self.id, sec_next - sec_now)
                    self.post(MsgData(self.id, self.data))

                    while (sec_next > time.time()):
                        time.sleep(self.STOP_DURATION)
                        if self._scheduler_stop:
                            return  # cleanup is done in finally!

                # now look how many ticks to concatenate
                while True:
                    candidate = cron.get_next()
                    log.debug('  ? %s = + %f s', str(cron.get_current(ret_type=datetime)), candidate - sec_next)
                    if candidate - sec_next > tick:
                        log.debug('  ... busted!')
                        break
                    sec_next = candidate

                # just to be sure, croniter may need longer for sparse schedules with long pauses
                if self._scheduler_stop:
                    return  # cleanup is done in finally!

                self.data = 100
                log.brief('ScheduleInput %s: output 100 for %f s', self.id, sec_next - sec_now)
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

    def get_settings(self):
        settings = super().get_settings()
        settings.append(('cronspec', 'CRON (m h DoM M DoW)', self.cronspec, 'type="text"'))
        return settings