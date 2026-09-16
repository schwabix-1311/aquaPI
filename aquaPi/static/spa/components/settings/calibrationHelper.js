// 2-point calibration helper for ScaleAux's offset/factor fields - not a
// Setting-driven widget (ScaleAux only ever persists offset/factor, see
// aux_nodes.py get_settings_schema()), a bespoke component that computes
// offset/factor from two (measured, reference) points and writes the
// result directly into the SAME offset/factor fields each host page
// already has (wiringNodeDialog.js's staged form.fields, or
// NodeSettingsFields' immediate PUT) - see ./scaleCalibration.js for the
// math. Labeling is user-perspective, not wire-perspective: "Messwert"
// is what's read off the live sensor, "Referenz" is the known/target
// value the user provides (a pH buffer's value, or a fan-curve's target
// %) - not ScaleAux's own "receives"/output terms.
//
// Used both by NodeSettingsFields (/parameters) and WiringNodeDialog's
// edit dialog (/wiring) - never the /wiring create dialog, calibrating
// needs a live reading from an already-wired node.

import {registerGlobalComponent} from '../app/registry.js'
import {computeOffsetFactor} from './scaleCalibration.js'

// Referenz v-combobox suggestions, keyed by referenceUnit - free typing
// always still works regardless; a unit with no entry here (or none at
// all) just gets an empty suggestion list. pH: common buffer-solution
// values. %: round quarter-steps, useful for a fan-curve's 0/100-style
// target endpoints.
const REFERENCE_SUGGESTIONS_BY_UNIT = {
	'pH': [4.0, 6.86, 7.0, 9.18, 10.0],
	'%': [0, 25, 50, 75, 100],
}

// module-level (not a component method) so data() can call it directly,
// independent of Vue's methods-vs-data setup ordering - clones, never
// holds a live reference into the currentPoints prop: editing the seeded
// fields must not mutate the node's real data
function seedPoints(currentPoints) {
	if (currentPoints && currentPoints.length === 2) {
		return currentPoints.map(p => ({measured: p.measured, reference: p.reference}))
	}
	return [
		{measured: null, reference: null},
		{measured: null, reference: null},
	]
}

const CalibrationHelper = {
	props: {
		measuredUnit: {type: String, default: ''},
		referenceUnit: {type: String, default: ''},
		currentMeasuredValue: {type: Number, default: null},
		// the node's actually-stored points (e.g. from a template insert,
		// or just never re-touched since creation) - seeds the entry
		// fields below so an existing calibration is visible and editable
		// in place, rather than looking uncalibrated until overwritten
		currentPoints: {type: Array, default: null},
	},
	template: `
			<div class="mb-3">
			<div class="text-subtitle-2 mb-2">{{ $t('misc.calibration.heading') }}</div>
			<v-row v-for="(point, idx) in points" :key="idx" dense align="center">
				<v-col cols="12" sm="6" md="4">
					<v-combobox
						v-model="point.reference"
						:items="referenceSuggestions"
						:label="referenceLabel"
						density="compact" variant="outlined" hide-details="auto"
						autocomplete="off" clearable
					></v-combobox>
				</v-col>
				<v-col cols="12" sm="6" md="4">
					<v-text-field
						v-model.number="point.measured"
						:label="measuredLabel"
						type="number" step="any"
						:readonly="followingIndex === idx"
						:class="{'aquapi-calibration-flash': flashIndex === idx}"
						density="compact" variant="outlined" hide-details="auto"
						autocomplete="off"
					>
						<template #append-inner>
							<v-btn
								icon size="x-small" variant="text"
								:disabled="currentMeasuredValue === null"
								:color="followingIndex === idx ? 'primary' : undefined"
								:title="followingIndex === idx
									? $t('misc.calibration.readSensorStop')
									: $t('misc.calibration.readSensorStart')"
								@click="toggleFollow(idx)"
							><v-icon size="small">{{ followingIndex === idx ? 'mdi-record-circle' : 'mdi-target' }}</v-icon></v-btn>
						</template>
					</v-text-field>
				</v-col>
			</v-row>

			<div v-if="preview" class="text-caption grey--text mt-2">
				{{ $t('misc.calibration.preview', {offset: preview.offset.toFixed(4), factor: preview.factor.toFixed(4)}) }}
			</div>
			<v-alert v-else-if="degenerate" type="warning" density="compact" variant="text" class="mt-2 pa-0">
				{{ $t('misc.calibration.identicalMeasured') }}
			</v-alert>

			<div v-if="showJblHint" class="text-caption grey--text mt-2">
				<div>{{ $t('misc.calibration.jblHint') }}</div>
				<div v-if="measuredDiff !== null">
					{{ $t('misc.calibration.measuredDiff', {diff: measuredDiff.toFixed(3)}) }}
				</div>
			</div>

			<v-btn
				class="mt-3" color="primary" size="small"
				:disabled="!preview"
				@click="apply"
			>{{ $t('misc.calibration.apply') }}</v-btn>
			</div>
	`,
	data: function() {
		return {
			points: seedPoints(this.currentPoints),
			// index (0/1) of the point row currently live-following
			// currentMeasuredValue, or null if neither is - mutually
			// exclusive by construction (a single index, not two flags),
			// so turning one row's toggle on always turns the other off
			followingIndex: null,
			// index of the row to briefly flash (stock-ticker style) after
			// its Messwert just changed from a live update
			flashIndex: null,
		}
	},
	watch: {
		// the host dialog/component instance can be reused across
		// different nodes (e.g. switching which node is being edited
		// without a remount) - re-seed whenever the underlying node's
		// own points genuinely change. NOT just whenever this prop's
		// array happens to get a new reference: a ScaleAux re-posts (and
		// therefore gets a fresh SSE-pushed node object, points array
		// included - see App.vue.js) every time its own upstream source
		// ticks, even though its *stored* points haven't changed at all -
		// comparing by value, not by reference, is what keeps a live
		// follow (below) from being silently reset moments after it starts
		currentPoints: function(newVal, oldVal) {
			if (JSON.stringify(newVal) === JSON.stringify(oldVal)) return
			this.points = seedPoints(newVal)
			this.followingIndex = null
		},
		// this is what makes a locked (following) field keep updating as
		// new readings arrive via SSE (dashboardStore.setNode(), see
		// App.vue.js) - currentMeasuredValue is already reactively bound
		// to the source node's live .data by the host component
		currentMeasuredValue: function(newVal) {
			if (this.followingIndex === null || newVal === null) return
			this.points[this.followingIndex].measured = newVal
			const idx = this.followingIndex
			this.flashIndex = idx
			setTimeout(() => {
				if (this.flashIndex === idx) this.flashIndex = null
			}, 600)
		},
	},
	computed: {
		measuredLabel: function() {
			return this.$t('misc.calibration.measured', {unit: this.measuredUnit})
		},
		referenceLabel: function() {
			return this.$t('misc.calibration.reference', {unit: this.referenceUnit})
		},
		isPhFromVoltage: function() {
			return this.measuredUnit === 'V' && this.referenceUnit === 'pH'
		},
		referenceSuggestions: function() {
			return REFERENCE_SUGGESTIONS_BY_UNIT[this.referenceUnit] || []
		},
		showJblHint: function() {
			return this.isPhFromVoltage
		},
		bothPointsFilled: function() {
			return this.points.every(p =>
				p.measured !== null && p.measured !== '' &&
				p.reference !== null && p.reference !== '')
		},
		preview: function() {
			if (!this.bothPointsFilled) return null
			try {
				return computeOffsetFactor(
					{measured: Number(this.points[0].measured), reference: Number(this.points[0].reference)},
					{measured: Number(this.points[1].measured), reference: Number(this.points[1].reference)},
				)
			} catch (e) {
				return null
			}
		},
		degenerate: function() {
			return this.bothPointsFilled && !this.preview
		},
		measuredDiff: function() {
			if (!this.bothPointsFilled) return null
			return Math.abs(Number(this.points[1].measured) - Number(this.points[0].measured))
		},
	},
	methods: {
		toggleFollow: function(idx) {
			if (this.followingIndex === idx) {
				// turn off - freeze whatever's currently shown
				this.followingIndex = null
				return
			}
			// switching row (or turning on from off) - the other row, if
			// any, stops following as a side effect of only one index
			// ever being tracked; snapshot right away instead of waiting
			// for the next live reading to arrive
			this.followingIndex = idx
			if (this.currentMeasuredValue !== null) {
				this.points[idx].measured = this.currentMeasuredValue
			}
		},
		apply: function() {
			if (!this.preview) return
			// the raw points travel along too (measured+reference, the
			// literal shape hist_nodes.py's log_calibration_event()
			// expects) - so a recalibration's history can show what was
			// actually measured, not just the offset/factor it produced
			this.$emit('apply', {
				...this.preview,
				points: this.points.map(p => ({
					measured: Number(p.measured), reference: Number(p.reference),
				})),
			})
		},
	},
}
registerGlobalComponent('CalibrationHelper', CalibrationHelper)

// vim: set noet ts=4 sw=4:
