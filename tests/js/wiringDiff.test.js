// Unit tests for wiringDiff() - the pure baseline-vs-working diff that
// replaced the /wiring draft's _new/_dirty/_deleted bookkeeping.
// Run: node --test "tests/js/**/*.test.js"

import test from 'node:test'
import assert from 'node:assert/strict'

import {wiringDiff} from '../../aquaPi/static/spa/components/wiring/wiringDiff.js'

const NODE_TYPES = {
	AnalogInput: {receives: 'none', fields: [{key: 'unit'}, {key: 'interval'}]},
	MinimumCtrl: {receives: 'single', fields: [{key: 'setpoint'}]},
	History: {receives: 'multi', fields: [{key: 'capacity'}]},
	Alert: {receives: 'none', fields: [{key: 'repeat'}, {key: 'conditions'}]},
}

// a small realistic baseline: sensor -> ctrl, plus a History on the sensor
function baseline() {
	return {
		sensor: {id: 'sensor', type: 'AnalogInput', name: 'Sensor', role: 'IN_ENDP',
			receives: [], group: '', pos_x: 0, pos_y: 0, unit: 'C', interval: 10},
		ctrl: {id: 'ctrl', type: 'MinimumCtrl', name: 'Ctrl', role: 'CTRL',
			receives: ['sensor'], group: 'Tank', pos_x: 310, pos_y: 0, setpoint: 24},
		hist: {id: 'hist', type: 'History', name: 'Hist', role: 'HISTORY',
			receives: ['sensor'], group: '', pos_x: 620, pos_y: 0, capacity: 1000},
	}
}
const clone = (o) => JSON.parse(JSON.stringify(o))

test('no changes -> hasChanges false, all lists empty', () => {
	const d = wiringDiff(baseline(), clone(baseline()), NODE_TYPES)
	assert.equal(d.hasChanges, false)
	assert.deepEqual(d, {creates: [], updates: [], deletes: [], hasChanges: false})
})

test('pos-only change -> update carries only the moved coordinate', () => {
	const w = clone(baseline())
	w.ctrl.pos_x = 999
	const d = wiringDiff(baseline(), w, NODE_TYPES)
	assert.deepEqual(d.updates, [{id: 'ctrl', pos_x: 999}])
	assert.equal(d.creates.length, 0)
	assert.equal(d.deletes.length, 0)
})

test('group-only change -> update carries only group', () => {
	const w = clone(baseline())
	w.ctrl.group = 'Becken 2'
	const d = wiringDiff(baseline(), w, NODE_TYPES)
	assert.deepEqual(d.updates, [{id: 'ctrl', group: 'Becken 2'}])
})

test('receives change -> update carries receives (for a type that accepts it)', () => {
	const w = clone(baseline())
	w.hist.receives = ['sensor', 'ctrl']
	const d = wiringDiff(baseline(), w, NODE_TYPES)
	assert.deepEqual(d.updates, [{id: 'hist', receives: ['sensor', 'ctrl']}])
})

test('field change -> update carries the full fields object for that node', () => {
	const w = clone(baseline())
	w.hist.capacity = 5000
	const d = wiringDiff(baseline(), w, NODE_TYPES)
	assert.deepEqual(d.updates, [{id: 'hist', fields: {capacity: 5000}}])
})

test('new node -> create entry with temp_id and full shape, no update', () => {
	const w = clone(baseline())
	w['draft-1'] = {id: 'draft-1', _tempId: 'draft-1', type: 'AnalogInput',
		name: 'Neu', role: 'IN_ENDP', receives: [], group: 'G',
		pos_x: 20, pos_y: 20, unit: 'pH', interval: 5}
	const d = wiringDiff(baseline(), w, NODE_TYPES)
	assert.equal(d.updates.length, 0)
	assert.deepEqual(d.creates, [{
		temp_id: 'draft-1', type: 'AnalogInput', name: 'Neu',
		receives: [], fields: {unit: 'pH', interval: 5},
		group: 'G', pos_x: 20, pos_y: 20,
	}])
})

test('deleted source -> delete entry + pruned survivor receives', () => {
	const w = clone(baseline())
	delete w.sensor
	// the store's draftDeleteNode would also prune this; here we do it by hand
	w.ctrl.receives = []
	w.hist.receives = []
	const d = wiringDiff(baseline(), w, NODE_TYPES)
	assert.deepEqual(d.deletes, ['sensor'])
	const byId = Object.fromEntries(d.updates.map(u => [u.id, u]))
	assert.deepEqual(byId.ctrl, {id: 'ctrl', receives: []})
	assert.deepEqual(byId.hist, {id: 'hist', receives: []})
})

test('Alert: receives is never emitted even when it differs (schema says none)', () => {
	const base = {
		alert: {id: 'alert', type: 'Alert', name: 'A', role: 'ALERTS',
			receives: ['sensor'], group: '', pos_x: 0, pos_y: 0, repeat: 3600,
			conditions: [{class: 'AlertAbove', node_id: 'sensor', limit: 30, duration: 0}]},
	}
	const w = clone(base)
	w.alert.receives = ['sensor', 'ctrl']   // e.g. a stale prune
	w.alert.pos_x = 42
	const d = wiringDiff(base, w, NODE_TYPES)
	assert.deepEqual(d.updates, [{id: 'alert', pos_x: 42}])
})

test('Alert: a conditions change is carried in fields; unchanged -> no fields', () => {
	const base = {
		alert: {id: 'alert', type: 'Alert', name: 'A', role: 'ALERTS',
			receives: ['sensor'], group: '', pos_x: 0, pos_y: 0, repeat: 3600,
			conditions: [{class: 'AlertAbove', node_id: 'sensor', limit: 30, duration: 0}]},
	}
	// pos moved, conditions untouched -> update has no `fields`
	let w = clone(base)
	w.alert.pos_x = 10
	assert.deepEqual(wiringDiff(base, w, NODE_TYPES).updates, [{id: 'alert', pos_x: 10}])

	// a condition limit changed -> the whole conditions list rides in `fields`
	w = clone(base)
	w.alert.conditions[0].limit = 25
	const d = wiringDiff(base, w, NODE_TYPES)
	assert.deepEqual(d.updates, [{id: 'alert', fields: {
		repeat: 3600,
		conditions: [{class: 'AlertAbove', node_id: 'sensor', limit: 25, duration: 0}],
	}}])
})

test('missing nodeTypes entry: pos/group/receives still diffed, fields skipped', () => {
	const base = {
		x: {id: 'x', type: 'Unknown', name: 'X', role: 'AUX',
			receives: ['a'], group: '', pos_x: 0, pos_y: 0, foo: 1},
	}
	const w = clone(base)
	w.x.pos_y = 50
	w.x.foo = 2
	const d = wiringDiff(base, w, {})
	// no schema -> receives kind unknown -> not emitted; fields not emitted
	assert.deepEqual(d.updates, [{id: 'x', pos_y: 50}])
})

test('null baseline or working -> no changes', () => {
	assert.equal(wiringDiff(null, {}, NODE_TYPES).hasChanges, false)
	assert.equal(wiringDiff({}, null, NODE_TYPES).hasChanges, false)
})
