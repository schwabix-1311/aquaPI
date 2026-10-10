#!/usr/bin/env python3
""" Tests for DriverShelly's input support (aquaPi/driver/DriverShelly.py):
    DriverShellyInput.read() for both Shelly generations, and _identify()
    counting inputs from the right endpoint per generation, and offering
    only switch-mode inputs as ports.
"""

import aquaPi.driver.DriverShelly as ds
from aquaPi.driver.base import PortFunc


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(f'HTTP {self.status_code}')


def _router(routes):
    """ build a fake requests.get that dispatches on the URL path """
    def _get(url, params=None, timeout=None):
        for frag, payload in routes.items():
            if frag in url:
                if callable(payload):   # per-request answer, e.g. by params['id']
                    payload = payload(params)
                if isinstance(payload, _Resp):
                    return payload
                return _Resp(payload)
        return _Resp('Not Found', status=404)
    return _get


# --- DriverShellyInput.read() ----------------------------------------------


def test_gen1_input_read_true(monkeypatch):
    monkeypatch.setattr(ds.requests, 'get',
                        _router({'/status': {'inputs': [{'input': 1}, {'input': 0}]}}))
    d = ds.DriverShellyInput({'ip': '1.2.3.4', 'ch': 0, 'gen': 1}, PortFunc.Bin)
    assert d.read() is True


def test_gen1_input_read_false_for_other_channel(monkeypatch):
    monkeypatch.setattr(ds.requests, 'get',
                        _router({'/status': {'inputs': [{'input': 1}, {'input': 0}]}}))
    d = ds.DriverShellyInput({'ip': '1.2.3.4', 'ch': 1, 'gen': 1}, PortFunc.Bin)
    assert d.read() is False


def test_gen2_input_read_true(monkeypatch):
    monkeypatch.setattr(ds.requests, 'get',
                        _router({'/rpc/Input.GetStatus': {'id': 0, 'state': True}}))
    d = ds.DriverShellyInput({'ip': '1.2.3.4', 'ch': 0, 'gen': 2}, PortFunc.Bin)
    assert d.read() is True


def test_gen2_null_state_keeps_last_known(monkeypatch):
    monkeypatch.setattr(ds.requests, 'get',
                        _router({'/rpc/Input.GetStatus': {'id': 0, 'state': None}}))
    d = ds.DriverShellyInput({'ip': '1.2.3.4', 'ch': 0, 'gen': 2}, PortFunc.Bin)
    d._val = True
    assert d.read() is True


def test_read_error_returns_last_known(monkeypatch):
    def _boom(*_a, **_kw):
        raise ConnectionError('unreachable')
    monkeypatch.setattr(ds.requests, 'get', _boom)
    d = ds.DriverShellyInput({'ip': '1.2.3.4', 'ch': 0, 'gen': 1}, PortFunc.Bin)
    d._val = True
    assert d.read() is True


def test_fake_input_does_no_network(monkeypatch):
    def _boom(*_a, **_kw):
        raise AssertionError('fake driver must not touch the network')
    monkeypatch.setattr(ds.requests, 'get', _boom)
    d = ds.DriverShellyInput({'ip': '0.0.0.0', 'ch': 0, 'gen': 1, 'fake': True}, PortFunc.Bin)
    assert d.read() is False
    assert d.name.startswith('!')


# --- _identify() input counting ------------------------------------------


def test_identify_counts_gen1_inputs_from_status(monkeypatch):
    monkeypatch.setattr(ds.requests, 'get', _router({
        '/shelly': {'type': 'SHSW-1', 'mac': '8CAAB54306A0', 'num_outputs': 1},
        '/settings': {'name': 'kitchen'},
        '/status': {'inputs': [{'input': 0}]},
        '/relay/0': {'ison': False},
        '/light/0': _Resp('', status=404),
    }))
    dev = ds._identify('1.2.3.4')
    assert dev['gen'] == 1
    assert dev['name'] == 'kitchen'
    assert dev['label'] == 'kitchen'
    assert dev['relays'] == 1
    assert dev['inputs'] == 1


def test_identify_counts_gen2_inputs_from_rpc(monkeypatch):
    monkeypatch.setattr(ds.requests, 'get', _router({
        '/shelly': {'gen': 2, 'model': 'SNSN-0024X', 'name': None,
                    'id': 'shellyplusi4-c4d8d5546e54', 'mac': 'C4D8D5546E54'},
        '/rpc/Shelly.GetStatus': {'input:0': {}, 'input:1': {}, 'input:2': {}, 'input:3': {}},
        '/relay/0': _Resp('', status=404),
        '/light/0': _Resp('', status=404),
    }))
    dev = ds._identify('1.2.3.4')
    assert dev['gen'] == 2
    assert dev['relays'] == 0
    assert dev['inputs'] == 4
    # unnamed -> fall back to the device id, not the meaningless model code
    assert dev['label'] == 'shellyplusi4-c4d8d5546e54'


def test_identify_label_falls_back_to_mac_and_ip(monkeypatch):
    # unnamed Gen1 device with no id: label is "<mac> (<ip>)", the two
    # things an installer actually saw
    monkeypatch.setattr(ds.requests, 'get', _router({
        '/shelly': {'type': 'SHIX3-1', 'mac': '8CAAB54306A0', 'num_inputs': 3},
        '/settings': {'name': None},
        '/status': {'inputs': [{'input': 0}, {'input': 0}, {'input': 0}]},
        '/relay/0': _Resp('', status=404),
        '/light/0': _Resp('', status=404),
    }))
    dev = ds._identify('192.168.1.60')
    assert dev['name'] is None
    assert dev['label'] == '8CAAB54306A0 (192.168.1.60)'
    assert dev['inputs'] == 3


# --- switch-mode filter: only inputs with a stable level become ports -----
# payloads as read live from real devices (SHSW-25, SHIX3-1, Plus i4)


def test_identify_gen1_relay_device_uses_relay_btn_type(monkeypatch):
    monkeypatch.setattr(ds.requests, 'get', _router({
        '/shelly': {'type': 'SHSW-25', 'mac': '8CAAB54306A1'},
        '/settings': {'name': 'decke', 'relays': [{'btn_type': 'toggle'},
                                                  {'btn_type': 'momentary_on_release'}]},
        '/status': {'inputs': [{'input': 0}, {'input': 0}]},
        '/relay/0': {'ison': False},
        '/relay/1': {'ison': False},
        '/light/0': _Resp('', status=404),
    }))
    dev = ds._identify('1.2.3.4')
    assert dev['inputs'] == 2
    assert dev['switch_inputs'] == [0]


def test_identify_gen1_input_device_uses_input_btn_type(monkeypatch):
    monkeypatch.setattr(ds.requests, 'get', _router({
        '/shelly': {'type': 'SHIX3-1', 'mac': '8CAAB54306A2'},
        '/settings': {'name': 'wohnzimmer', 'inputs': [{'btn_type': 'momentary'},
                                                       {'btn_type': 'toggle'},
                                                       {'btn_type': 'edge'}]},
        '/status': {'inputs': [{'input': 0}, {'input': 1}, {'input': 0}]},
        '/relay/0': _Resp('', status=404),
        '/light/0': _Resp('', status=404),
    }))
    dev = ds._identify('1.2.3.4')
    assert dev['switch_inputs'] == [1, 2]


def test_identify_gen2_skips_buttons_and_disabled_inputs(monkeypatch):
    configs = [{'id': 0, 'type': 'button', 'enable': True},
               {'id': 1, 'type': 'switch', 'enable': True},
               {'id': 2, 'type': 'switch', 'enable': False},
               {'id': 3, 'type': 'analog', 'enable': True}]
    monkeypatch.setattr(ds.requests, 'get', _router({
        '/shelly': {'gen': 2, 'model': 'SNSN-0024X', 'name': None,
                    'id': 'shellyplusi4-c4d8d5546e54', 'mac': 'C4D8D5546E54'},
        '/rpc/Shelly.GetStatus': {'input:0': {}, 'input:1': {}, 'input:2': {}, 'input:3': {}},
        '/rpc/Input.GetConfig': lambda params: configs[params['id']],
        '/relay/0': _Resp('', status=404),
        '/light/0': _Resp('', status=404),
    }))
    dev = ds._identify('1.2.3.4')
    assert dev['inputs'] == 4
    assert dev['switch_inputs'] == [1]


def test_only_switch_inputs_become_ports_named_by_device_channel(monkeypatch):
    monkeypatch.setattr(ds, '_find_ips', lambda: {'1.2.3.4'})
    monkeypatch.setattr(ds, '_identify', lambda ip: {
        'ip': ip, 'gen': 1, 'type': 'SHIX3-1', 'name': 'wz', 'label': 'wz',
        'relays': 0, 'lights': 0, 'inputs': 3, 'switch_inputs': [2]})
    ports = ds._find_real_ports()
    assert list(ports) == ['wz input 2']
    assert ports['wz input 2'].func == PortFunc.Bin
