const state = () => ({
	nodeTypes: {},
	nodeTypesLoaded: false,
	templates: [],
	snapshots: [],
})

const getters = {
	nodeTypes: (state) => {
		return state.nodeTypes
	},
	nodeTypesLoaded: (state) => {
		return state.nodeTypesLoaded
	},
	templates: (state) => {
		return state.templates
	},
	snapshots: (state) => {
		return state.snapshots
	},
}

const actions = {
	async fetchNodeTypes({state, commit}) {
		if (state.nodeTypesLoaded) {
			return state.nodeTypes
		}

		const response = await fetch('/api/node-types/', {
			method: 'get',
			mode: 'same-origin',
			cache: 'no-cache',
			headers: {
				'X-Requested-With': 'XMLHttpRequest',
				'Accept': 'application/json'
			},
		})

		if (response.status == 200) {
			const nodeTypes = await response.json()
			commit('setNodeTypes', nodeTypes)
		}

		return state.nodeTypes
	},

	async createNode({dispatch}, payload) {
		try {
			const response = await fetch('/api/nodes/', {
				method: 'post',
				mode: 'same-origin',
				cache: 'no-cache',
				headers: {
					'X-Requested-With': 'XMLHttpRequest',
					'Accept': 'application/json',
					'Content-Type': 'application/json',
				},
				body: JSON.stringify(payload),
			})

			const body = await response.json().catch(() => null)

			if (response.status == 201) {
				await dispatch('dashboard/fetchNodes', null, {root: true})
				return {ok: true, node: body}
			}

			return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
		} catch (e) {
			return {ok: false, error: e.message}
		}
	},

	async updateNode({dispatch}, payload) {
		const {nodeId, changes} = payload

		try {
			const response = await fetch('/api/nodes/' + nodeId, {
				method: 'put',
				mode: 'same-origin',
				cache: 'no-cache',
				headers: {
					'X-Requested-With': 'XMLHttpRequest',
					'Accept': 'application/json',
					'Content-Type': 'application/json',
				},
				body: JSON.stringify(changes),
			})

			const body = await response.json().catch(() => null)

			if (response.status == 200) {
				await dispatch('dashboard/fetchNodes', null, {root: true})
				return {ok: true, node: body}
			}

			return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
		} catch (e) {
			return {ok: false, error: e.message}
		}
	},

	async deleteNode({dispatch}, payload) {
		const {nodeId} = payload

		try {
			const response = await fetch('/api/nodes/' + nodeId, {
				method: 'delete',
				mode: 'same-origin',
				cache: 'no-cache',
				headers: {
					'X-Requested-With': 'XMLHttpRequest',
					'Accept': 'application/json'
				},
			})

			if (response.status == 204) {
				await dispatch('dashboard/fetchNodes', null, {root: true})
				return {ok: true}
			}

			const body = await response.json().catch(() => null)
			return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
		} catch (e) {
			return {ok: false, error: e.message}
		}
	},

	async fetchTemplates({commit}) {
		const response = await fetch('/api/templates/', {
			method: 'get',
			mode: 'same-origin',
			cache: 'no-cache',
			headers: {
				'X-Requested-With': 'XMLHttpRequest',
				'Accept': 'application/json'
			},
		})
		if (response.status == 200) {
			commit('setTemplates', await response.json())
		}
	},

	async createTemplate({dispatch}, payload) {
		try {
			const response = await fetch('/api/templates/', {
				method: 'post',
				mode: 'same-origin',
				cache: 'no-cache',
				headers: {
					'X-Requested-With': 'XMLHttpRequest',
					'Accept': 'application/json',
					'Content-Type': 'application/json',
				},
				body: JSON.stringify(payload),
			})
			const body = await response.json().catch(() => null)
			if (response.status == 201) {
				await dispatch('fetchTemplates')
				return {ok: true, template: body}
			}
			return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
		} catch (e) {
			return {ok: false, error: e.message}
		}
	},

	async deleteTemplate({dispatch}, payload) {
		const {name} = payload
		try {
			const response = await fetch('/api/templates/' + encodeURIComponent(name), {
				method: 'delete',
				mode: 'same-origin',
				cache: 'no-cache',
				headers: {
					'X-Requested-With': 'XMLHttpRequest',
					'Accept': 'application/json'
				},
			})
			if (response.status == 204) {
				await dispatch('fetchTemplates')
				return {ok: true}
			}
			const body = await response.json().catch(() => null)
			return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
		} catch (e) {
			return {ok: false, error: e.message}
		}
	},

	async insertTemplate({dispatch}, payload) {
		const {name} = payload
		try {
			const response = await fetch('/api/templates/' + encodeURIComponent(name) + '/insert', {
				method: 'post',
				mode: 'same-origin',
				cache: 'no-cache',
				headers: {
					'X-Requested-With': 'XMLHttpRequest',
					'Accept': 'application/json'
				},
			})
			const body = await response.json().catch(() => null)
			if (response.status == 201) {
				await dispatch('dashboard/fetchNodes', null, {root: true})
				return {ok: true, nodes: body}
			}
			return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
		} catch (e) {
			return {ok: false, error: e.message}
		}
	},

	async fetchSnapshots({commit}) {
		const response = await fetch('/api/config/snapshots', {
			method: 'get',
			mode: 'same-origin',
			cache: 'no-cache',
			headers: {
				'X-Requested-With': 'XMLHttpRequest',
				'Accept': 'application/json'
			},
		})
		if (response.status == 200) {
			commit('setSnapshots', await response.json())
		}
	},

	async createSnapshot({dispatch}, payload) {
		try {
			const response = await fetch('/api/config/snapshots', {
				method: 'post',
				mode: 'same-origin',
				cache: 'no-cache',
				headers: {
					'X-Requested-With': 'XMLHttpRequest',
					'Accept': 'application/json',
					'Content-Type': 'application/json',
				},
				body: JSON.stringify(payload),
			})
			const body = await response.json().catch(() => null)
			if (response.status == 201) {
				await dispatch('fetchSnapshots')
				return {ok: true, snapshot: body}
			}
			return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
		} catch (e) {
			return {ok: false, error: e.message}
		}
	},

	async deleteSnapshot({dispatch}, payload) {
		const {name} = payload
		try {
			const response = await fetch('/api/config/snapshots/' + encodeURIComponent(name), {
				method: 'delete',
				mode: 'same-origin',
				cache: 'no-cache',
				headers: {
					'X-Requested-With': 'XMLHttpRequest',
					'Accept': 'application/json'
				},
			})
			if (response.status == 204) {
				await dispatch('fetchSnapshots')
				return {ok: true}
			}
			const body = await response.json().catch(() => null)
			return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
		} catch (e) {
			return {ok: false, error: e.message}
		}
	},

	async restoreSnapshot({dispatch}, payload) {
		const {name} = payload
		try {
			const response = await fetch('/api/config/snapshots/' + encodeURIComponent(name) + '/restore', {
				method: 'post',
				mode: 'same-origin',
				cache: 'no-cache',
				headers: {
					'X-Requested-With': 'XMLHttpRequest',
					'Accept': 'application/json'
				},
			})
			const body = await response.json().catch(() => null)
			if (response.status == 200) {
				await dispatch('dashboard/fetchNodes', null, {root: true})
				return {ok: true, nodes: body}
			}
			return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
		} catch (e) {
			return {ok: false, error: e.message}
		}
	},
}

const mutations = {
	setNodeTypes(state, payload) {
		state.nodeTypes = payload
		state.nodeTypesLoaded = true
	},
	setTemplates(state, payload) {
		state.templates = payload
	},
	setSnapshots(state, payload) {
		state.snapshots = payload
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
