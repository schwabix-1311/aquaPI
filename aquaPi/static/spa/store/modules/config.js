const state = () => ({
	nodeTypes: {},
	nodeTypesLoaded: false,
	templates: [],
	snapshots: [],
	draft: null,
	draftTempCounter: 0,
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
	draftActive: (state) => {
		return state.draft !== null
	},
	draftNodes: (state) => {
		if (!state.draft) {
			return []
		}
		return Object.values(state.draft).filter(node => !node._deleted)
	},
	draftDirty: (state) => {
		if (!state.draft) {
			return false
		}
		return Object.values(state.draft).some(node => node._new || node._dirty || node._deleted)
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

	// --- /config editor draft mode (Step 16): all node CRUD below is
	// applied client-side to state.draft only, and only actually sent
	// to the backend as a single atomic diff by saveDraft() ---

	initDraft({rootGetters, commit}) {
		const nodes = rootGetters['dashboard/nodes']
		const draft = {}
		Object.values(nodes).forEach(node => {
			draft[node.id] = Object.assign({}, node, {_new: false, _dirty: false, _deleted: false})
		})
		commit('setDraft', draft)
	},

	discardDraft({commit}) {
		commit('setDraft', null)
	},

	draftCreateNode({state, commit}, payload) {
		const tempId = 'draft-' + (state.draftTempCounter + 1)
		commit('bumpDraftTempCounter')
		const node = Object.assign({}, payload, {
			id: tempId,
			identifier: tempId,
			_tempId: tempId,
			_new: true,
			_dirty: true,
			_deleted: false,
		})
		commit('setDraftNode', node)
		return node
	},

	draftUpdateNode({state, commit}, payload) {
		const {nodeId, changes} = payload
		const existing = state.draft[nodeId]
		if (!existing) {
			return
		}
		const node = Object.assign({}, existing, changes, {
			_dirty: existing._new ? existing._dirty : true,
		})
		commit('setDraftNode', node)
	},

	draftDeleteNode({state, commit}, payload) {
		const {nodeId} = payload
		const existing = state.draft[nodeId]
		if (!existing) {
			return
		}
		if (existing._new) {
			commit('removeDraftNode', nodeId)
		} else {
			commit('setDraftNode', Object.assign({}, existing, {_deleted: true}))
		}
	},

	async saveDraft({state, dispatch, commit}) {
		if (!state.draft) {
			return {ok: true}
		}

		const fieldsOf = (node) => {
			const schema = state.nodeTypes[node.type]
			const fields = {}
			;(schema && schema.fields || []).forEach(field => {
				if (node[field.key] !== undefined) {
					fields[field.key] = node[field.key]
				}
			})
			return fields
		}

		const creates = []
		const updates = []
		const deletes = []

		Object.values(state.draft).forEach(node => {
			if (node._new && node._deleted) {
				return
			}
			if (node._new) {
				creates.push({
					temp_id: node._tempId,
					type: node.type,
					name: node.name,
					receives: node.receives || [],
					fields: fieldsOf(node),
					group: node.group || '',
					pos_x: node.pos_x || 0,
					pos_y: node.pos_y || 0,
				})
			} else if (node._deleted) {
				deletes.push(node.id)
			} else if (node._dirty) {
				updates.push({
					id: node.id,
					receives: node.receives || [],
					fields: fieldsOf(node),
					group: node.group || '',
					pos_x: node.pos_x || 0,
					pos_y: node.pos_y || 0,
				})
			}
		})

		if (!creates.length && !updates.length && !deletes.length) {
			commit('setDraft', null)
			return {ok: true}
		}

		try {
			const response = await fetch('/api/config/apply', {
				method: 'post',
				mode: 'same-origin',
				cache: 'no-cache',
				headers: {
					'X-Requested-With': 'XMLHttpRequest',
					'Accept': 'application/json',
					'Content-Type': 'application/json',
				},
				body: JSON.stringify({creates, updates, deletes}),
			})

			const body = await response.json().catch(() => null)

			if (response.status == 200) {
				await dispatch('dashboard/fetchNodes', null, {root: true})
				commit('setDraft', null)
				return {ok: true, idMap: body.id_map}
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
	setDraft(state, payload) {
		state.draft = payload
	},
	setDraftNode(state, payload) {
		state.draft = Object.assign({}, state.draft)
		state.draft[payload.id] = payload
	},
	removeDraftNode(state, nodeId) {
		state.draft = Object.assign({}, state.draft)
		delete state.draft[nodeId]
	},
	bumpDraftTempCounter(state) {
		state.draftTempCounter += 1
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
