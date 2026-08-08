import {EventBus, AQUAPI_EVENTS} from '../../components/app/EventBus.js';

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

			/** @type {Promise.<any>} */
			let fetchPromise = fetch('/api/nodes/' + nodeId, {
				method: 'get',
				mode: 'same-origin',
				cache: 'no-cache',
				headers: {
					'X-Requested-With': 'XMLHttpRequest',
					'Accept': 'application/json'
				},
				redirect: 'follow'
			}).then(response => response.json())

			let nodePromise = fetchPromise
				.then(response => {
					return (response.result == 'SUCCESS' ? response.data : null)
				})
				.catch((e) => { console.error(e.message) })
			return nodePromise
		},

		async fetchNodes() {
			let nodes = {}

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

			if (response.status == 200) {
				let nodeIds = await response.json()

				if (nodeIds.length) {
					let promises = nodeIds.map(nodeId => this.fetchNode({nodeId}))

					await Promise.all(promises)
						.then(values => {
							values.forEach(item => {
								nodes[item.id] = item
							})

							this.setNodes(nodes)
							this.setAllNodesLoaded(true)
							EventBus.$emit(AQUAPI_EVENTS.APP_LOADING, false)
						})
				}
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

			if (fetchResult.status == 200) {
				let response = await fetchResult.json()
				if (response.result == 'SUCCESS' && response.data) {
					return response.data
				}
			}

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
		setNodes(payload) {
			this.nodes = Object.assign({}, payload)
		},
		setAllNodesLoaded(payload) {
			this.allNodesLoaded = payload
		}
	}
})

// vim: set noet ts=4 sw=4:
