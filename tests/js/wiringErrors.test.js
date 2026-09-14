// Unit tests for resolveConfigDiffError() - resolving a failed
// POST /api/config/apply result into a localized message.
// Run: node --test "tests/js/**/*.test.js"

import test from 'node:test'
import assert from 'node:assert/strict'

import {resolveConfigDiffError} from '../../aquaPi/static/spa/components/wiring/wiringErrors.js'

// a minimal $t stand-in: records calls, returns something derived from
// the key so assertions can check both the key used and the params passed
function fakeT(calls) {
	return (key, params) => {
		calls.push({key, params})
		return `[${key}${params ? ':' + JSON.stringify(params) : ''}]`
	}
}

test('falls back to the raw error string when no key/items are present', () => {
	const calls = []
	const msg = resolveConfigDiffError({error: 'raw fallback text'}, fakeT(calls))
	assert.equal(msg, 'raw fallback text')
	assert.equal(calls.length, 0)
})

test('resolves a single errorKey with errorParams', () => {
	const calls = []
	const msg = resolveConfigDiffError({
		error: 'fallback', errorKey: 'cycleDetected', errorParams: null,
	}, fakeT(calls))
	assert.equal(msg, '[pages.wiring.errors.cycleDetected]')
	assert.deepEqual(calls, [{key: 'pages.wiring.errors.cycleDetected', params: null}])
})

test('errorItems: joins multiple resolved messages with "; "', () => {
	const calls = []
	const msg = resolveConfigDiffError({
		error: 'fallback',
		errorItems: [
			{key: 'notConnected', params: {node: 'Lueftersteuerung'}},
			{key: 'missingValue', params: {node: 'Kuehlungsluefter', fieldLabel: 'outputPort'}},
		],
	}, fakeT(calls))
	assert.equal(
		msg,
		'[pages.wiring.errors.notConnected:{"node":"Lueftersteuerung"}]; '
		+ '[pages.wiring.errors.missingValue:{"node":"Kuehlungsluefter","fieldLabel":"[pages.settings.fields.outputPort]"}]'
	)
})

test('errorItems: missingValue resolves fieldLabel via pages.settings.fields first', () => {
	const calls = []
	resolveConfigDiffError({
		errorItems: [{key: 'missingValue', params: {node: 'X', fieldLabel: 'setpoint'}}],
	}, fakeT(calls))
	// first call resolves the field label itself, second the outer sentence
	assert.equal(calls[0].key, 'pages.settings.fields.setpoint')
	assert.equal(calls[1].key, 'pages.wiring.errors.missingValue')
	assert.equal(calls[1].params.fieldLabel, '[pages.settings.fields.setpoint]')
})

test('errorItems takes priority over errorKey when both are present', () => {
	const calls = []
	const msg = resolveConfigDiffError({
		error: 'fallback', errorKey: 'cycleDetected',
		errorItems: [{key: 'notConnected', params: {node: 'X'}}],
	}, fakeT(calls))
	assert.equal(msg, '[pages.wiring.errors.notConnected:{"node":"X"}]')
})

// vim: set noet ts=4 sw=4:
