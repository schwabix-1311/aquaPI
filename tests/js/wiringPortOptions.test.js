// Unit tests for wiringPortOptions.draftPortOptions - the draft-aware
// port picker list for the /wiring add/edit dialog.
// Run: node --test "tests/js/**/*.test.js"

import test from 'node:test'
import assert from 'node:assert/strict'

import {draftPortOptions} from '../../aquaPi/static/spa/components/wiring/wiringPortOptions.js'

const ALL_BOUT = ['GPIO 0 out', 'GPIO 1 out', 'GPIO 12 out', 'GPIO 13 out']

test('new node: a port a draft edit vacated is offered again', () => {
	// live registry still shows GPIO 0 as used (unsaved Heizstab holds it);
	// the draft has already moved Heizstab to GPIO 12
	const opts = draftPortOptions({
		free: ['GPIO 1 out'],
		allPorts: ALL_BOUT,
		ownPort: '',
		draftNodes: [{id: 'heizstab', port: 'GPIO 12 out'}],
		baselineNodes: [{id: 'heizstab', port: 'GPIO 0 out'}],
		selfId: null,
	})
	assert.deepEqual(opts, ['GPIO 0 out', 'GPIO 1 out'])
})

test('new node: a port a draft edit just claimed disappears', () => {
	const opts = draftPortOptions({
		free: ['GPIO 0 out', 'GPIO 1 out'],
		allPorts: ALL_BOUT,
		draftNodes: [{id: 'x', port: 'GPIO 0 out'}],   // draft-new node took it
		baselineNodes: [],
		selfId: null,
	})
	assert.deepEqual(opts, ['GPIO 1 out'])
})

test('editing a node keeps its own current pick even though it is "in use"', () => {
	const opts = draftPortOptions({
		free: ['GPIO 1 out'],
		allPorts: ALL_BOUT,
		ownPort: 'GPIO 12 out',
		draftNodes: [{id: 'heizstab', port: 'GPIO 12 out'}],
		baselineNodes: [{id: 'heizstab', port: 'GPIO 12 out'}],
		selfId: 'heizstab',
	})
	assert.ok(opts.includes('GPIO 12 out'))
	assert.ok(opts.includes('GPIO 1 out'))
})

test('a vacated port of a different function never leaks in', () => {
	// baseline PWM node freed 'PWM 0'; this is a Bout select
	const opts = draftPortOptions({
		free: ['GPIO 1 out'],
		allPorts: ALL_BOUT,
		draftNodes: [{id: 'dimmer', port: 'TC420 #1 CH1'}],
		baselineNodes: [{id: 'dimmer', port: 'PWM 0'}],
		selfId: null,
	})
	assert.deepEqual(opts, ['GPIO 1 out'])
})

test('no allPorts (registry cold): degrades to free + own, never invents ports', () => {
	const opts = draftPortOptions({
		free: ['GPIO 1 out'],
		allPorts: null,
		ownPort: 'GPIO 12 out',
		draftNodes: [{id: 'heizstab', port: 'GPIO 12 out'}],
		baselineNodes: [{id: 'heizstab', port: 'GPIO 0 out'}],
		selfId: 'heizstab',
	})
	assert.deepEqual(opts, ['GPIO 1 out', 'GPIO 12 out'])
})

test('result is sorted and deduped', () => {
	const opts = draftPortOptions({
		free: ['GPIO 13 out', 'GPIO 1 out'],
		allPorts: ALL_BOUT,
		ownPort: 'GPIO 1 out',
		draftNodes: [],
		baselineNodes: [{id: 'a', port: 'GPIO 1 out'}],
		selfId: 'a',
	})
	assert.deepEqual(opts, ['GPIO 1 out', 'GPIO 13 out'])
})

// vim: set noet ts=4 sw=4:
