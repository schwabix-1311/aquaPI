import {registerGlobalComponent} from '../app/registry.js'
import {useSettingsStore} from '../../store/modules/settings.js'
import {useNotificationsStore} from '../../store/modules/notifications.js'
import {useUsersStore} from '../../store/modules/users.js'

// A 2nd, operator/admin-configured notification for an Alert node: once
// the alert has stayed continuously active for 'escalation_after_minutes',
// also notify 'escalation_channel' - a specific IoRegistry port name, same
// kind of value as the node's own primary 'port' ('sendTo') Setting, not
// tied to any particular channel type (Email/Telegram/...). Not
// schema-driven like NodeSettingsFields (this isn't part of the node's
// own get_settings() - it's a separate, per-(account, alert node) REST
// resource, GET/PUT /api/notifications/prefs...), so it follows
// AlertCondEditor's shape instead: own local dirty-tracking, own Save
// button, own store.
const EscalationEditor = {
	props: {
		node: {type: Object, required: true},
	},
	template: `
		<div class="mt-2">
			<div class="text-overline">{{ $t('pages.settings.escalation.title') }}</div>
			<v-alert v-if="error" type="error" density="compact" variant="tonal" class="mb-2">{{ error }}</v-alert>
			<div class="d-flex align-center mb-2" style="gap:8px;">
				<v-select
					v-model="escalationChannel"
					:items="channelItems"
					:label="$t('pages.settings.escalation.channel')"
					:disabled="!canEdit"
					density="compact" variant="outlined" hide-details
					style="flex:1; max-width:220px;"
				></v-select>
				<v-text-field
					v-model.number="escalationAfterMinutes"
					type="number" min="0"
					:disabled="!canEdit || escalationChannel === 'none'"
					:label="$t('pages.settings.escalation.afterMinutes')"
					density="compact" variant="outlined" hide-details
					style="max-width:140px;"
				></v-text-field>
				<v-btn
					color="primary" size="small"
					:disabled="!canEdit || !dirty"
					:loading="saving"
					@click="save"
				>
					{{ $t('pages.settings.escalation.save') }}
				</v-btn>
			</div>
		</div>
	`,
	data: function() {
		return {
			escalationChannel: 'none',
			escalationAfterMinutes: 0,
			savedSnapshot: JSON.stringify({escalation_channel: 'none', escalation_after_minutes: 0}),
			saving: false,
			error: null,
		}
	},
	computed: {
		settingsStore() {
			return useSettingsStore()
		},
		notificationsStore() {
			return useNotificationsStore()
		},
		usersStore() {
			return useUsersStore()
		},
		// same permission level as the node's own 'sendTo' (port) field
		// and AlertCondEditor's conditions - see alertCondEditor.js's
		// canEdit for why this differs from NodeReceivesEditor's
		// admin-only raw receives edit
		canEdit() {
			return this.usersStore.isOperatorOrAdmin
		},
		// reuse the same free-port list the node's own 'sendTo' select
		// already offers (populated by NodeSettingsFields' fetchNodeSettings,
		// which runs for this node just above in NodeSettingsCard) - no
		// dedicated backend endpoint needed just to list ports again
		portOptions() {
			const portSetting = this.settingsStore.settingsForNode(this.node.id)
				.find((entry) => entry.key === 'port')
			return (portSetting && portSetting.options) || []
		},
		channelItems() {
			const items = [{title: this.$t('pages.settings.escalation.none'), value: 'none'}]
			this.portOptions.forEach((port) => items.push({title: port, value: port}))
			if (this.escalationChannel !== 'none' && !this.portOptions.includes(this.escalationChannel)) {
				items.push({title: this.escalationChannel, value: this.escalationChannel})
			}
			return items
		},
		dirty() {
			const saved = JSON.parse(this.savedSnapshot)
			return this.escalationChannel !== saved.escalation_channel
				|| Number(this.escalationAfterMinutes) !== saved.escalation_after_minutes
		},
	},
	watch: {
		'node.id': function() {
			this.resetFromStore()
		},
	},
	methods: {
		resetFromStore: function() {
			this.error = null
			const pref = this.notificationsStore.prefForAlertNode(this.node.id)
			this.escalationChannel = pref.escalation_channel
			this.escalationAfterMinutes = pref.escalation_after_minutes
			this.savedSnapshot = JSON.stringify(pref)
		},
		save: async function() {
			this.error = null
			this.saving = true
			try {
				const result = await this.notificationsStore.setPref({
					alertNodeId: this.node.id,
					escalationChannel: this.escalationChannel,
					escalationAfterMinutes: Number(this.escalationAfterMinutes) || 0,
				})
				if (result.ok) {
					this.resetFromStore()
					this.$toast.success(this.$t('misc.toast.saveSuccess'))
				} else {
					this.error = result.error
					this.$toast.error(result.error || this.$t('misc.toast.saveError'))
				}
			} finally {
				this.saving = false
			}
		},
	},
	created: async function() {
		if (!this.notificationsStore.loaded) {
			await this.notificationsStore.fetchPrefs()
		}
		this.resetFromStore()
	},
}
registerGlobalComponent('EscalationEditor', EscalationEditor)

// vim: set noet ts=4 sw=4:
