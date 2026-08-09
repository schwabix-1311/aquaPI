import {EventBus, AQUAPI_EVENTS} from '../../components/app/EventBus.js';
import i18n from '../../i18n/index.js';

export const useSettingsStore = Pinia.defineStore('settings', {
	state: () => ({
		byNode: {},   // nodeId -> array of settings entries (from get_settings())
		errors: {},   // nodeId -> error string or null
	}),

	getters: {
		settingsForNode: (state) => (nodeId) => {
			return state.byNode[nodeId] || []
		},
		errorForNode: (state) => (nodeId) => {
			return state.errors[nodeId] || null
		},
	},

	actions: {
		async fetchNodeSettings(nodeId) {
			try {
				const response = await fetch('/api/nodes/' + nodeId + '/settings', {
					method: 'get',
					mode: 'same-origin',
					cache: 'no-cache',
					headers: {
						'X-Requested-With': 'XMLHttpRequest',
						'Accept': 'application/json'
					},
				})

				if (response.status == 200) {
					const settings = await response.json()
					this.setSettings({nodeId, settings})
					this.setError({nodeId, error: null})
					return true
				}

				this.setError({nodeId, error: 'HTTP ' + response.status})
				console.error('ERROR loading settings for node ' + nodeId + ': HTTP ' + response.status)
				EventBus.$emit(AQUAPI_EVENTS.TOAST_REQUESTED, {
					message: i18n.global.t('misc.toast.loadError', {what: i18n.global.t('misc.toast.what.nodeSettings')}),
					color: 'error',
					timeout: 6000,
				})
				return false
			} catch (e) {
				this.setError({nodeId, error: e.message})
				console.error('ERROR loading settings for node ' + nodeId + ': ' + e.message)
				EventBus.$emit(AQUAPI_EVENTS.TOAST_REQUESTED, {
					message: i18n.global.t('misc.toast.loadError', {what: i18n.global.t('misc.toast.what.nodeSettings')}),
					color: 'error',
					timeout: 6000,
				})
				return false
			}
		},

		async updateNodeSetting(payload) {
			const {nodeId, key, value} = payload

			try {
				const response = await fetch('/api/nodes/' + nodeId + '/settings', {
					method: 'put',
					mode: 'same-origin',
					cache: 'no-cache',
					headers: {
						'X-Requested-With': 'XMLHttpRequest',
						'Accept': 'application/json',
						'Content-Type': 'application/json',
					},
					body: JSON.stringify({[key]: value}),
				})

				if (response.status == 200) {
					const settings = await response.json()
					this.setSettings({nodeId, settings})
					this.setError({nodeId, error: null})
					return true
				}

				let error = 'HTTP ' + response.status
				try {
					const body = await response.json()
					if (body && body.error) {
						error = body.error
					}
				} catch (e) {}

				this.setError({nodeId, error})
				return false
			} catch (e) {
				this.setError({nodeId, error: e.message})
				return false
			}
		},

		setSettings(payload) {
			const {nodeId, settings} = payload
			this.byNode = Object.assign({}, this.byNode, {[nodeId]: settings})
		},
		setError(payload) {
			const {nodeId, error} = payload
			this.errors = Object.assign({}, this.errors, {[nodeId]: error})
		},
	}
})

// vim: set noet ts=4 sw=4:
