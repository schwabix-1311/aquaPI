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
			try {
				const response = await fetch('/api/notifications/prefs', {
					method: 'get',
					mode: 'same-origin',
					cache: 'no-cache',
					headers: {
						'X-Requested-With': 'XMLHttpRequest',
						'Accept': 'application/json',
					},
				})

				if (response.status == 200) {
					const prefs = await response.json()
					this.setPrefs(prefs)
					return true
				}

				return false
			} catch (e) {
				return false
			}
		},

		async setPref(payload) {
			const {alertNodeId, escalationChannel, escalationAfterMinutes} = payload

			try {
				const response = await fetch('/api/notifications/prefs/' + alertNodeId, {
					method: 'put',
					mode: 'same-origin',
					cache: 'no-cache',
					headers: {
						'X-Requested-With': 'XMLHttpRequest',
						'Accept': 'application/json',
						'Content-Type': 'application/json',
					},
					body: JSON.stringify({
						escalation_channel: escalationChannel,
						escalation_after_minutes: escalationAfterMinutes,
					}),
				})

				const body = await response.json().catch(() => null)

				if (response.status == 200) {
					this.setOnePref(body)
					return {ok: true}
				}

				return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
			} catch (e) {
				return {ok: false, error: e.message}
			}
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
