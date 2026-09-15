// Unit tests for computeOffsetFactor() - the 2-point calibration math
// behind CalibrationHelper, mirroring ScaleAux.__init__'s own derivation.
// Run: node --test "tests/js/**/*.test.js"

import test from 'node:test'
import assert from 'node:assert/strict'

import {computeOffsetFactor} from '../../aquaPi/static/spa/components/settings/scaleCalibration.js'

test('pH-style two points: derives the expected offset/factor', () => {
	// matches the "pH Wert" node's own real-world calibration:
	// points=[(2.99, 4.0), (2.51, 6.9)]
	const {offset, factor} = computeOffsetFactor(
		{measured: 2.99, reference: 4.0},
		{measured: 2.51, reference: 6.9},
	)
	const dX = 2.51 - 2.99
	const expectedFactor = (6.9 - 4.0) / dX
	assert.equal(factor, expectedFactor)
	assert.equal(offset, 4.0 - expectedFactor * 2.99)
})

test('fan-curve style two points: derives the expected offset/factor', () => {
	// matches the shipped cooling-fan template's own derivation:
	// points=[(26.0, 0), (28.0, 100)] -> factor=50, offset=-1300
	const {offset, factor} = computeOffsetFactor(
		{measured: 26.0, reference: 0},
		{measured: 28.0, reference: 100},
	)
	assert.equal(factor, 50)
	assert.equal(offset, -1300)
})

test('order of the two points does not change the result', () => {
	const a = computeOffsetFactor(
		{measured: 26.0, reference: 0}, {measured: 28.0, reference: 100})
	const b = computeOffsetFactor(
		{measured: 28.0, reference: 100}, {measured: 26.0, reference: 0})
	assert.equal(a.factor, b.factor)
	assert.equal(a.offset, b.offset)
})

test('identical measured values throws instead of dividing by zero', () => {
	assert.throws(() => computeOffsetFactor(
		{measured: 2.5, reference: 4.0}, {measured: 2.5, reference: 6.9}))
})
