import {useDashboardStore} from './dashboard.js';
import {apiRequest} from '../apiRequest.js';
import {wiringDiff} from '../../components/wiring/wiringDiff.js';
import {EventBus, AQUAPI_EVENTS} from '../../components/app/EventBus.js';
import i18n from '../../i18n/index.js';

// plain deep copy - node objects are JSON straight from the REST API
const clone = (obj) => JSON.parse(JSON.stringify(obj))

// shared "couldn't load X" toast for the read-only fetchers below
// (mutating actions return {ok, error} and let the caller decide instead)
function emitLoadError(whatKey) {
	EventBus.$emit(AQUAPI_EVENTS.TOAST_REQUESTED, {
		message: i18n.global.t('misc.toast.loadError',
			{what: i18n.global.t('misc.toast.what.' + whatKey)}),
		color: 'error',
		timeout: 6000,
	})
}

export const useWiringStore = Pinia.defineStore('wiring', {
	state: () => ({
		nodeTypes: {},
		nodeTypesLoaded: false,
		templates: [],
		snapshots: [],
		// draft = the working {id: node} map being edited; draftBaseline =
		// an untouched snapshot of what the server had when the draft was
		// opened. The diff between the two IS the pending change set - no
		// per-node _new/_dirty/_deleted bookkeeping. Both null when no
		// draft is open.
		draft: null,
		draftBaseline: null,
		draftTempCounter: 0,
	}),

	getters: {
		draftActive: (state) => {
			return state.draft !== null
		},
		draftNodes: (state) => {
			return state.draft ? Object.values(state.draft) : []
		},
		draftDirty: (state) => {
			return wiringDiff(state.draftBaseline, state.draft, state.nodeTypes).hasChanges
		},
	},

	actions: {
		async fetchNodeTypes() {
			if (this.nodeTypesLoaded) {
				return this.nodeTypes
			}
			const res = await apiRequest('get', '/api/node-types/')
			if (res.ok) {
				this.setNodeTypes(res.data)
			} else {
				console.error('ERROR loading node types: ' + res.error)
				emitLoadError('nodeTypes')
			}
			return this.nodeTypes
		},

		async updateNode(payload) {
			const {nodeId, changes} = payload
			const res = await apiRequest('put', '/api/nodes/' + nodeId, changes)
			if (res.ok) {
				await useDashboardStore().fetchNodes()
				return {ok: true, node: res.data}
			}
			return {ok: false, error: res.error}
		},

		async updateNodeConditions(payload) {
			const {nodeId, conditions} = payload
			const res = await apiRequest('put', '/api/nodes/' + nodeId + '/conditions', {conditions})
			if (!res.ok) {
				return {ok: false, error: res.error}
			}
			const body = res.data
			useDashboardStore().setNode(body)
			// This bypasses the /wiring draft entirely (Alert has no
			// NODE_TYPE_SCHEMA entry, so its conditions/receives are
			// never part of the create/update diff) - if a draft happens
			// to be active, patch this one node's stale copy in BOTH the
			// working map and the baseline, so the canvas/edit dialog
			// reflect the (already persisted) change immediately without
			// it showing up as a pending diff or disturbing the draft's
			// other unrelated edits.
			const patch = {conditions: body.conditions, receives: body.receives}
			if (this.draft && this.draft[nodeId]) {
				this.setDraftNode(Object.assign({}, this.draft[nodeId], patch))
			}
			if (this.draftBaseline && this.draftBaseline[nodeId]) {
				this.draftBaseline = Object.assign({}, this.draftBaseline, {
					[nodeId]: Object.assign({}, this.draftBaseline[nodeId], patch),
				})
			}
			return {ok: true, node: body}
		},

		async fetchTemplates() {
			const lang = i18n.global.locale.value
			const res = await apiRequest('get',
				'/api/templates/?lang=' + encodeURIComponent(lang))
			if (res.ok) {
				this.setTemplates(res.data)
			} else {
				console.error('ERROR loading templates: ' + res.error)
				emitLoadError('templates')
			}
		},

		async createTemplate(payload) {
			const res = await apiRequest('post', '/api/templates/', payload)
			if (res.ok) {
				await this.fetchTemplates()
				return {ok: true, template: res.data}
			}
			return {ok: false, error: res.error}
		},

		async deleteTemplate(payload) {
			const {id} = payload
			const res = await apiRequest('delete',
				'/api/templates/' + encodeURIComponent(id))
			if (res.ok) {
				await this.fetchTemplates()
				return {ok: true}
			}
			return {ok: false, error: res.error}
		},

		async insertTemplate(payload) {
			const {id} = payload
			const lang = i18n.global.locale.value
			const res = await apiRequest('post', '/api/templates/'
				+ encodeURIComponent(id) + '/insert?lang=' + encodeURIComponent(lang))
			if (res.ok) {
				await useDashboardStore().fetchNodes()
				return {ok: true, nodes: res.data}
			}
			return {ok: false, error: res.error}
		},

		async fetchSnapshots() {
			const res = await apiRequest('get', '/api/config/snapshots')
			if (res.ok) {
				this.setSnapshots(res.data)
			} else {
				console.error('ERROR loading snapshots: ' + res.error)
				emitLoadError('snapshots')
			}
		},

		async createSnapshot(payload) {
			const res = await apiRequest('post', '/api/config/snapshots', payload)
			if (res.ok) {
				await this.fetchSnapshots()
				return {ok: true, snapshot: res.data}
			}
			return {ok: false, error: res.error}
		},

		async deleteSnapshot(payload) {
			const {name} = payload
			const res = await apiRequest('delete',
				'/api/config/snapshots/' + encodeURIComponent(name))
			if (res.ok) {
				await this.fetchSnapshots()
				return {ok: true}
			}
			return {ok: false, error: res.error}
		},

		async restoreSnapshot(payload) {
			const {name} = payload
			const res = await apiRequest('post',
				'/api/config/snapshots/' + encodeURIComponent(name) + '/restore')
			if (res.ok) {
				await useDashboardStore().fetchNodes()
				return {ok: true, nodes: res.data}
			}
			return {ok: false, error: res.error}
		},

		// --- /wiring editor draft mode (Step 16): all node CRUD below is
		// applied client-side to state.draft only, and only actually sent
		// to the backend as a single atomic diff by saveDraft() ---

		initDraft() {
			const nodes = useDashboardStore().nodes
			this.draftBaseline = clone(nodes)
			this.draft = clone(nodes)
		},

		discardDraft() {
			this.draft = null
			this.draftBaseline = null
		},

		draftCreateNode(payload) {
			const tempId = 'draft-' + (this.draftTempCounter + 1)
			this.bumpDraftTempCounter()
			// _tempId correlates this node with its create entry in the
			// diff (so other nodes' `receives` can reference it and the
			// backend can remap it to the real id). It's the ONLY marker
			// left on a draft node - "new" is simply "id not in baseline".
			const node = Object.assign({}, payload, {
				id: tempId,
				identifier: tempId,
				_tempId: tempId,
			})
			this.setDraftNode(node)
			return node
		},

		draftUpdateNode(payload) {
			const {nodeId, changes} = payload
			const existing = this.draft && this.draft[nodeId]
			if (!existing) {
				return
			}
			this.setDraftNode(Object.assign({}, existing, changes))
		},

		draftDeleteNode(payload) {
			const {nodeId} = payload
			if (!this.draft || !this.draft[nodeId]) {
				return
			}
			// drop the now-dangling wire into this node from every surviving
			// node, mirroring the backend's prune_dangling_references(): a
			// receives entry pointing at a deleted node is not an error, it
			// just goes away with the node. Doing it here also keeps the
			// canvas honest (the edge disappears at once). Alert nodes are
			// skipped: their receives derive from conditions, edited through
			// their own endpoint, and wiringDiff() never emits `receives`
			// for them anyway.
			Object.values(this.draft).forEach(other => {
				if (other.id === nodeId || other.role === 'ALERTS') {
					return
				}
				if ((other.receives || []).includes(nodeId)) {
					this.draftUpdateNode({
						nodeId: other.id,
						changes: {receives: other.receives.filter(id => id !== nodeId)},
					})
				}
			})
			// removed from the working map -> "in baseline but not working"
			// is a delete; "in neither" (a create deleted again) is a no-op
			this.removeDraftNode(nodeId)
		},

		async saveDraft() {
			if (!this.draft) {
				return {ok: true}
			}

			const diff = wiringDiff(this.draftBaseline, this.draft, this.nodeTypes)
			if (!diff.hasChanges) {
				this.discardDraft()
				return {ok: true}
			}

			const res = await apiRequest('post', '/api/config/apply', {
				creates: diff.creates,
				updates: diff.updates,
				deletes: diff.deletes,
			})
			if (res.ok) {
				await useDashboardStore().fetchNodes()
				this.discardDraft()
				return {ok: true, idMap: res.data && res.data.id_map}
			}
			return {ok: false, error: res.error}
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
