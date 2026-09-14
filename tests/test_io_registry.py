#!/usr/bin/env python3
""" IoRegistry port reservation semantics, in particular deps:
    - a dual-use pin ('PWM 1' owns 'GPIO 19 in/out') must not be
      double-claimed, in either claim order
    - ports that only *share* a dep (a bus: several DS1820 on one 1-Wire
      pin, several ADC channels on one I2C bus) may coexist
"""

import pytest

from aquaPi.driver import create_io_registry, IoRegistry, PortFunc
from aquaPi.driver.base import DriverPortInuseError


@pytest.fixture(autouse=True, scope='module')
def _io():
    create_io_registry()


@pytest.fixture
def reg():
    r = IoRegistry.get()
    yield r
    # drain any claim a failing test might have leaked
    for name, cnt in list(IoRegistry._primary_claims.items()):
        for _ in range(cnt):
            try:
                r.driver_destruct(name, _Dummy())
            except Exception:
                IoRegistry._primary_claims.pop(name, None)


class _Dummy:
    def close(self):
        pass


def _free(reg, func):
    return set(reg.get_ports_by_function([func], in_use=False))


def test_dual_use_pin_blocks_the_other_form_either_order(reg):
    # claim the raw GPIO first, then the PWM that repurposes the same pin
    d = reg.driver_factory('GPIO 19 out')
    assert 'PWM 1' not in _free(reg, PortFunc.Aout)
    with pytest.raises(DriverPortInuseError):
        reg.driver_factory('PWM 1')
    reg.driver_destruct('GPIO 19 out', d)
    assert 'PWM 1' in _free(reg, PortFunc.Aout)

    # and the other order: PWM first, then the raw GPIO
    d = reg.driver_factory('PWM 1')
    assert 'GPIO 19 out' not in _free(reg, PortFunc.Bout)
    with pytest.raises(DriverPortInuseError):
        reg.driver_factory('GPIO 19 out')
    reg.driver_destruct('PWM 1', d)
    assert 'GPIO 19 out' in _free(reg, PortFunc.Bout)


def test_preview_release_of_a_dep_unblocks_its_primary(reg):
    # claim the raw GPIO for real, hiding 'PWM 1' - a preview that
    # releases just the GPIO must report 'PWM 1' free, while the real
    # registry still reports it in-use (item #8: freeing a dep pin can
    # unblock a primary port that was only hidden because of it)
    d = reg.driver_factory('GPIO 19 out')
    try:
        assert 'PWM 1' not in _free(reg, PortFunc.Aout)

        preview = reg.preview()
        assert not preview.is_free('PWM 1')
        preview.release('GPIO 19 out')
        assert preview.is_free('PWM 1')

        # the real registry is untouched by the preview
        assert 'PWM 1' not in _free(reg, PortFunc.Aout)
    finally:
        reg.driver_destruct('GPIO 19 out', d)


def test_preview_does_not_mutate_the_real_registry(reg):
    preview = reg.preview()
    preview.claim('PWM 1')
    assert preview.is_free('PWM 1') is False
    # the real registry never saw this claim
    assert 'PWM 1' in _free(reg, PortFunc.Aout)
    assert IoRegistry._primary_claims.get('PWM 1', 0) == 0


def test_preview_claim_rejects_the_same_dual_use_conflict_either_order(reg):
    preview = reg.preview()
    preview.claim('PWM 1')
    with pytest.raises(DriverPortInuseError):
        preview.claim('GPIO 19 out')

    preview = reg.preview()
    preview.claim('GPIO 19 out')
    with pytest.raises(DriverPortInuseError):
        preview.claim('PWM 1')


def test_shared_bus_dep_allows_multiple_primaries(reg):
    # two ADC channels on the same I2C bus pins (deps 'GPIO 2 in/out')
    d1 = reg.driver_factory('ADC #1 in 0')
    d2 = reg.driver_factory('ADC #1 in 1')
    reg.driver_destruct('ADC #1 in 0', d1)
    reg.driver_destruct('ADC #1 in 1', d2)

    # a raw GPIO claim on a bus pin is still refused while a channel holds it
    d1 = reg.driver_factory('ADC #1 in 0')
    assert 'GPIO 2 out' not in _free(reg, PortFunc.Bout)
    with pytest.raises(DriverPortInuseError):
        reg.driver_factory('GPIO 2 out')
    reg.driver_destruct('ADC #1 in 0', d1)
