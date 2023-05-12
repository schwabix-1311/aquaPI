import {EventBus, AQUAPI_EVENTS} from '../../components/app/EventBus.js';

const state = () => ({
	widgets: [],
	nodes: {},
	histories: {}
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
	node: (state) => (nodeId) => {
		return state.nodes[nodeId]
	},
	histories: (state) => {
		return state.histories
	},
	history: (state) => (nodeId) => {
		return state.histories[nodeId]
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
		try {
			let config = window.localStorage.getItem('aquapi.dashboard')
			if (null === config) {
				// Fetch (default) dashboard config
				let items = await context.dispatch('fetchDashboard');
				if (items) {
					items.forEach((item) => {
						item.visible = false
					})
					context.dispatch('persistConfig', items)
					config = JSON.stringify(items)
				}
			}
			return await JSON.parse(config)
		} catch(e) {
			console.error('ERROR loading dashboard config: ' + e.message)
			return false
		}
	},

	async fetchDashboard(context, addHistory= false) {
		const fetchResult = await fetch('/api/config/dashboard' + '?add_history=' + (addHistory ? 'true' : 'false'), {
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

	fetchNode({state, getters, dispatch, commit}, payload) {
		const { nodeId, addHistory } = payload

		/** @type {Promise.<any>} */
		let fetchPromise = fetch('/api/nodes/' + nodeId + '?add_history=' + (addHistory ? 'true' : 'false'), {
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

	async loadNodes({state, getters, dispatch, commit}, addHistory= false) {
		let nodes = {}

		// Fetch all nodes (returns array of node id)
		const response = await fetch('/api/nodes/' + '?add_history=' + (addHistory ? 'true' : 'false'), {
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
				let promises = nodeIds.map(nodeId => dispatch('fetchNode', {nodeId, addHistory}))

				Promise.all(promises)
					.then(values => {
						values.forEach(item => {
							nodes[item.id] = item
						})

						commit('setNodes', nodes)
						EventBus.$emit(AQUAPI_EVENTS.APP_LOADING, false)
					})
			}
		}
	},

	// TODO: prelim. method for new history API
	// async loadNodeHistory({state, getters, dispatch, commit}, node) {
	//	console.log('### loadNodesHistory')
	//	console.log('node:', node)
	//	const nodeIds = node.inputs?.sender
	//
	//	let histories = {}
	//
	//	if (nodeIds.length) {
	//		let promises = nodeIds.map(nodeId => dispatch('fetchNode', {nodeId, addHistory: true}))
	//
	//		Promise.all(promises)
	//			.then(values => {
	//				values.forEach(item => {
	//					console.log('... item:', item)
	//					histories[item.id] = item
	//				})
	//
	//				commit('setHistories', histories)
	//			})
	//	}
	// },
	async loadNodeHistory({state, getters, dispatch, commit}, node) {
		const nodeId = node.id

		const result = await dispatch('fetchNode', {nodeId, addHistory: true})

		if (result?.store) {
			commit('setHistory', {id: nodeId, data: result.store})

			await Object.entries(result.store).forEach(([id, data]) => {
				commit('setHistory', {id, data})
			})
		}

		return state.histories[nodeId]
	}
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
	setHistories(state, payload) {
		state.histories = Object.assign({}, state.histories, payload)
	},
	setHistory(state, payload) {
		try {
			state.histories[payload.id] = payload.data
		} catch (e) {
			console.log('ERROR mutating state.histories')
			console.error(e)
		}
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
