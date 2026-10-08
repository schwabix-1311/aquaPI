#!/usr/bin/env python3
""" Tests for machineroom/ctrl_nodes.py: PidCtrl's bumpless restart - a
    controller restored from the wiring DB continues at its persisted
    output instead of falling back to the neutral 50%.
"""

import pytest

from aquaPi import db as db_module
from aquaPi.machineroom import ctrl_nodes
from aquaPi.machineroom.ctrl_nodes import PidCtrl
from aquaPi.machineroom.msg_types import MsgData


@pytest.fixture
def clock(monkeypatch):
    """ PidCtrl.listen() reads time() for its tick length - drive it by hand """
    now = [1000.0]
    monkeypatch.setattr(ctrl_nodes, 'time', lambda: now[0])
    return now


def _restored(output: float, **gains) -> PidCtrl:
    """ a PidCtrl that last posted `output`, round-tripped through the same
        serialize/deserialize path a restart uses
    """
    node = PidCtrl('Heizleistung', 'sensor', 25.0, **gains)
    node.data = output
    return db_module._deserialize_node('PidCtrl', db_module.serialize_node(node))


def _feed(node, clock, values, step=60.0):
    for v in values:
        node.listen(MsgData('sensor', v))
        clock[0] += step


def test_restored_pid_resumes_its_persisted_output(clock):
    node = _restored(21.0, p_fact=180.0, i_fact=0.05)
    assert node.data == 21.0

    _feed(node, clock, [25.0625, 25.0625])

    # one 60s tick of integral on a +0.0625 error moves it by
    # i * err * dt = 0.05 * 0.0625 * 60 ~ 0.19pp - not back to ~50%
    assert node.data == pytest.approx(21.0 - 0.05 * 0.0625 * 60, abs=1e-6)


def test_restored_pid_still_reacts_through_p(clock):
    node = _restored(21.0, p_fact=180.0, i_fact=0.05)

    _feed(node, clock, [25.0, 25.0625])

    # the P term follows the change in error since the restart reading
    expected = 21.0 - 180.0 * 0.0625 - 0.05 * 0.0625 * 60
    assert node.data == pytest.approx(expected, abs=1e-6)


def test_restored_p_only_controller_has_no_integral_to_seed(clock):
    node = _restored(21.0, p_fact=180.0, i_fact=0.0)

    _feed(node, clock, [25.0625, 25.0625])

    assert node.data == pytest.approx(50.0 - 180.0 * 0.0625, abs=1e-6)


def test_new_pid_starts_from_neutral(clock):
    node = PidCtrl('Heizleistung', 'sensor', 25.0, p_fact=180.0, i_fact=0.05)

    _feed(node, clock, [25.0, 25.0])

    assert node.data == pytest.approx(50.0, abs=1e-6)
