#!/usr/bin/env python3
""" Tests for PortDriverMixin (aquaPi/machineroom/port_driver.py) - the
    shared attach/detach/isinstance-check/log shape now used by
    InputNode, DeviceNode and Alert instead of each reimplementing it.
    Uses a fake IoRegistry so this stays a hermetic unit test of the
    mixin itself, independent of any real/simulated hardware driver.
"""

import pytest

from aquaPi.machineroom import port_driver
from aquaPi.machineroom.port_driver import PortDriverMixin


class _FakeDriver:
    pass


class _WrongDirectionDriver:
    pass


class _FakeRegistry:
    def __init__(self):
        self.destructed: list = []
        self.factory_calls: list = []
        self.next_driver = _FakeDriver()

    def driver_factory(self, port, opts=None):
        self.factory_calls.append((port, opts))
        return self.next_driver

    def driver_destruct(self, port, driver):
        self.destructed.append((port, driver))


class _Node(PortDriverMixin):
    _DRIVER_BASE = _FakeDriver
    _PORT_CAPABILITY = 'testing'

    def __init__(self):
        self.name = 'Testnode'
        self._driver = None
        self._port = ''


@pytest.fixture
def registry(monkeypatch):
    fake = _FakeRegistry()
    monkeypatch.setattr(port_driver.IoRegistry, 'get', classmethod(lambda cls: fake))
    return fake


def test_setting_port_attaches_driver(registry):
    node = _Node()
    node.port = 'p1'

    assert node.port == 'p1'
    assert node._driver is registry.next_driver
    assert registry.factory_calls == [('p1', None)]


def test_clearing_port_destructs_and_clears_driver(registry):
    node = _Node()
    node.port = 'p1'

    node.port = ''

    assert node.port == ''
    assert node._driver is None
    assert registry.destructed == [('p1', registry.next_driver)]


def test_reattaching_port_destructs_previous_first(registry):
    node = _Node()
    node.port = 'p1'
    old_driver = node._driver

    node.port = 'p2'

    assert registry.destructed == [('p1', old_driver)]
    assert registry.factory_calls[-1] == ('p2', None)


def test_wrong_direction_driver_is_rejected(registry, caplog):
    registry.next_driver = _WrongDirectionDriver()
    node = _Node()

    node.port = 'p1'

    assert node._driver is None
    assert node.port == 'p1'  # _port is still recorded even though attach failed
    assert 'testing' in caplog.text


def test_port_driver_opts_hook_is_passed_to_factory(registry):
    class _NodeWithOpts(_Node):
        def _port_driver_opts(self):
            return {'foo': 'bar'}

    node = _NodeWithOpts()
    node.port = 'p1'

    assert registry.factory_calls == [('p1', {'foo': 'bar'})]


def test_sync_driver_hook_runs_after_attach(registry):
    calls = []

    class _NodeWithSync(_Node):
        def _sync_driver(self):
            calls.append(self._driver)

    node = _NodeWithSync()
    node.port = 'p1'

    assert calls == [node._driver]
