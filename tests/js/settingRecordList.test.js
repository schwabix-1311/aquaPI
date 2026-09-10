// Unit tests for the pure row <-> value helpers of the SettingRecordList
// widget. Run: node --test "tests/js/**/*.test.js"

import test from 'node:test'
import assert from 'node:assert/strict'

import {
	subFieldsOf, emptyRow, rowsFromValue, stripRows, nodeFilterFor,
} from '../../aquaPi/static/spa/components/settings/recordListRows.js'

// the Alert.conditions sub-schema (Setting.to_dict() shape)
const SUB = [
	{key: 'class', label: 'alertCondClass', value: 'AlertAbove',
		attrs: {type: 'select', options: ['AlertAbove', 'AlertBelow'],
			optionLabelPrefix: 'misc.alertConds.'}},
	{key: 'node_id', label: 'alertCondWatchedNode', value: null,
		attrs: {type: 'select', nodeFilter: 'numeric'}},
	{key: 'limit', label: 'alertCondLimit', value: 50, attrs: {type: 'number'}},
	{key: 'duration', label: 'alertCondDuration', value: 0, attrs: {type: 'number', min: 0}},
]

test('subFieldsOf reads attrs.recordSchema, tolerates a bare item', () => {
	assert.equal(subFieldsOf({attrs: {recordSchema: SUB}}), SUB)
	assert.deepEqual(subFieldsOf({}), [])
	assert.deepEqual(subFieldsOf(null), [])
})

test('emptyRow seeds every sub-field from its default + a unique _key', () => {
	const a = emptyRow(SUB)
	const b = emptyRow(SUB)
	assert.deepEqual({...a, _key: 0}, {_key: 0, class: 'AlertAbove', node_id: null,
		limit: 50, duration: 0})
	assert.notEqual(a._key, b._key)
})

test('rowsFromValue fills each row, missing sub-field falls back to default', () => {
	const rows = rowsFromValue(
		[{class: 'AlertBelow', node_id: 'wasser', limit: 12}], SUB)
	assert.equal(rows.length, 1)
	assert.equal(rows[0].class, 'AlertBelow')
	assert.equal(rows[0].node_id, 'wasser')
	assert.equal(rows[0].limit, 12)
	assert.equal(rows[0].duration, 0)           // from default
	assert.ok(rows[0]._key)
	assert.deepEqual(rowsFromValue(null, SUB), [])
})

test('stripRows drops _key, sorts keys (to match the API), coerces numbers', () => {
	const rows = [{_key: 'x', duration: '5', limit: '24',
		node_id: 'wasser', class: 'AlertBelow', junk: 1}]
	const out = stripRows(rows, SUB)
	assert.deepEqual(out, [{class: 'AlertBelow', node_id: 'wasser',
		limit: 24, duration: 5}])
	// keys alphabetical, so a value round-tripped through the API stays
	// byte-identical (the Flask JSON encoder sorts keys)
	assert.deepEqual(Object.keys(out[0]), ['class', 'duration', 'limit', 'node_id'])
})

test('stripRows leaves a blank number blank (server rejects a required blank)', () => {
	const out = stripRows([{_key: 'x', class: 'AlertAbove', node_id: 'w',
		limit: '', duration: 0}], SUB)
	assert.equal(out[0].limit, '')
})

test('rowsFromValue -> stripRows round-trips a value unchanged', () => {
	const value = [
		{class: 'AlertAbove', node_id: 'wasser', limit: 30, duration: 0},
		{class: 'AlertBelow', node_id: 'luft', limit: 5, duration: 10},
	]
	assert.deepEqual(stripRows(rowsFromValue(value, SUB), SUB), value)
})

test('nodeFilterFor: plain nodeFilter, and per-class override wins', () => {
	assert.equal(nodeFilterFor(SUB[1], {class: 'AlertAbove'}), 'numeric')
	const perClass = {attrs: {nodeFilter: 'numeric',
		nodeFilterByClass: {AlertLongActive: 'binary'}}}
	assert.equal(nodeFilterFor(perClass, {class: 'AlertLongActive'}), 'binary')
	assert.equal(nodeFilterFor(perClass, {class: 'AlertAbove'}), 'numeric')
	assert.equal(nodeFilterFor({attrs: {}}, {}), null)
})
