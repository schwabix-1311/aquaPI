// Unit tests for wiringConnect.js - the single source/target rule that
// replaced the SOURCEABLE_ROLES whitelist and the ad-hoc receives-item
// filters. Run: node --test "tests/js/**/*.test.js"

import test from 'node:test'
import assert from 'node:assert/strict'

import {
	canConnect, connectableSources, isUsableSource,
	isNumericSource, targetAcceptsReceives, findDropTarget,
} from '../../aquaPi/static/spa/components/wiring/wiringConnect.js'

const NODE_TYPES = {
	AnalogInput: {receives: 'none', data_range: 'ANALOG'},
	SwitchInput: {receives: 'none', data_range: 'BINARY'},
	TextInput: {receives: 'none', data_range: 'STRING'},
	MinimumCtrl: {receives: 'single', data_range: 'BINARY'},
	AnalogDevice: {receives: 'single', data_range: 'PERCENT'},
	AvgAux: {receives: 'multi', data_range: 'UNDEF'},
	History: {receives: 'multi', data_range: 'UNDEF'},
	Alert: {receives: 'none', data_range: 'STRING'},
}

const sensor = {id: 'sensor', type: 'AnalogInput', role: 'IN_ENDP', data_range: 'ANALOG'}
const text = {id: 'text', type: 'TextInput', role: 'IN_ENDP', data_range: 'STRING'}
const ctrl = {id: 'ctrl', type: 'MinimumCtrl', role: 'CTRL', data_range: 'BINARY'}
const dev = {id: 'dev', type: 'AnalogDevice', role: 'OUT_ENDP', data_range: 'PERCENT'}
const hist = {id: 'hist', type: 'History', role: 'HISTORY', data_range: 'UNDEF'}
const alert = {id: 'alert', type: 'Alert', role: 'ALERTS', data_range: 'STRING'}

test('a plain numeric sensor can feed a controller', () => {
	assert.equal(canConnect(sensor, ctrl, NODE_TYPES), true)
})

test('an output device is a valid source (it posts its actuated value)', () => {
	assert.equal(isUsableSource(dev, NODE_TYPES), true)
	assert.equal(canConnect(dev, hist, NODE_TYPES), true)
})

test('a History is never a source (constant keep-alive)', () => {
	assert.equal(isUsableSource(hist, NODE_TYPES), false)
	assert.equal(canConnect(hist, ctrl, NODE_TYPES), false)
})

test('STRING sources (Alert, TextInput) are never usable', () => {
	assert.equal(isUsableSource(alert, NODE_TYPES), false)
	assert.equal(isUsableSource(text, NODE_TYPES), false)
	assert.equal(canConnect(alert, hist, NODE_TYPES), false)
	assert.equal(canConnect(text, hist, NODE_TYPES), false)
})

test('an Alert is never a valid target (receives derived from conditions)', () => {
	assert.equal(targetAcceptsReceives(alert, NODE_TYPES), false)
	assert.equal(canConnect(sensor, alert, NODE_TYPES), false)
})

test('a node cannot connect to itself', () => {
	assert.equal(canConnect(ctrl, ctrl, NODE_TYPES), false)
})

test('a type with receives:none is not a valid target', () => {
	assert.equal(targetAcceptsReceives(sensor, NODE_TYPES), false)
})

test('unsaved draft node: data_range falls back to the type schema', () => {
	const draftText = {id: 'd1', type: 'TextInput', role: 'IN_ENDP'}  // no data_range yet
	assert.equal(isUsableSource(draftText, NODE_TYPES), false)
	const draftSensor = {id: 'd2', type: 'AnalogInput', role: 'IN_ENDP'}
	assert.equal(isUsableSource(draftSensor, NODE_TYPES), true)
})

test('connectableSources: History picker offers only usable, non-STRING producers', () => {
	const all = {sensor, text, ctrl, dev, hist, alert}
	const ids = connectableSources(hist, all, NODE_TYPES).map(n => n.id).sort()
	assert.deepEqual(ids, ['ctrl', 'dev', 'sensor'])
})

test('connectableSources accepts an array too', () => {
	const ids = connectableSources(ctrl, [sensor, text, alert, hist], NODE_TYPES).map(n => n.id)
	assert.deepEqual(ids, ['sensor'])
})

test('isNumericSource: only ANALOG/PERCENT/BINARY, never STRING or UNDEF', () => {
	assert.equal(isNumericSource(sensor, NODE_TYPES), true)   // ANALOG
	assert.equal(isNumericSource(ctrl, NODE_TYPES), true)     // BINARY
	assert.equal(isNumericSource(dev, NODE_TYPES), true)      // PERCENT
	assert.equal(isNumericSource(alert, NODE_TYPES), false)   // STRING
	assert.equal(isNumericSource(hist, NODE_TYPES), false)    // UNDEF
})

// findDropTarget() - regression coverage for a real bug found via a live
// pointer-drag repro (not reachable from a pure state-layer test alone):
// dropping a connection exactly on the target's port dot silently
// registered nothing, because comps.js centers that dot ON the node
// box's edge line - a drop landing there sits right on the hit-test
// boundary and can miss it by a sub-pixel rounding difference.
const BOX_W = 240, BOX_H = 76
const nodeAt = (id, x, y) => ({id, pos_x: x, pos_y: y})

test('findDropTarget: a point inside the box matches', () => {
	const target = nodeAt('t', 500, 900)
	const hit = findDropTarget([target], 's', 550, 920, 16, BOX_W, BOX_H)
	assert.equal(hit, target)
})

test('findDropTarget: a point exactly on the box edge (the input port dot' +
    ' position) matches with margin, would miss with none', () => {
	const target = nodeAt('t', 500, 900)
	// the input port sits at (pos_x, pos_y + BOX_H/2) - right on the left edge
	const portX = 500, portY = 900 + BOX_H / 2
	assert.equal(findDropTarget([target], 's', portX, portY, 16, BOX_W, BOX_H), target)
	assert.equal(findDropTarget([target], 's', portX - 1, portY, 0, BOX_W, BOX_H), null)
})

test('findDropTarget: a point beyond the margin does not match', () => {
	const target = nodeAt('t', 500, 900)
	assert.equal(findDropTarget([target], 's', 500 - 20, 920, 16, BOX_W, BOX_H), null)
})

test('findDropTarget: excludes the dragged node itself even if the point is over it', () => {
	const self = nodeAt('s', 500, 900)
	assert.equal(findDropTarget([self], 's', 550, 920, 16, BOX_W, BOX_H), null)
})
