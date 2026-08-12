import {registerGlobalComponent} from '../app/registry.js'
import {useDashboardStore} from '../../store/modules/dashboard.js'
import {useConfigStore} from '../../store/modules/config.js'
import {useUsersStore} from '../../store/modules/users.js'

// Shared between /settings (inline in NodeSettingsCard) and /config
// (inside ConfigNodeDialog) - the only editor for an Alert node's
// AlertCond watches. Not schema-driven like NodeSettingsFields/
// ConfigNodeDialog's generic fields: there is no NODE_TYPE_SCHEMA entry
// for Alert (conditions are a set of objects, not a plain field), and
// with only 2 concrete AlertCond classes, hardcoding them here is
// simpler than inventing a schema endpoint for two fixed options.
const ALERT_COND_CLASSES = ['AlertAbove', 'AlertBelow']

const AlertCondEditor = {
	props: {
		node: {type: Object, required: true},
		// set by /config's ConfigNodeDialog, which has its own single
		// Save button for the whole edit dialog - two separate, visually
		// unrelated Save buttons in one dialog is confusing and error-
		// prone, so the dialog hides this one and calls save() itself
		// (via $refs) as part of its own combined save.
		hideSaveButton: {type: Boolean, default: false},
	},
	template: `
		<div>
			<v-alert v-if="error" type="error" density="compact" variant="tonal" class="mb-2">{{ error }}</v-alert>
			<v-alert v-if="!rows.length" type="info" density="compact" variant="tonal" class="mb-2">
				{{ $t('pages.settings.alertConds.hintEmpty') }}
			</v-alert>
			<div v-for="(row, idx) in rows" :key="row._key" class="d-flex align-center mb-2" style="gap:8px;">
				<v-select
					v-model="row.class"
					:items="condClassItems"
					:label="$t('pages.settings.alertConds.condition')"
					:disabled="!isAdmin"
					density="compact" variant="outlined" hide-details
					style="max-width:115px;"
				></v-select>
				<v-select
					v-model="row.node_id"
					:items="nodeItems"
					:label="$t('pages.settings.alertConds.watchedNode')"
					:disabled="!isAdmin"
					density="compact" variant="outlined" hide-details
					style="flex:1;"
				></v-select>
				<v-text-field
					v-model.number="row.limit"
					type="number"
					:label="$t('pages.settings.alertConds.limit')"
					:disabled="!isAdmin"
					density="compact" variant="outlined" hide-details
					style="max-width:100px;"
				></v-text-field>
				<v-text-field
					v-model.number="row.duration"
					type="number" min="0"
					:label="$t('pages.settings.alertConds.duration')"
					:disabled="!isAdmin"
					density="compact" variant="outlined" hide-details
					style="max-width:100px;"
				></v-text-field>
				<v-btn
					icon variant="text" color="grey-darken-1" size="small"
					:disabled="!isAdmin"
					@click="removeRow(idx)"
					:title="$t('pages.settings.alertConds.remove')"
				>
					<v-icon size="small">mdi-delete</v-icon>
				</v-btn>
			</div>
			<div class="d-flex align-center mt-1" style="gap:8px;">
				<v-btn variant="outlined" size="small" :disabled="!isAdmin" @click="addRow">
					<v-icon start size="small">mdi-plus</v-icon>{{ $t('pages.settings.alertConds.add') }}
				</v-btn>
				<v-spacer></v-spacer>
				<v-btn
					v-if="!hideSaveButton"
					color="primary" size="small"
					:disabled="!isAdmin || !dirty || !rowsValid"
					:loading="saving"
					@click="save"
				>
					{{ $t('pages.settings.alertConds.save') }}
				</v-btn>
			</div>
		</div>
	`,
	data: function() {
		return {rows: [], savedSnapshot: '[]', saving: false, error: null}
	},
	computed: {
		configStore() {
			return useConfigStore()
		},
		dashboardStore() {
			return useDashboardStore()
		},
		usersStore() {
			return useUsersStore()
		},
		isAdmin() {
			// PUT /api/nodes/<id>/conditions is admin-only, same gate as
			// NodeReceivesEditor uses for its own PUT /api/nodes/<id> call
			return this.usersStore.isAdmin
		},
		condClassItems: function() {
			return ALERT_COND_CLASSES.map(cls => ({title: this.$t('misc.alertConds.' + cls), value: cls}))
		},
		nodeItems: function() {
			return Object.values(this.dashboardStore.nodes)
				.filter(n => n.id !== this.node.id)
				.map(n => ({title: n.name + ' (' + n.type + ')', value: n.id}))
		},
		normalizedRows: function() {
			return this.rows.map(r => ({
				class: r.class,
				node_id: r.node_id,
				limit: Number(r.limit),
				duration: Number(r.duration) || 0,
			}))
		},
		rowsValid: function() {
			return this.rows.every(r => r.node_id && r.class && r.limit !== '' && !isNaN(Number(r.limit)))
		},
		dirty: function() {
			return JSON.stringify(this.normalizedRows) !== this.savedSnapshot
		},
	},
	watch: {
		'node.id': function() {
			this.resetRows()
		},
	},
	methods: {
		resetRows: function() {
			this.error = null
			this.rows = (this.node.conditions || []).map((c, i) => ({
				_key: i + '-' + c.node_id,
				class: c.class,
				node_id: c.node_id,
				limit: c.limit,
				duration: c.duration || 0,
			}))
			this.savedSnapshot = JSON.stringify(this.normalizedRows)
		},
		addRow: function() {
			this.rows.push({
				_key: 'new-' + Date.now() + '-' + Math.random(),
				class: 'AlertAbove', node_id: '', limit: 50, duration: 0,
			})
		},
		removeRow: async function(idx) {
			if (this.rows.length === 1) {
				const ok = await this.$confirm(this.$t('pages.settings.alertConds.confirmClearAll'), {
					confirmLabel: this.$t('pages.config.delete'),
					confirmColor: 'error',
				})
				if (!ok) {
					return
				}
			}
			this.rows.splice(idx, 1)
		},
		// Returns {ok, error} so an embedding parent (ConfigNodeDialog) can
		// await it as part of its own combined save. A no-op (ok:true) if
		// nothing changed, so a parent's "save everything" flow doesn't
		// fire a pointless PUT when the user never touched conditions.
		save: async function() {
			if (!this.dirty) {
				return {ok: true}
			}
			this.error = null
			this.saving = true
			try {
				const result = await this.configStore.updateNodeConditions({
					nodeId: this.node.id,
					conditions: this.normalizedRows,
				})
				if (result.ok) {
					this.savedSnapshot = JSON.stringify(this.normalizedRows)
					if (!this.hideSaveButton) {
						this.$toast.success(this.$t('misc.toast.saveSuccess'))
					}
				} else {
					this.error = result.error
					if (!this.hideSaveButton) {
						this.$toast.error(result.error || this.$t('misc.toast.saveError'))
					}
				}
				return result
			} finally {
				this.saving = false
			}
		},
	},
	created: function() {
		this.resetRows()
	},
}
registerGlobalComponent('AlertCondEditor', AlertCondEditor)

// vim: set noet ts=4 sw=4:
