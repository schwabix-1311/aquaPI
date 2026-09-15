// Pure math for the CalibrationHelper widget: derive a ScaleAux node's
// offset/factor from two (measured, reference) points, kept import-free
// so it - and its node:test unit tests - never pull in the Vue
// components. Mirrors ScaleAux.__init__'s own factor/offset derivation
// (aquaPi/machineroom/aux_nodes.py) exactly.

export function computeOffsetFactor(point1, point2) {
	const dX = point2.measured - point1.measured
	if (!dX) {
		throw new Error('identicalMeasured')
	}
	const factor = (point2.reference - point1.reference) / dX
	const offset = point1.reference - factor * point1.measured
	return {offset, factor}
}
