// Compact calibration-history readout for a ScaleAux node: surfaces the
// existing, previously-unused GET /api/nodes/<id>/calibration-log
// (aquaPi/machineroom/hist_nodes.py's "Step 28" mechanism, auto-recorded
// whenever offset/factor changes via PUT /api/nodes/<id>/settings or -
// once the matching db.py fix ships - /wiring's save path too). Read-only,
// no chart in this pass - just enough to see when this node was last
// recalibrated and by how much, since probes drift gradually rather than
// jumping between known points.

import {registerGlobalComponent} from '../app/registry.js'
import {useSettingsStore} from '../../store/modules/settings.js'
import i18n from '../../i18n/index.js'
import {groupCalibrationLog} from './calibrationHistoryGrouping.js'

// calibration_log's 'field' column stores the raw Setting KEY ('offset'/
// 'factor', see the isinstance(node, ScaleAux) checks in api.py and
// db.py's apply_config_diff), not its i18n LABEL key - ScaleAux's own
// schema (aux_nodes.py) declares factor's label as 'scaleFactor', not
// 'factor' (Setting('factor', 'scaleFactor', ...)), so the two can't be
// resolved by just prefixing 'pages.settings.fields.' onto the raw key
const FIELD_LABEL_KEYS = {offset: 'offset', factor: 'scaleFactor'}

const CalibrationHistory = {
	props: {
		nodeId: {type: String, required: true},
	},
	template: `
		<div class="mb-3">
			<div class="text-subtitle-2 mb-1">{{ $t('misc.calibration.historyHeading') }}</div>
			<div v-if="loading" class="text-caption grey--text">
				<aquapi-loading-indicator :size="16" color="primary"></aquapi-loading-indicator>
			</div>
			<div v-else-if="!groups.length" class="text-caption grey--text">
				{{ $t('misc.calibration.historyEmpty') }}
			</div>
			<v-list v-else density="compact" class="pa-0">
				<v-list-item v-for="(group, idx) in groups" :key="idx" class="px-0" min-height="28">
					<v-list-item-title class="text-caption">
						{{ formatTs(group.ts) }}: {{ groupLine(group) }}
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
		// one calibration event (2-point apply, or a hand-edit) writes one
		// calibration_log row per changed field, a few ms apart - group
		// them back into one line per event: "<date>: Faktor a->b, Offset c->d"
		groups: function() {
			return groupCalibrationLog(this.entries)
		},
	},
	methods: {
		formatTs: function(ts) {
			return new Date(ts).toLocaleString(i18n.global.locale.value)
		},
		fieldLabel: function(field) {
			return this.$t('pages.settings.fields.' + (FIELD_LABEL_KEYS[field] || field))
		},
		groupLine: function(group) {
			const parts = []
			if (group.factor) {
				parts.push(this.fieldLabel('factor') + ' ' + group.factor.old + '→' + group.factor.new)
			}
			if (group.offset) {
				parts.push(this.fieldLabel('offset') + ' ' + group.offset.old + '→' + group.offset.new)
			}
			return parts.join(', ')
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
