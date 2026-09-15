// Compact calibration-history readout for a ScaleAux node: surfaces the
// existing, previously-unused GET /api/nodes/<id>/calibration-log
// (aquaPi/machineroom/hist_nodes.py's "Step 28" mechanism, auto-recorded
// whenever ScaleAux.points changes via PUT /api/nodes/<id>/settings or
// /wiring's save path). Read-only, no chart in this pass - just enough
// to see when this node was last recalibrated and by how much, since
// probes drift gradually rather than jumping between known points.
//
// One calibration event is exactly one row here: {ts, old_points: [...2],
// new_points: [...2]}, each point {measured, reference} - points is
// ScaleAux's sole/canonical calibration state now (offset/factor are
// always freshly derived from it, never independently stored), so
// there's no reassembly to do on this side and no fallback case to
// handle: every logged event always has points.
//
// Shown as the reference/measured pair itself ("6.9 pH = 2.51 V"), not
// offset/factor - those are internal linear-scaling math, not
// something a user reading history can interpret at a glance (what
// does "offset -25.2" mean for a pH probe?).

import {registerGlobalComponent} from '../app/registry.js'
import {useSettingsStore} from '../../store/modules/settings.js'
import i18n from '../../i18n/index.js'

const CalibrationHistory = {
	props: {
		nodeId: {type: String, required: true},
		measuredUnit: {type: String, default: ''},
		referenceUnit: {type: String, default: ''},
	},
	template: `
		<div class="mb-3">
			<div class="text-subtitle-2 mb-1">{{ $t('misc.calibration.historyHeading') }}</div>
			<div v-if="loading" class="text-caption grey--text">
				<aquapi-loading-indicator :size="16" color="primary"></aquapi-loading-indicator>
			</div>
			<div v-else-if="!entries.length" class="text-caption grey--text">
				{{ $t('misc.calibration.historyEmpty') }}
			</div>
			<v-list v-else density="compact" class="pa-0">
				<v-list-item v-for="(entry, idx) in entries" :key="idx" class="px-0" min-height="28">
					<v-list-item-title class="text-caption">
						{{ formatTs(entry.ts) }}: {{ pointsLine(entry.new_points) }}
					</v-list-item-title>
				</v-list-item>
			</v-list>
		</div>
	`,
	data: function() {
		return {
			loading: true,
		}
	},
	computed: {
		settingsStore() {
			return useSettingsStore()
		},
		entries: function() {
			return this.settingsStore.calibrationLogForNode(this.nodeId)
		},
	},
	methods: {
		formatTs: function(ts) {
			return new Date(ts).toLocaleString(i18n.global.locale.value)
		},
		pointsLine: function(points) {
			// same Referenz-first pairing order as CalibrationHelper's own
			// fields, e.g. "6.9 pH = 2.51 V, 4 pH = 2.99 V"
			return points
				.map(p => p.reference + ' ' + this.referenceUnit + ' = ' + p.measured + ' ' + this.measuredUnit)
				.join(', ')
		},
	},
	mounted: function() {
		this.loading = true
		this.settingsStore.fetchCalibrationLog(this.nodeId)
			.finally(() => { this.loading = false })
	},
}
registerGlobalComponent('CalibrationHistory', CalibrationHistory)

// vim: set noet ts=4 sw=4:
