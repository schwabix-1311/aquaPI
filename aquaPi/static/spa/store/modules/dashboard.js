import {EventBus, AQUAPI_EVENTS} from '../../components/app/EventBus.js';

const state = () => ({
	widgets: [],
	nodes: {},
	allNodesLoaded: false
})
const getters = {
	widgets: (state) => {
		return state.widgets
	},
	visibleWidgets: (state) => {
		let items = {}
		state.widgets.filter(item => item.visible == true)
			.forEach(item => {
				items[item.id] = item
			})
		return items
	},
	nodes: (state) => {
		return state.nodes
	},
	allNodesLoaded: (state) => {
		return state.allNodesLoaded
	},
	node: (state) => (nodeId) => {
		return state.nodes[nodeId]
	}
}

const actions = {
	persistConfig(context, payload) {
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
	async loadConfig(context) {
		let configChanged = false

		// Fetch all available nodes
		if (!context.getters['allNodesLoaded']) {
			await context.dispatch('fetchNodes')
		}

		// Get all available nodes from store
		const nodes = await context.getters['nodes']

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

				context.dispatch('persistConfig', items)
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
				context.dispatch('persistConfig', config)
			}

			return config
		} catch(e) {
			console.error('ERROR loading dashboard config: ' + e.message)
			return false
		}
	},

	fetchNode({state, getters, dispatch, commit}, payload) {
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

	async fetchNodes({state, getters, dispatch, commit}) {
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
				let promises = nodeIds.map(nodeId => dispatch('fetchNode', {nodeId}))

				await Promise.all(promises)
					.then(values => {
						values.forEach(item => {
							nodes[item.id] = item
						})

						commit('setNodes', nodes)
						commit('setAllNodesLoaded', true)
						EventBus.$emit(AQUAPI_EVENTS.APP_LOADING, false)
					})
			}
		}

		return await state.nodes
	},

	async fetchNodeHistory({state, getters, dispatch, commit}, payload) {
		let { nodeId, start, step} = payload

		if (null === start || start === 0) {
			start = 1
		}
		if (null === step || step == 0) {
			step = 30
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
}

const mutations = {
	setWidgets(state, payload) {
		state.widgets = payload
	},
	setNode(state, payload) {
		try {
			let nodes = state.nodes
			nodes[payload.id] = payload
			state.nodes = nodes
		} catch (e) {
			console.log('ERROR mutating state.nodes:')
			console.error(e)
		}
	},
	setNodes(state, payload) {
		state.nodes = Object.assign({}, payload)
	},
	setAllNodesLoaded(state, payload) {
		state.allNodesLoaded = payload
	}
}

export default {
	namespaced: true,
	state,
	getters,
	actions,
	mutations
}

// vim: set noet ts=4 sw=4:
