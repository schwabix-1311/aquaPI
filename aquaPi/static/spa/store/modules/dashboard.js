import {EventBus, AQUAPI_EVENTS} from '../../components/app/EventBus.js';
import i18n from '../../i18n/index.js';
import {apiRequest} from '../apiRequest.js';

export const useDashboardStore = Pinia.defineStore('dashboard', {
	state: () => ({
		widgets: [],
		nodes: {},
		allNodesLoaded: false
	}),

	getters: {
		visibleWidgets: (state) => {
			let items = {}
			state.widgets.filter(item => item.visible == true)
				.forEach(item => {
					items[item.id] = item
				})
			return items
		},
		node: (state) => (nodeId) => {
			return state.nodes[nodeId]
		}
	},

	actions: {
		async fetchDashboard() {
			const res = await apiRequest('get', '/api/dashboard/')
			return res.ok ? res.data : null
		},
		async saveDashboard(config) {
			const res = await apiRequest('put', '/api/dashboard/', config)
			if (!res.ok) {
				console.error('ERROR saving dashboard config: ' + res.error)
			}
			return res.ok
		},
		async loadConfig() {
			let configChanged = false

			// Fetch all available nodes
			if (!this.allNodesLoaded) {
				await this.fetchNodes()
			}

			// Get all available nodes from store
			const nodes = this.nodes

			try {
				// the per-user server layout is the sole source of truth;
				// null (401/offline/error) is treated as "nothing saved
				// yet", same as a legitimate empty '[]' response
				let config = await this.fetchDashboard()
				if (config === null) {
					config = []
				}

				// Remove dashboard items for no longer existing nodes
				config = config.filter((item) => nodes[item.id] !== undefined)

				// Refresh role/type/identifier from the live node for
				// existing items - a node's id is derived from its name,
				// so if two nodes ever swap names (id stays the same, but
				// the role/type behind that id changes), a stale cached
				// role/type would otherwise persist forever. 'name' and
				// 'visible' are intentionally left alone: 'name' can be
				// user-customized in the configurator, 'visible' is a
				// pure user preference.
				config.forEach((item) => {
					const node = nodes[item.id]
					if (item.role !== node.role || item.type !== node.type
						|| item.identifier !== node.identifier) {
						item.role = node.role
						item.type = node.type
						item.identifier = node.identifier
						configChanged = true
					}
				})

				// Add dashboard items for new nodes
				for (let nodeId in nodes) {
					if (config.filter((item) => item.id === nodeId).length == 0) {
						let node = nodes[nodeId]
						config.push({
							id: node.id,
							identifier: node.identifier,
							name: node.name,
							role: node.role,
							type: node.type,
							visible: false
						})

						configChanged = true
					}
				}

				if (configChanged) {
					await this.saveDashboard(config)
				}

				return config
			} catch(e) {
				console.error('ERROR loading dashboard config: ' + e.message)
				return false
			}
		},

		async fetchNode(payload) {
			const { nodeId } = payload

			const res = await apiRequest('get', '/api/nodes/' + nodeId)

			// fetchNodes() lists all node ids, then fetches each in parallel -
			// one can be deleted (elsewhere, or by an SSE-triggered reload)
			// between the list and this fetch. That 404 has no body, so
			// treat it as the expected "it's gone" case instead of a load
			// failure.
			if (res.status === 404) {
				console.debug(`fetchNode: ${nodeId} no longer exists (404 above is expected)`)
				return null
			}
			if (!res.ok) {
				console.error(`Failed to load node ${nodeId}: ${res.error}`)
				return null
			}

			return res.data && res.data.result === 'SUCCESS' ? res.data.data : null
		},

		async fetchNodes() {
			let nodes = {}

			try {
				// Fetch all nodes (returns array of node id)
				const res = await apiRequest('get', '/api/nodes/')
				if (!res.ok) {
					throw new Error('GET /api/nodes/ returned ' + res.status)
				}

				const nodeIds = res.data

				if (nodeIds && nodeIds.length) {
					const values = await Promise.all(nodeIds.map(nodeId => this.fetchNode({nodeId})))
					values.filter(item => item).forEach(item => {
						nodes[item.id] = item
					})
				}

				this.setNodes(nodes)
				this.setAllNodesLoaded(true)
			} catch (e) {
				console.error('ERROR loading nodes: ' + e.message)
				EventBus.$emit(AQUAPI_EVENTS.TOAST_REQUESTED, {
					message: i18n.global.t('misc.toast.loadError', {what: i18n.global.t('misc.toast.what.nodes')}),
					color: 'error',
					timeout: 6000,
				})
			} finally {
				EventBus.$emit(AQUAPI_EVENTS.APP_LOADING, false)
			}

			return this.nodes
		},

		async fetchNodeHistory(payload) {
			let { nodeId, start, step} = payload

			if (null === start || start === 0) {
				start = 1
			}
			if (null === step) {
				step = 0
			}

			const res = await apiRequest('get',
				'/api/history/' + nodeId + '?start=' + start + '&step=' + step)

			if (res.ok && res.data && res.data.result == 'SUCCESS' && res.data.data) {
				return res.data.data
			}

			console.error('ERROR loading history for node ' + nodeId + ': '
				+ (res.error || 'Unexpected response: ' + JSON.stringify(res.data)))
			EventBus.$emit(AQUAPI_EVENTS.TOAST_REQUESTED, {
				message: i18n.global.t('misc.toast.loadError', {what: i18n.global.t('misc.toast.what.history')}),
				color: 'error',
				timeout: 6000,
			})
			return null
		},

		setWidgets(payload) {
			this.widgets = payload
		},
		setNode(payload) {
			try {
				let nodes = this.nodes
				nodes[payload.id] = payload
				this.nodes = nodes
			} catch (e) {
				console.log('ERROR mutating state.nodes:')
				console.error(e)
			}
		},
		removeNode(nodeId) {
			if (this.nodes[nodeId] === undefined) {
				return
			}
			const nodes = Object.assign({}, this.nodes)
			delete nodes[nodeId]
			this.nodes = nodes
		},
		setNodes(payload) {
			this.nodes = Object.assign({}, payload)
		},
		setAllNodesLoaded(payload) {
			this.allNodesLoaded = payload
		}
	}
})

// vim: set noet ts=4 sw=4:
