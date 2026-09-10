#!/usr/bin/env python3
""" Unit tests for the generic 'record-list' Setting type: Setting.to_dict()
    shape and api._validate_and_cast()'s recursive validation. No Flask app
    context needed - both are pure.
"""

import pytest

from aquaPi.machineroom.msg_bus import Setting
from aquaPi.api import _validate_and_cast


def _record_list_setting():
    return Setting(
        'conditions', 'conditions', [],
        type='record-list',
        record_schema=[
            Setting('class', 'condClass', 'AlertAbove',
                    type='select', options=['AlertAbove', 'AlertBelow']),
            Setting('node_id', 'condNode', None, type='select', node_filter='numeric'),
            Setting('limit', 'condLimit', 50.0, type='number'),
            Setting('duration', 'condDuration', 0, type='number', min=0),
        ])


def test_to_dict_nests_the_record_schema_and_node_filter():
    d = _record_list_setting().to_dict()
    assert d['key'] == 'conditions'
    assert d['attrs']['type'] == 'record-list'
    sub = d['attrs']['recordSchema']
    assert [s['key'] for s in sub] == ['class', 'node_id', 'limit', 'duration']
    assert sub[0]['attrs']['options'] == ['AlertAbove', 'AlertBelow']
    assert sub[1]['attrs']['nodeFilter'] == 'numeric'
    # a plain Setting carries neither key
    plain = Setting('x', 'x', 1, type='number').to_dict()['attrs']
    assert 'recordSchema' not in plain and 'nodeFilter' not in plain


_SUB_SCHEMA = _record_list_setting().to_dict()['attrs']['recordSchema']


def test_validate_and_cast_record_list_happy_path():
    out = _validate_and_cast(
        'conditions',
        [{'class': 'AlertBelow', 'node_id': 'wasser', 'limit': '24', 'duration': 5,
          '_key': 'ui-junk'}],
        'record-list', vrecord_schema=_SUB_SCHEMA)
    # rebuilt in schema order, _key dropped, limit coerced to float
    assert out == [{'class': 'AlertBelow', 'node_id': 'wasser',
                    'limit': 24.0, 'duration': 5.0}]
    assert list(out[0].keys()) == ['class', 'node_id', 'limit', 'duration']


def test_validate_and_cast_record_list_fills_missing_sub_field_from_default():
    out = _validate_and_cast(
        'conditions', [{'class': 'AlertAbove', 'node_id': 'wasser', 'limit': 30}],
        'record-list', vrecord_schema=_SUB_SCHEMA)
    assert out[0]['duration'] == 0  # from the sub-field default


def test_validate_and_cast_record_list_empty_list_ok_when_optional():
    assert _validate_and_cast('conditions', [], 'record-list',
                              voptional=True, vrecord_schema=_SUB_SCHEMA) == []


@pytest.mark.parametrize('bad, msg', [
    ('not-a-list', 'expected a list of records'),
    ([42], 'expected an object'),
    ([{'class': 'Nope', 'node_id': 'wasser', 'limit': 1}], 'not a valid choice'),
    ([{'class': 'AlertAbove', 'node_id': 'wasser', 'limit': 'abc'}], 'expected a number'),
    ([{'class': 'AlertAbove', 'node_id': None, 'limit': 1}], 'value is required'),
])
def test_validate_and_cast_record_list_rejections(bad, msg):
    with pytest.raises(ValueError) as ex:
        _validate_and_cast('conditions', bad, 'record-list', vrecord_schema=_SUB_SCHEMA)
    assert msg in str(ex.value)
