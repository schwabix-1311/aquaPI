#!/usr/bin/env python3

import logging
from threading import Thread
import time

from .msg_bus import (BusListener, BusRole, DataRange, MsgData)
from ..driver import (io_registry)


log = logging.getLogger('machineroom.out_nodes')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose


# ========== outputs AKA Device ==========


class DeviceNode(BusListener):
    """ Base class for OUT_ENDP such as relay, PWM, GPIO pins.
        Receives float input from listened sender.
        Binary devices should use a threashold of 50 or pythonic
        truth testing, whatever is more intuitive for each dev.
    """
    ROLE = BusRole.OUT_ENDP

    # def __getstate__(self):
    #     return super().__getstate__()

    # def __setstate__(self, state):
    #     self.data = state['data']
    #     self.__init__(state, _cont=True)


class SwitchDevice(DeviceNode):
    """ A binary output to a GPIO pin or relay.

        Options:
            name       - unique name of this output node in UI
            inputs     - id of a single (!) input to receive data from
            port       - name of a IoRegistry port driver to drive output
            inverted   - swap the boolean interpretation for active low outputs

        Output:
            drive output with bool(input), possibly inverted
    """
    data_range = DataRange.BINARY

    def __init__(self, name, inputs, port, inverted=0, _cont=False):
        super().__init__(name, inputs, _cont=_cont)
        self._driver = None
        self._port = None
        self._inverted = int(inverted)
        ##self.unit = '%' if self.data_range != DataRange.BINARY else '⏻'
        self.port = port
        self.switch(self.data if _cont else False)
        log.info('%s init to %f|%r', self.name, self.data, inverted)

    def __getstate__(self):
        state = super().__getstate__()
        state.update(port=self.port)
        state.update(inverted=self._inverted)
        return state

    def __setstate__(self, state):
        self.data = state['data']
        self.__init__(state['name'], state['inputs'], state['port'], inverted=state['inverted'], _cont=True)

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

    @property
    def inverted(self):
        return self._inverted

    @inverted.setter
    def inverted(self, inverted):
        self._inverted = inverted
        self.switch(self.data)

    def listen(self, msg):
        if isinstance(msg, MsgData):
            #if self.data != bool(msg.data):
            data = (msg.data > 50.)
            if self.data != data:
                self.switch(data)
        return super().listen(msg)

    def switch(self, state: bool) -> None:
        self.data: bool = state

        log.info('SwitchDevice %s: turns %s', self.id, 'ON' if self.data else 'OFF')
        if not self._inverted:
            self._driver.write(self.data)
        else:
            self._driver.write(not self.data)
        self.post(MsgData(self.id, self.data))  # to make our state known

    def get_settings(self):
        settings = super().get_settings()
        settings.append(('inverted', 'Inverted', self.inverted,
                         'type="number" min="0" max="1"'))  # FIXME   'class="uk-checkbox" type="checkbox" checked' fixes appearance, but result is always False )
        return settings


class SlowPwmDevice(DeviceNode):
    """ An analog output to a binary GPIO pin or relay using slow PWM.

        Options:
            name       - unique name of this output node in UI
            inputs     - id of a single (!) input to receive data from
            port       - name of a IoRegistry port driver to drive output
            inverted   - swap the boolean interpretation for active low outputs
            cycle      - optional cycle time in sec for generated PWM

        Output:
            drive output with PWM(input/100 * cycle), possibly inverted
    """
    data_range = DataRange.BINARY

    def __init__(self, name, inputs, port, inverted=0, cycle=60., _cont=False):
        super().__init__(name, inputs, _cont=_cont)
        self.data = 50.0
        ##self.unit = '%' if self.data_range != DataRange.BINARY else '⏻'
        self.cycle = float(cycle)
        self._driver = None
        self._port = None
        self._inverted = int(inverted)
        self._thread = None
        self._thread_stop = False
        self.port = port
        self.set(self.data)
        log.info('%s init to %f|%r|%r s', self.name, self.data, inverted, cycle)

    def __getstate__(self):
        state = super().__getstate__()
        state.update(cycle=self.cycle)
        state.update(port=self.port)
        state.update(inverted=self._inverted)
        return state

    def __setstate__(self, state):
        self.data = state['data']
        self.__init__(state['name'], state['inputs'], state['port'],
                      inverted=state['inverted'], cycle=state['cycle'],
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

    @property
    def inverted(self):
        return self._inverted

    @inverted.setter
    def inverted(self, inverted):
        self._inverted = inverted
        self.set(self.data)

    def listen(self, msg):
        if isinstance(msg, MsgData):
            self.set(float(msg.data))
        return super().listen(msg)

    def _pulse(self, hi_sec: float):
        def toggle_and_wait(state: bool, end: float) -> bool:
            start = time.time()
            self._driver.write(state  if not self._inverted else not state)
            self.post(MsgData(self.id, 100  if state else 0))
            # avoid error accumulation by exact final sleep()
            while time.time() < end - .1:
                if self._thread_stop:
                    self._thread_stop = False
                    return False
                time.sleep(.1)
            time.sleep(end - time.time())
            log.debug('  _pulse needed %f instead of %f',
                      time.time() - start, end - start)
            return True

        while True:
            lead_edge = time.time()
            if hi_sec > 0.1:
                if not toggle_and_wait(True, lead_edge + hi_sec):
                    return
            if hi_sec < self.cycle:
                if not toggle_and_wait(False, lead_edge + self.cycle):
                    return
        return

    def set(self, perc: float) -> None:
        self.data: float = perc

        log.info('SlowPwmDevice %s: sets %.1f %%  (%.3f of %f s)',
                 self.id, self.data, self.cycle * perc/100, self.cycle)
        if self._thread:
            self._thread_stop = True
            self._thread.join()
        self._thread = Thread(name='PIDpulse', target=self._pulse,
                              args=[self.data / 100 * self.cycle], daemon=True)
        self._thread.start()

    def get_settings(self):
        settings = super().get_settings()
        settings.append(('cycle', 'PWM cycle time', self.cycle,
                         'type="number" min="10" max="300" step="1"',
                         'inverted', 'Inverted', self.inverted,
                         'type="number" min="0" max="1"'))
        return settings


class AnalogDevice(DeviceNode):
    """ An analog output using PWM (or DAC), 0..100% input range is
        mapped to the pysical minimum...maximum range of this node.

        Options:
            name     - unique name of this output node in UI
            inputs   - id of a single (!) input to receive data from
            port     - name of a IoRegistry port driver to drive output
            minimum  - minimum percentage value to avoid flicker, or reliable start (motor!)
            maximum  - upper physical percentage limit (overload, brightness, ...)
            percept  - perceptive correction using in², close to linear brightness perception

        Output:
            drive analog output with minimum...maximum, optional perceptive correction
    """
    data_range = DataRange.PERCENT

    def __init__(self, name, inputs, port, percept=False, minimum=0, maximum=100, _cont=False):
        super().__init__(name, inputs, _cont=_cont)
        self._driver = None
        self._port = None
        self.unit = '%'  ## if self.data_range != DataRange.BINARY else '⏻'
        self.percept = bool(percept)
        self.minimum = min(max(0, minimum), 90)
        self.maximum = min(max(minimum + 1, maximum), 100)
        self.port = port
        self.set_percent(self.data if _cont else 0)
        log.info('%s init to %r | pe %r | min %f | max %f', self.name, self.data, percept, minimum, maximum)

    def __getstate__(self):
        state = super().__getstate__()
        state.update(port=self.port)
        state.update(percept=self.percept)
        state.update(minimum=self.minimum)
        state.update(maximum=self.maximum)
        log.debug('AnalogDevice.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('AnalogDevice.setstate %r', state)
        self.data = state['data']
        self.__init__(state['name'], state['inputs'], state['port'], percept=state['percept'], minimum=state['minimum'],
                      maximum=state['maximum'], _cont=True)

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
            if self.data != float(msg.data):
                self.set_percent(float(msg.data))
        return super().listen(msg)

    def set_percent(self, percent):
        out_val = float(percent)
        log.debug('%s set to %f %%', self.name, round(out_val, 4))
        if out_val > 0:
            if self.percept:
                out_val = (out_val ** 2) / (100 ** 2) * 100
                log.debug('  percept to %f %%', out_val)
            out_range = self.maximum - self.minimum
            out_val = out_val / 100 * out_range
            log.debug('  scale to %f %% [%f]', out_val, out_range)
            out_val += self.minimum
        log.debug('    finally %f %%', out_val)
        self.data = out_val

        self._driver.write(out_val)
        self.post(MsgData(self.id, round(out_val, 4)))  # to make our state known

    def get_settings(self):
        settings = super().get_settings()
        settings.append(('minimum', 'Minimum [%]', self.minimum, 'type="number" min="0" max="99"'))
        settings.append(('maximum', 'Maximum [%]', self.maximum, 'type="number" min="1" max="100"'))
        settings.append(('percept', 'Perceptive', self.percept, 'type="number" min="0" max="1"'))  # 'type="checkbox"' )
        return settings
