// Unit tests for wiringConnect.js - the single source/target rule that
// replaced the SOURCEABLE_ROLES whitelist and the ad-hoc receives-item
// filters. Run: node --test "tests/js/**/*.test.js"

import test from 'node:test'
import assert from 'node:assert/strict'

import {
	canConnect, connectableSources, isUsableSource,
	isNumericSource, targetAcceptsReceives,
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
