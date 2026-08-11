#!/usr/bin/env python3

import logging

from ..driver import IoRegistry


log = logging.getLogger('machineroom.port_driver')


class PortDriverMixin:
    """ Mixin for nodes that attach to an optional IoRegistry port
        driver, destructing any previous one first - the same
        attach/detach/isinstance-check/log shape independently
        reimplemented by InputNode, DeviceNode and Alert.

        A using class must declare self._driver/self._port itself
        (before first assigning self.port), set the class attributes
        _DRIVER_BASE (InDriver or OutDriver) and _PORT_CAPABILITY (a
        short description for the log message, e.g. 'reading data'),
        and may override _port_driver_opts()/_sync_driver() for
        class-specific extra factory options / post-attach side
        effects (both no-ops by default).
    """
    _DRIVER_BASE: type
    _PORT_CAPABILITY: str = 'this'

    @property
    def port(self) -> str:
        return self._port

    @port.setter
    def port(self, port: str) -> None:
        self._apply_port(port)
        self._sync_driver()

    def _apply_port(self, port: str) -> None:
        """ (re)connect self._driver to `port`, destructing any
            previous one. Does not run _sync_driver() - callers that
            need the port attached before their own state is fully
            set up (e.g. during __init__) can call this directly.
        """
        if self._driver:
            IoRegistry.get().driver_destruct(self._port, self._driver)
            self._driver = None
        if port:
            driver = IoRegistry.get().driver_factory(port, self._port_driver_opts())
            if isinstance(driver, self._DRIVER_BASE):
                self._driver = driver
            else:
                log.error('Port %s does not support %s. %s will be ignored.',
                          port, self._PORT_CAPABILITY, self.name)
        self._port = port

    def _port_driver_opts(self):
        return None

    def _sync_driver(self) -> None:
        """ push/pull the node's state to/from a freshly (re)attached
            driver. No-op by default.
        """
