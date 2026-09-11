import {EventBus, AQUAPI_EVENTS} from '../../components/app/EventBus.js';
import i18n from '../../i18n/index.js';
import {apiRequest} from '../apiRequest.js';

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
			const res = await apiRequest('get', '/api/nodes/' + nodeId + '/settings')

			if (res.ok) {
				this.setSettings({nodeId, settings: res.data})
				this.setError({nodeId, error: null})
				return true
			}

			this.setError({nodeId, error: res.error})
			console.error('ERROR loading settings for node ' + nodeId + ': ' + res.error)
			EventBus.$emit(AQUAPI_EVENTS.TOAST_REQUESTED, {
				message: i18n.global.t('misc.toast.loadError', {what: i18n.global.t('misc.toast.what.nodeSettings')}),
				color: 'error',
				timeout: 6000,
			})
			return false
		},

		async updateNodeSetting(payload) {
			const {nodeId, key, value} = payload

			const res = await apiRequest('put', '/api/nodes/' + nodeId + '/settings', {[key]: value})

			if (res.ok) {
				this.setSettings({nodeId, settings: res.data})
				this.setError({nodeId, error: null})
				return true
			}

			this.setError({nodeId, error: res.error})
			return false
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
