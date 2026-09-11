import {apiRequest} from '../apiRequest.js';

export const useNotificationsStore = Pinia.defineStore('notifications', {
	state: () => ({
		prefsByAlertNode: {},   // alert_node_id -> {escalation_channel, escalation_after_minutes}
		loaded: false,
	}),

	getters: {
		prefForAlertNode: (state) => (alertNodeId) => {
			return state.prefsByAlertNode[alertNodeId]
				|| {escalation_channel: 'none', escalation_after_minutes: 0}
		},
	},

	actions: {
		async fetchPrefs() {
			const res = await apiRequest('get', '/api/notifications/prefs')
			if (res.ok) {
				this.setPrefs(res.data)
				return true
			}
			return false
		},

		async setPref(payload) {
			const {alertNodeId, escalationChannel, escalationAfterMinutes} = payload

			const res = await apiRequest('put', '/api/notifications/prefs/' + alertNodeId, {
				escalation_channel: escalationChannel,
				escalation_after_minutes: escalationAfterMinutes,
			})

			if (res.ok) {
				this.setOnePref(res.data)
				return {ok: true}
			}
			return {ok: false, error: res.error}
		},

		setPrefs(prefs) {
			const byNode = {}
			prefs.forEach((pref) => {
				byNode[pref.alert_node_id] = pref
			})
			this.prefsByAlertNode = byNode
			this.loaded = true
		},
		setOnePref(pref) {
			this.prefsByAlertNode = Object.assign({}, this.prefsByAlertNode, {[pref.alert_node_id]: pref})
		},
	}
})

// vim: set noet ts=4 sw=4:
