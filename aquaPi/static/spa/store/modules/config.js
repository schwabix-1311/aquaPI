import {useDashboardStore} from './dashboard.js';
import {EventBus, AQUAPI_EVENTS} from '../../components/app/EventBus.js';
import i18n from '../../i18n/index.js';

export const useConfigStore = Pinia.defineStore('config', {
	state: () => ({
		nodeTypes: {},
		nodeTypesLoaded: false,
		templates: [],
		snapshots: [],
		draft: null,
		draftTempCounter: 0,
	}),

	getters: {
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
	},

	actions: {
		async fetchNodeTypes() {
			if (this.nodeTypesLoaded) {
				return this.nodeTypes
			}

			try {
				const response = await fetch('/api/node-types/', {
					method: 'get',
					mode: 'same-origin',
					cache: 'no-cache',
					headers: {
						'X-Requested-With': 'XMLHttpRequest',
						'Accept': 'application/json'
					},
				})

				if (response.status !== 200) {
					throw new Error('GET /api/node-types/ returned ' + response.status)
				}

				this.setNodeTypes(await response.json())
			} catch (e) {
				console.error('ERROR loading node types: ' + e.message)
				EventBus.$emit(AQUAPI_EVENTS.TOAST_REQUESTED, {
					message: i18n.global.t('misc.toast.loadError', {what: i18n.global.t('misc.toast.what.nodeTypes')}),
					color: 'error',
					timeout: 6000,
				})
			}

			return this.nodeTypes
		},

		async createNode(payload) {
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
					await useDashboardStore().fetchNodes()
					return {ok: true, node: body}
				}

				return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
			} catch (e) {
				return {ok: false, error: e.message}
			}
		},

		async updateNode(payload) {
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
					await useDashboardStore().fetchNodes()
					return {ok: true, node: body}
				}

				return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
			} catch (e) {
				return {ok: false, error: e.message}
			}
		},

		async updateNodeConditions(payload) {
			const {nodeId, conditions} = payload

			try {
				const response = await fetch('/api/nodes/' + nodeId + '/conditions', {
					method: 'put',
					mode: 'same-origin',
					cache: 'no-cache',
					headers: {
						'X-Requested-With': 'XMLHttpRequest',
						'Accept': 'application/json',
						'Content-Type': 'application/json',
					},
					body: JSON.stringify({conditions}),
				})

				const body = await response.json().catch(() => null)

				if (response.status == 200) {
					useDashboardStore().setNode(body)
					// This bypasses the /config draft entirely (Alert has no
					// NODE_TYPE_SCHEMA entry, so its conditions/receives are
					// never part of the create/update diff) - if a draft
					// happens to be active, patch just this one node's stale
					// copy in place so the canvas/edit dialog reflect the
					// change immediately, without discarding any of the
					// draft's OTHER unrelated pending edits the way a full
					// initDraft() refetch would.
					if (this.draft && this.draft[nodeId]) {
						this.setDraftNode(Object.assign({}, this.draft[nodeId], {
							conditions: body.conditions,
							receives: body.receives,
						}))
					}
					return {ok: true, node: body}
				}

				return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
			} catch (e) {
				return {ok: false, error: e.message}
			}
		},

		async deleteNode(payload) {
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
					await useDashboardStore().fetchNodes()
					return {ok: true}
				}

				const body = await response.json().catch(() => null)
				return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
			} catch (e) {
				return {ok: false, error: e.message}
			}
		},

		async fetchTemplates() {
			try {
				const response = await fetch('/api/templates/', {
					method: 'get',
					mode: 'same-origin',
					cache: 'no-cache',
					headers: {
						'X-Requested-With': 'XMLHttpRequest',
						'Accept': 'application/json'
					},
				})
				if (response.status !== 200) {
					throw new Error('GET /api/templates/ returned ' + response.status)
				}
				this.setTemplates(await response.json())
			} catch (e) {
				console.error('ERROR loading templates: ' + e.message)
				EventBus.$emit(AQUAPI_EVENTS.TOAST_REQUESTED, {
					message: i18n.global.t('misc.toast.loadError', {what: i18n.global.t('misc.toast.what.templates')}),
					color: 'error',
					timeout: 6000,
				})
			}
		},

		async createTemplate(payload) {
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
					await this.fetchTemplates()
					return {ok: true, template: body}
				}
				return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
			} catch (e) {
				return {ok: false, error: e.message}
			}
		},

		async deleteTemplate(payload) {
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
					await this.fetchTemplates()
					return {ok: true}
				}
				const body = await response.json().catch(() => null)
				return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
			} catch (e) {
				return {ok: false, error: e.message}
			}
		},

		async insertTemplate(payload) {
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
					await useDashboardStore().fetchNodes()
					return {ok: true, nodes: body}
				}
				return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
			} catch (e) {
				return {ok: false, error: e.message}
			}
		},

		async fetchSnapshots() {
			try {
				const response = await fetch('/api/config/snapshots', {
					method: 'get',
					mode: 'same-origin',
					cache: 'no-cache',
					headers: {
						'X-Requested-With': 'XMLHttpRequest',
						'Accept': 'application/json'
					},
				})
				if (response.status !== 200) {
					throw new Error('GET /api/config/snapshots returned ' + response.status)
				}
				this.setSnapshots(await response.json())
			} catch (e) {
				console.error('ERROR loading snapshots: ' + e.message)
				EventBus.$emit(AQUAPI_EVENTS.TOAST_REQUESTED, {
					message: i18n.global.t('misc.toast.loadError', {what: i18n.global.t('misc.toast.what.snapshots')}),
					color: 'error',
					timeout: 6000,
				})
			}
		},

		async createSnapshot(payload) {
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
					await this.fetchSnapshots()
					return {ok: true, snapshot: body}
				}
				return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
			} catch (e) {
				return {ok: false, error: e.message}
			}
		},

		async deleteSnapshot(payload) {
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
					await this.fetchSnapshots()
					return {ok: true}
				}
				const body = await response.json().catch(() => null)
				return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
			} catch (e) {
				return {ok: false, error: e.message}
			}
		},

		async restoreSnapshot(payload) {
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
					await useDashboardStore().fetchNodes()
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

		initDraft() {
			const nodes = useDashboardStore().nodes
			const draft = {}
			Object.values(nodes).forEach(node => {
				draft[node.id] = Object.assign({}, node, {_new: false, _dirty: false, _deleted: false})
			})
			this.setDraft(draft)
		},

		discardDraft() {
			this.setDraft(null)
		},

		draftCreateNode(payload) {
			const tempId = 'draft-' + (this.draftTempCounter + 1)
			this.bumpDraftTempCounter()
			const node = Object.assign({}, payload, {
				id: tempId,
				identifier: tempId,
				_tempId: tempId,
				_new: true,
				_dirty: true,
				_deleted: false,
			})
			this.setDraftNode(node)
			return node
		},

		draftUpdateNode(payload) {
			const {nodeId, changes} = payload
			const existing = this.draft[nodeId]
			if (!existing) {
				return
			}
			const node = Object.assign({}, existing, changes, {
				_dirty: existing._new ? existing._dirty : true,
			})
			this.setDraftNode(node)
		},

		draftDeleteNode(payload) {
			const {nodeId} = payload
			const existing = this.draft[nodeId]
			if (!existing) {
				return
			}
			if (existing._new) {
				this.removeDraftNode(nodeId)
			} else {
				this.setDraftNode(Object.assign({}, existing, {_deleted: true}))
			}
		},

		async saveDraft() {
			if (!this.draft) {
				return {ok: true}
			}

			const fieldsOf = (node) => {
				const schema = this.nodeTypes[node.type]
				const fields = {}
				;(schema && schema.fields || []).forEach(field => {
					if (node[field.key] !== undefined) {
						fields[field.key] = node[field.key]
					}
				})
				return fields
			}

			const dashboardNodes = useDashboardStore().nodes

			const creates = []
			const updates = []
			const deletes = []

			Object.values(this.draft).forEach(node => {
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
					const upd = {
						id: node.id,
						group: node.group || '',
						pos_x: node.pos_x || 0,
						pos_y: node.pos_y || 0,
					}

					// Node types without a NODE_TYPE_SCHEMA entry (Alert,
					// History) reject *any* update payload that even mentions
					// 'receives'/'fields', regardless of value - their receives
					// are edited through a dedicated endpoint instead (see
					// NodeReceivesEditor). Since this node may be dirty for an
					// unrelated reason (e.g. only pos_x/pos_y changed, as the
					// /config auto-layout does for every node including these),
					// only include receives/fields when they actually changed
					// from the last-known server state, not unconditionally.
					const original = dashboardNodes[node.id]
					const receives = node.receives || []
					if (!original || JSON.stringify(receives) !== JSON.stringify(original.receives || [])) {
						upd.receives = receives
					}
					const fields = fieldsOf(node)
					if (!original || JSON.stringify(fields) !== JSON.stringify(fieldsOf(original))) {
						upd.fields = fields
					}

					updates.push(upd)
				}
			})

			if (!creates.length && !updates.length && !deletes.length) {
				this.setDraft(null)
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
					await useDashboardStore().fetchNodes()
					this.setDraft(null)
					return {ok: true, idMap: body.id_map}
				}

				return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
			} catch (e) {
				return {ok: false, error: e.message}
			}
		},

		setNodeTypes(payload) {
			this.nodeTypes = payload
			this.nodeTypesLoaded = true
		},
		setTemplates(payload) {
			this.templates = payload
		},
		setSnapshots(payload) {
			this.snapshots = payload
		},
		setDraft(payload) {
			this.draft = payload
		},
		setDraftNode(payload) {
			this.draft = Object.assign({}, this.draft)
			this.draft[payload.id] = payload
		},
		removeDraftNode(nodeId) {
			this.draft = Object.assign({}, this.draft)
			delete this.draft[nodeId]
		},
		bumpDraftTempCounter() {
			this.draftTempCounter += 1
		},
	}
})

// vim: set noet ts=4 sw=4:
