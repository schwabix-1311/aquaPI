#!/usr/bin/env python3

import logging
from typing import Any
from abc import ABC

from .msg_types import (Msg, MsgData)
from .msg_bus import (BusListener, BusRole, DataRange)
from ..driver import (io_registry, OutDriver)


log = logging.getLogger('machineroom.out_nodes')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose


# ========== outputs AKA Device ==========


class DeviceNode(BusListener, ABC):
    """ Base class for OUT_ENDP such as relay, PWM, GPIO pins.
        Receives float input from listened sender.
        The interpretation is device specific, recommendation is
        to follow pythonic truth testing to avoid surprises.
    """
    ROLE = BusRole.OUT_ENDP

    # def __getstate__(self) -> dict[str, Any]:
    #     return super().__getstate__()

    # def __setstate__(self, state: dict[str, Any]) -> None:
    #     self.data = state['data']
    #     DeviceNode.__init__(self, state, _cont=True)


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

    def __init__(self, name: str, receives: str, port: str,
                 inverted: bool = False, _cont: bool = False):
        super().__init__(name, receives, _cont=_cont)
        self._driver: OutDriver | None = None
        self._port: str = ''
        self._inverted = inverted
        ##self.unit = '%' if self.data_range != DataRange.BINARY else '⏻'
        self.port = port
        self.switch(self.data if _cont else False)
        log.info('%s init to %r|%f|%f', self.name, _cont, self.data, inverted)

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state.update(port=self.port)
        state.update(inverted=self.inverted)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        SwitchDevice.__init__(self, state['name'], state['receives'], state['port'],
                              inverted=state['inverted'], _cont=True)

    @property
    def port(self) -> str:
        return self._port

    @port.setter
    def port(self, port: str) -> None:
        if self._driver:
            io_registry.driver_destruct(self._port, self._driver)
        if port:
            driver = io_registry.driver_factory(port)
            if isinstance(driver, OutDriver):
                self._driver = driver
            else:
                log.error('Port %s does not support writing data. %s will be ignored.',
                          port, self.name)
        self._port = port

    @property
    def inverted(self) -> bool:
        return self._inverted

    @inverted.setter
    def inverted(self, inverted: bool) -> None:
        self._inverted = inverted
        self.switch(self.data)

    def listen(self, msg: Msg) -> bool:
        if isinstance(msg, MsgData):
            if self.data != bool(msg.data):
                self.switch(msg.data)
        return super().listen(msg)

    def switch(self, on: bool) -> None:
        self.data: bool = on

        log.info('SwitchDevice %s: turns %s', self.id, 'ON' if self.data else 'OFF')
        if self._driver:
            if not self.inverted:
                self._driver.write(self.data)
            else:
                self._driver.write(not self.data)
        self.post(MsgData(self.id, 100 if self.data else 0))

    def get_settings(self) -> list[tuple]:
        settings = super().get_settings()
        settings.append(('inverted', 'Inverted', self.inverted,
                         'type="number" min="0" max="1"'))  # FIXME   'class="uk-checkbox" type="checkbox" checked' fixes appearance, but result is always False )
        return settings


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

    def __init__(self, name: str, receives: str, port: str,
                 percept: bool = False, minimum: float = 0, maximum: float = 100,
                 _cont=False):
        super().__init__(name, receives, _cont=_cont)
        self._driver: OutDriver | None = None
        self._port: str = ''
        self.unit: str = '%'  ## if self.data_range != DataRange.BINARY else '⏻'
        self.percept = percept
        self.minimum = min(max(0., minimum), 90.)
        self.maximum = min(max(minimum + 1., maximum), 100.)
        self.port = port
        self.set_percent(self.data if _cont else 0)
        log.info('%s init to %r | pe %r | min %f | max %f', self.name, self.data, percept, minimum, maximum)

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state.update(port=self.port)
        state.update(percept=self.percept)
        state.update(minimum=self.minimum)
        state.update(maximum=self.maximum)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.data = state['data']
        AnalogDevice.__init__(self, state['name'], state['receives'],
                              state['port'], percept=state['percept'],
                              minimum=state['minimum'], maximum=state['maximum'], _cont=True)

    @property
    def port(self) -> str:
        return self._port

    @port.setter
    def port(self, port: str) -> None:
        if self._driver:
            io_registry.driver_destruct(self._port, self._driver)
        if port:
            driver = io_registry.driver_factory(port)
            if isinstance(driver, OutDriver):
                self._driver = driver
            else:
                log.error('Port %s does not support writing data. %s will be ignored.',
                          port, self.name)
        self._port = port

    def listen(self, msg: Msg) -> bool:
        if isinstance(msg, MsgData):
            if self.data != float(msg.data):
                self.set_percent(float(msg.data))
        return super().listen(msg)

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

    def get_settings(self) -> list[tuple]:
        settings = super().get_settings()
        settings.append(('minimum', 'Minimum [%]', self.minimum, 'type="number" min="0" max="99"'))
        settings.append(('maximum', 'Maximum [%]', self.maximum, 'type="number" min="1" max="100"'))
        settings.append(('percept', 'Perceptive', self.percept, 'type="number" min="0" max="1"'))  # 'type="checkbox"' )
        return settings
