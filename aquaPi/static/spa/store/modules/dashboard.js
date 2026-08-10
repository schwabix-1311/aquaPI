import {EventBus, AQUAPI_EVENTS} from '../../components/app/EventBus.js';
import i18n from '../../i18n/index.js';

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
		persistConfig(payload) {
			try {
				const config = []
				payload.forEach((widget) => {
					config.push({identifier: widget.identifier, id: widget.id, name: widget.name, role: widget.role, type: widget.type, visible: widget.visible})
				})
				window.localStorage.setItem('aquapi.dashboard', JSON.stringify(config))
				return true
			} catch(e) {
				console.error(e.message)
				return false
			}
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
				let config = window.localStorage.getItem('aquapi.dashboard')
				if (null === config) {
					// Create (default) dashboard config
					let items = []

					for (let nodeId in nodes) {
						let node = nodes[nodeId]
						items.push({
							id: node.id,
							identifier: node.identifier,
							name: node.name,
							role: node.role,
							type: node.type,
							visible: false
						})
					}

					this.persistConfig(items)
					config = JSON.stringify(items)

					configChanged = true
				}

				config = await JSON.parse(config)

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
					this.persistConfig(config)
				}

				return config
			} catch(e) {
				console.error('ERROR loading dashboard config: ' + e.message)
				return false
			}
		},

		fetchNode(payload) {
			const { nodeId } = payload

			return fetch('/api/nodes/' + nodeId, {
				method: 'get',
				mode: 'same-origin',
				cache: 'no-cache',
				headers: {
					'X-Requested-With': 'XMLHttpRequest',
					'Accept': 'application/json'
				},
				redirect: 'follow'
			})
				.then(response => response.json())
				.then(response => (response.result == 'SUCCESS' ? response.data : null))
				.catch((e) => {
					console.error('Failed to load node ' + nodeId + ': ' + e.message)
					return null
				})
		},

		async fetchNodes() {
			let nodes = {}

			try {
				// Fetch all nodes (returns array of node id)
				const response = await fetch('/api/nodes/', {
					method: 'get',
					mode: 'same-origin',
					cache: 'no-cache',
					headers: {
						'X-Requested-With': 'XMLHttpRequest',
						'Accept': 'application/json'
					},
					redirect: 'follow'
				});

				if (response.status !== 200) {
					throw new Error('GET /api/nodes/ returned ' + response.status)
				}

				const nodeIds = await response.json()

				if (nodeIds.length) {
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

			try {
				const fetchResult = await fetch('/api/history/' + nodeId + '?start=' + start + '&step=' + step, {
					method: 'get',
					mode: 'same-origin',
					cache: 'no-cache',
					headers: {
						'X-Requested-With': 'XMLHttpRequest',
						'Accept': 'application/json'
					},
					redirect: 'follow'
				});

				if (fetchResult.status !== 200) {
					throw new Error('GET /api/history/ returned ' + fetchResult.status)
				}

				const response = await fetchResult.json()
				if (response.result == 'SUCCESS' && response.data) {
					return response.data
				}
				throw new Error('Unexpected response: ' + JSON.stringify(response))
			} catch (e) {
				console.error('ERROR loading history for node ' + nodeId + ': ' + e.message)
				EventBus.$emit(AQUAPI_EVENTS.TOAST_REQUESTED, {
					message: i18n.global.t('misc.toast.loadError', {what: i18n.global.t('misc.toast.what.history')}),
					color: 'error',
					timeout: 6000,
				})
				return null
			}
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
		setNodes(payload) {
			this.nodes = Object.assign({}, payload)
		},
		setAllNodesLoaded(payload) {
			this.allNodesLoaded = payload
		}
	}
})

// vim: set noet ts=4 sw=4:
