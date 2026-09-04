#!/usr/bin/env python3

from abc import ABC
import logging
from typing import Any
from threading import (Lock, Thread)
import time

from .msg_types import (Msg, MsgData)
from .msg_bus import (BusListener, BusRole, DataRange, Setting)
from .port_driver import PortDriverMixin
from ..driver import (OutDriver, PortFunc)


log = logging.getLogger('machineroom.out_nodes')


# ========== outputs AKA Device ==========


class DeviceNode(PortDriverMixin, BusListener, ABC):
    """ Base class for OUT_ENDP such as relay, PWM, GPIO pins.
        Receives float input from listened sender.
        Binary devices should use a threashold of 50 or pythonic
        truth testing, whatever is more intuitive for each dev.
    """
    ROLE = BusRole.OUT_ENDP
    _DRIVER_BASE = OutDriver
    _PORT_CAPABILITY = 'writing data'

    def __init__(self, name: str, receives: str, port: str,
                 _cont=False):
        super().__init__(name, receives, _cont=_cont)
        self.unit: str = '%'
        self._driver: OutDriver | None = None
        self._port: str = ''
        # bypass the port setter here - it's too early for _sync_driver()
        # to run (subclass attrs like _inverted/minimum/maximum aren't set
        # yet); each subclass's own __init__ does its own initial sync
        # (switch()/set_percent()/set()) once fully constructed.
        self._apply_port(port)

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state["port"] = self.port
        return state

    def __str__(self) -> str:
        return f'{type(self).__name__}({self.name}/{self.port})'

    @PortDriverMixin.port.setter
    def port(self, port: str) -> None:
        self._apply_port(port)
        if self._driver:
            # a runtime port change (e.g. via /settings) attaches a driver
            # that starts in its own default state - push the node's
            # current data to it now, instead of leaving it stale until
            # the next MsgData that happens to differ from self.data.
            self._sync_driver()

    def _sync_driver(self) -> None:
        """ push the node's current state to a freshly (re)attached
            driver. No-op by default; overridden by subclasses that can
            re-push their state (SwitchDevice, AnalogDevice).
            SlowPwmDevice doesn't need this - its background pulse thread
            already re-reads self._driver on its own on every toggle.
        """
        pass

    def pullout(self) -> bool:
        self.port = ''
        return super().pullout()

    def get_settings(self) -> list[Setting]:
        settings = super().get_settings()
        settings.append(self._port_setting('outputPort'))
        return settings

    @classmethod
    def get_settings_schema(cls) -> list[Setting]:
        schema = super().get_settings_schema()
        schema.append(cls.get_port_schema('outputPort'))
        return schema


class SwitchDevice(DeviceNode):
    """ A binary output to a GPIO pin or relay.

        Options:
            name       - unique name of this output node in UI
            receives   - id of a single (!) input to receive data from
            port       - name of a IoRegistry port driver to drive output
            inverted   - swap the boolean interpretation for active low outputs

        Output:
            drive output with bool(input), possibly inverted
    """
    data_range = DataRange.BINARY
    _port_funcs = [PortFunc.Bout]

    def __init__(self, name: str, receives: str, port: str,
                 inverted: bool = False, _cont: bool = False):
        super().__init__(name, receives, port, _cont=_cont)
        self._inverted = inverted
        self.switch(self.data if _cont else False)
        log.verbose('%s init to %f|%r', self.name, self.data, inverted)

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state["inverted"] = self.inverted
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        SwitchDevice.__init__(self, state['name'], state['receives'], state['port'],
                              inverted=state['inverted'], _cont=True)

    @property
    def inverted(self) -> bool:
        return self._inverted

    @inverted.setter
    def inverted(self, inverted: bool) -> None:
        self._inverted = inverted
        self.switch(self.data)

    def listen(self, msg: Msg) -> None:
        if isinstance(msg, MsgData):
            data = (msg.data > 50.)
            if self.data != data:
                self.switch(data)  # also posts
            else:
                self.post(MsgData(self.id, 100 if self.data else 0))

        super().listen(msg)

    def _sync_driver(self) -> None:
        self.switch(self.data)

    def switch(self, state: bool) -> None:
        self.data: bool = state

        log.verbose('SwitchDevice %s: turns %s', self.id, 'ON' if self.data else 'OFF')
        if self._driver:
            if not self.inverted:
                self._driver.write(self.data)
            else:
                self._driver.write(not self.data)
        self.post(MsgData(self.id, 100 if self.data else 0))

    def get_settings(self) -> list[Setting]:
        settings = super().get_settings()
        schema = {s.key: s for s in type(self).get_settings_schema()}
        settings.append(self._fill_setting(schema['inverted']))
        return settings

    @classmethod
    def get_settings_schema(cls) -> list[Setting]:
        schema = super().get_settings_schema()
        schema.append(Setting('inverted', 'inverted', False, type='checkbox'))
        return schema


class SlowPwmDevice(DeviceNode):
    """ An analog output to a binary GPIO pin or relay using slow PWM.

        Options:
            name       - unique name of this output node in UI
            receives   - id of a single (!) input to receive data from
            port       - name of a IoRegistry port driver to drive output
            inverted   - swap the boolean interpretation for active low outputs
            cycle      - optional cycle time in sec for generated PWM

        Output:
            drive output with PWM(input/100 * cycle), possibly inverted
    """
    data_range = DataRange.BINARY
    _port_funcs = [PortFunc.Bout]

    def __init__(self, name: str, receives: str, port: str,
                 inverted: bool = False, cycle: float = 60.,
                 _cont: bool = False):
        super().__init__(name, receives, port, _cont=_cont)
        self.data: float = 50.0
        self.cycle = float(cycle)
        self._inverted = inverted
        self._thread = None
        self._thread_stop = False
        # protects the stop-old/start-new sequence in set() below - during
        # startup, node.plugin()'s MsgHello cascades can re-enter set()
        # for this same device several times in quick succession, racing
        # unguarded self._thread/self._thread_stop access and deadlocking
        # in .join() (found 2026-08-09 via a py-spy stack dump)
        self._set_lock = Lock()
        self.set(self.data)
        log.verbose('%s init to %f|%r|%r s', self.name, self.data, inverted, cycle)

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state["cycle"] = self.cycle
        state["inverted"] = self._inverted
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        SlowPwmDevice.__init__(self, state['name'], state['receives'], state['port'],
                               inverted=state['inverted'], cycle=state['cycle'],
                               _cont=True)

    @property
    def inverted(self) -> bool:
        return self._inverted

    @inverted.setter
    def inverted(self, inverted: bool) -> None:
        self._inverted = inverted
        self.set(self.data)

    def listen(self, msg: Msg) -> None:
        if isinstance(msg, MsgData):
            log.debug('%s: ======= received %f from %s', self.id, msg.data, msg.sender)
            self.set(float(msg.data))

        super().listen(msg)

    def _pulse(self, hi_sec: float, cycle: float) -> None:
        def toggle_and_wait(state: bool, end: float) -> bool:
            start = time.time()
            if self._driver:
                self._driver.write(state  if not self._inverted else not state)
            log.debug('%s: ======= posts %d', self.id, 100 if state else 0)
            self.post(MsgData(self.id, 100  if state else 0))
            # avoid error accumulation by exact final sleep()
            while time.time() < end - .1:
                if self._thread_stop:
                    self._thread_stop = False
                    return False
                time.sleep(.1)
            time.sleep(max(0, end - time.time()))
            log.debug('  _pulse needed %f instead of %f',
                      time.time() - start, end - start)
            return True

        while True:
            lead_edge = time.time()
            if hi_sec > 0.1:
                if not toggle_and_wait(True, lead_edge + hi_sec):
                    return
            if hi_sec < cycle:
                if not toggle_and_wait(False, lead_edge + cycle):
                    return

    def set(self, perc: float) -> None:
        log.verbose('SlowPwmDevice %s: sets %.1f %%  (%.3f of %f s)',
                 self.id, perc, self.cycle * perc/100, self.cycle)
        with self._set_lock:
            if self._thread:
                self._thread_stop = True
                self._thread.join()
            self.data = perc
            self._thread = Thread(name='PIDpulse', target=self._pulse,
                                  args=[perc / 100 * self.cycle, self.cycle],
                                  daemon=True)
            self._thread.start()

    def get_settings(self) -> list[Setting]:
        settings = super().get_settings()
        schema = {s.key: s for s in type(self).get_settings_schema()}
        settings.append(self._fill_setting(schema['cycle']))
        settings.append(self._fill_setting(schema['inverted']))
        return settings

    @classmethod
    def get_settings_schema(cls) -> list[Setting]:
        schema = super().get_settings_schema()
        schema.append(Setting('cycle', 'cycle', 60.0, type='duration', min=10, max=300, step=1))
        schema.append(Setting('inverted', 'inverted', False, type='checkbox'))
        return schema


class AnalogDevice(DeviceNode):
    """ An analog output using PWM (or DAC), 0..100% input range is
        mapped to the pysical minimum...maximum range of this node.

        Options:
            name     - unique name of this output node in UI
            receives - id of a single (!) input to receive data from
            port     - name of a IoRegistry port driver to drive output
            minimum  - minimum percentage value to avoid flicker, or reliable start (motor!)
            maximum  - upper physical percentage limit (overload, brightness, ...)
            percept  - perceptive correction using in², close to linear brightness perception

        Output:
            drive analog output with minimum...maximum, optional perceptive correction
    """
    data_range = DataRange.PERCENT
    _port_funcs = [PortFunc.Aout]

    def __init__(self, name: str, receives: str, port: str,
                 percept: bool = False, minimum: float = 0, maximum: float = 100,
                 _cont=False):
        super().__init__(name, receives, port, _cont=_cont)
        self.percept = percept
        self.minimum = min(max(0., minimum), 90.)
        self.maximum = min(max(minimum + 1., maximum), 100.)
        self.set_percent(self.data if _cont else 0)
        log.verbose('%s init to %r | pe %r | min %f | max %f', self.name, self.data, percept, minimum, maximum)

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state["percept"] = self.percept
        state["minimum"] = self.minimum
        state["maximum"] = self.maximum
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        AnalogDevice.__init__(self, state['name'], state['receives'],
                              state['port'], percept=state['percept'],
                              minimum=state['minimum'], maximum=state['maximum'], _cont=True)

    def listen(self, msg: Msg) -> None:
        if isinstance(msg, MsgData):
            if self.data != float(msg.data):
                self.set_percent(float(msg.data))  # also posts
            else:
                self.post(MsgData(self.id, round(self.data, 4)))

        super().listen(msg)

    def set_percent(self, percent: float) -> None:
        out_val = percent
        log.debug('%s set to %f %%', self.name, round(out_val, 4))
        if out_val > 0.:
            if self.percept:
                out_val = (out_val ** 2) / (100 ** 2) * 100
                log.debug('  percept to %f %%', out_val)
            out_range = self.maximum - self.minimum
            out_val = out_val / 100 * out_range
            log.debug('  scale to %f %% [%f]', out_val, out_range)
            out_val += self.minimum
        log.debug('    finally %f %%', out_val)
        self.data = out_val

        if self._driver:
            self._driver.write(out_val)
        self.post(MsgData(self.id, round(out_val, 4)))  # to make our state known

    def _sync_driver(self) -> None:
        # NOT set_percent(self.data) - self.data already holds the fully
        # scaled/percept-corrected *output* value (see set_percent() above),
        # so re-running it through set_percent() would double-apply that
        # scaling. Push the already-computed value straight to the driver.
        if self._driver:
            self._driver.write(self.data)

    def get_settings(self) -> list[Setting]:
        settings = super().get_settings()
        schema = {s.key: s for s in type(self).get_settings_schema()}
        settings.append(self._fill_setting(schema['minimum']))
        settings.append(self._fill_setting(schema['maximum']))
        settings.append(self._fill_setting(schema['percept']))
        return settings

    @classmethod
    def get_settings_schema(cls) -> list[Setting]:
        schema = super().get_settings_schema()
        schema.append(Setting('minimum', 'minimum', 0, type='number', min=0, max=99))
        schema.append(Setting('maximum', 'maximum', 100, type='number', min=1, max=100))
        schema.append(Setting('percept', 'percept', False, type='checkbox'))
        return schema
