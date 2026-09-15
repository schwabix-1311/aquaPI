// Unit tests for groupCalibrationLog() - merges same-event offset/
// factor calibration_log rows into one entry per event.
// Run: node --test "tests/js/**/*.test.js"

import test from 'node:test'
import assert from 'node:assert/strict'

import {groupCalibrationLog} from '../../aquaPi/static/spa/components/settings/calibrationHistoryGrouping.js'

test('merges offset+factor rows from the same event (sub-second apart) into one group', () => {
	const groups = groupCalibrationLog([
		{ts: '2026-09-15T18:44:48.367291', field: 'factor', old_value: -6.04, new_value: -25.24},
		{ts: '2026-09-15T18:44:48.357660', field: 'offset', old_value: 22.06, new_value: 70.25},
	])
	assert.equal(groups.length, 1)
	assert.deepEqual(groups[0].factor, {old: -6.04, new: -25.24})
	assert.deepEqual(groups[0].offset, {old: 22.06, new: 70.25})
})

test('keeps events in different seconds as separate groups, newest first preserved', () => {
	const groups = groupCalibrationLog([
		{ts: '2026-09-15T18:44:48.0', field: 'offset', old_value: 1, new_value: 2},
		{ts: '2026-09-14T10:00:00.0', field: 'offset', old_value: 0, new_value: 1},
	])
	assert.equal(groups.length, 2)
	assert.equal(groups[0].ts, '2026-09-15T18:44:48.0')
	assert.equal(groups[1].ts, '2026-09-14T10:00:00.0')
})

test('a single-field event (only offset, or only factor) leaves the other null', () => {
	const groups = groupCalibrationLog([
		{ts: '2026-09-15T18:44:48.0', field: 'offset', old_value: 1, new_value: 2},
	])
	assert.equal(groups.length, 1)
	assert.deepEqual(groups[0].offset, {old: 1, new: 2})
	assert.equal(groups[0].factor, null)
})

test('empty/undefined input returns an empty array', () => {
	assert.deepEqual(groupCalibrationLog([]), [])
	assert.deepEqual(groupCalibrationLog(undefined), [])
})
