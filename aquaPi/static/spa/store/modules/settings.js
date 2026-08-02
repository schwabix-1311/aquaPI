const state = () => ({
	byNode: {},   // nodeId -> array of settings entries (from get_settings())
	errors: {},   // nodeId -> error string or null
})

const getters = {
	settingsForNode: (state) => (nodeId) => {
		return state.byNode[nodeId] || []
	},
	errorForNode: (state) => (nodeId) => {
		return state.errors[nodeId] || null
	},
}

const actions = {
	async fetchNodeSettings({commit}, nodeId) {
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
				commit('setSettings', {nodeId, settings})
				commit('setError', {nodeId, error: null})
				return true
			}

			commit('setError', {nodeId, error: 'HTTP ' + response.status})
			return false
		} catch (e) {
			commit('setError', {nodeId, error: e.message})
			return false
		}
	},

	async updateNodeSetting({commit}, payload) {
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
				commit('setSettings', {nodeId, settings})
				commit('setError', {nodeId, error: null})
				return true
			}

			let error = 'HTTP ' + response.status
			try {
				const body = await response.json()
				if (body && body.error) {
					error = body.error
				}
			} catch (e) {}

			commit('setError', {nodeId, error})
			return false
		} catch (e) {
			commit('setError', {nodeId, error: e.message})
			return false
		}
	},
}

const mutations = {
	setSettings(state, payload) {
		const {nodeId, settings} = payload
		state.byNode = Object.assign({}, state.byNode, {[nodeId]: settings})
	},
	setError(state, payload) {
		const {nodeId, error} = payload
		state.errors = Object.assign({}, state.errors, {[nodeId]: error})
	},
}

export default {
	namespaced: true,
	state,
	getters,
	actions,
	mutations
}

// vim: set noet ts=4 sw=4:
