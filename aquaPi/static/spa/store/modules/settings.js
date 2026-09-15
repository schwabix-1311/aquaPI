import {EventBus, AQUAPI_EVENTS} from '../../components/app/EventBus.js';
import i18n from '../../i18n/index.js';
import {apiRequest} from '../apiRequest.js';

export const useSettingsStore = Pinia.defineStore('settings', {
	state: () => ({
		byNode: {},          // nodeId -> array of settings entries (from get_settings())
		errors: {},          // nodeId -> error string or null
		calibrationLog: {},  // nodeId -> array of {ts, field, old_value, new_value}
	}),

	getters: {
		settingsForNode: (state) => (nodeId) => {
			return state.byNode[nodeId] || []
		},
		errorForNode: (state) => (nodeId) => {
			return state.errors[nodeId] || null
		},
		calibrationLogForNode: (state) => (nodeId) => {
			return state.calibrationLog[nodeId] || []
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
			// a single {key: value} update by default - pass `fields` (a
			// {key: value, ...} dict) instead to apply several at once in
			// one PUT, e.g. CalibrationHelper's offset+factor pair, so
			// both land in the same PUT/calibration-log-history moment
			// rather than two sequential requests
			const {nodeId, key, value, fields} = payload

			const res = await apiRequest('put', '/api/nodes/' + nodeId + '/settings',
				fields || {[key]: value})

			if (res.ok) {
				this.setSettings({nodeId, settings: res.data})
				this.setError({nodeId, error: null})
				return true
			}

			this.setError({nodeId, error: res.error})
			return false
		},

		async fetchCalibrationLog(nodeId) {
			const res = await apiRequest('get', '/api/nodes/' + nodeId + '/calibration-log')

			if (res.ok) {
				this.setCalibrationLog({nodeId, log: res.data})
				return true
			}

			console.error('ERROR loading calibration log for node ' + nodeId + ': ' + res.error)
			return false
		},

		setCalibrationLog(payload) {
			const {nodeId, log} = payload
			this.calibrationLog = Object.assign({}, this.calibrationLog, {[nodeId]: log})
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
