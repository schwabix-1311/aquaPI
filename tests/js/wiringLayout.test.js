// Unit tests for the /wiring canvas chain-layout algorithm.
// Run: node --test tests/js/
//
// computeLayout() is pure (no Vue, no store), so it can be exercised
// directly here. Geometry constants it uses:
//   NODE_BOX_WIDTH  = 240, LAYOUT_COL_GAP = 70  -> col pitch 310
//   NODE_BOX_HEIGHT = 76,  LAYOUT_ROW_GAP = 50  -> row pitch 126
//   a node with >1 incoming wire is nudged down by NODE_BOX_HEIGHT/2 = 38

import test from 'node:test'
import assert from 'node:assert/strict'

import {computeLayout} from '../../aquaPi/static/spa/components/wiring/wiringLayout.js'

const COL = 240 + 70
const ROW = 76 + 50
const OFFSET = 76 / 2

// terse node factory
const n = (id, role, receives = []) => ({id, role, receives})

test('plain chain: column = depth from root, single row', () => {
	const nodes = [
		n('sensor', 'IN_ENDP'),
		n('ctrl', 'CTRL', ['sensor']),
		n('dev', 'OUT_ENDP', ['ctrl']),
	]
	const l = computeLayout(nodes)
	assert.deepEqual(l.get('sensor'), {pos_x: 0, pos_y: 0})
	assert.deepEqual(l.get('ctrl'), {pos_x: COL, pos_y: 0})
	assert.deepEqual(l.get('dev'), {pos_x: 2 * COL, pos_y: 0})
})

test('fan-out: first listener keeps the row, the rest drop to new rows', () => {
	const nodes = [
		n('sensor', 'IN_ENDP'),
		n('ctrlA', 'CTRL', ['sensor']),
		n('ctrlB', 'CTRL', ['sensor']),
	]
	const l = computeLayout(nodes)
	assert.deepEqual(l.get('sensor'), {pos_x: 0, pos_y: 0})
	assert.deepEqual(l.get('ctrlA'), {pos_x: COL, pos_y: 0})
	assert.deepEqual(l.get('ctrlB'), {pos_x: COL, pos_y: ROW})
})

test('History sink: median source row, one column past the rightmost source, offset for >1 wire', () => {
	const nodes = [
		n('sensor', 'IN_ENDP'),
		n('ctrl', 'CTRL', ['sensor']),
		n('hist', 'HISTORY', ['sensor', 'ctrl']),
	]
	const l = computeLayout(nodes)
	// sources sit at rows [0, 0] -> median 0; rightmost col is ctrl's (1) -> col 2
	// hist has 2 incoming wires -> +OFFSET on y
	assert.deepEqual(l.get('hist'), {pos_x: 2 * COL, pos_y: OFFSET})
})

test('Alert with no resolvable sources falls back to its own fresh row at column 0', () => {
	const nodes = [
		n('sensor', 'IN_ENDP'),
		n('ctrl', 'CTRL', ['sensor']),
		n('alert', 'ALERTS', ['*']),
	]
	const l = computeLayout(nodes)
	assert.equal(l.get('alert').pos_x, 0)
	// placed on a row of its own, below the one-row sensor->ctrl chain
	assert.ok(l.get('alert').pos_y >= ROW)
})

test('orphaned two-node receives cycle: both still get a position', () => {
	const nodes = [
		n('a', 'AUX', ['b']),
		n('b', 'AUX', ['a']),
	]
	const l = computeLayout(nodes)
	assert.ok(l.has('a') && l.has('b'))
	assert.notDeepEqual(l.get('a'), l.get('b'))
})

test('a merge node (2 real inputs) gets the vertical half-box offset', () => {
	const nodes = [
		n('s1', 'IN_ENDP'),
		n('s2', 'IN_ENDP'),
		n('avg', 'AUX', ['s1', 's2']),
	]
	const l = computeLayout(nodes)
	assert.equal(l.get('avg').pos_y % ROW, OFFSET)
})

test('every node in the input appears exactly once in the output', () => {
	const nodes = [
		n('s1', 'IN_ENDP'), n('s2', 'IN_ENDP'),
		n('c1', 'CTRL', ['s1']), n('c2', 'CTRL', ['s2']),
		n('d1', 'OUT_ENDP', ['c1']),
		n('h', 'HISTORY', ['s1', 's2']),
		n('lonely', 'IN_ENDP'),
	]
	const l = computeLayout(nodes)
	assert.equal(l.size, nodes.length)
	for (const node of nodes) assert.ok(l.has(node.id), `missing ${node.id}`)
})
