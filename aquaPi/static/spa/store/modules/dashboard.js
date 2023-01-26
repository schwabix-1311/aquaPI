import {EventBus, AQUAPI_EVENTS} from '../../components/app/EventBus.js';

const state = () => ({
	widgets: [],
	nodes: {}
})
const getters = {
	widgets: (state) => {
		return state.widgets
	},
	nodes: (state) => {
		return state.nodes
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
		try {
			let config = window.localStorage.getItem('aquapi.dashboard')
			// config = await JSON.parse(config)
			return await JSON.parse(config)
		} catch(e) {
			console.error('ERROR loading dashboard config: ' + e.message)
			return false
		}
	},

	async loadNodes(context, addHistory=false) {
		let nodes = {}

		function fetchNode(nodeId) {
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
					// context.commit('setNode', response.data)
					return (response.result == 'SUCCESS' ? response.data : null)
				})
				.catch((e) => { console.error(e.message) })
			return nodePromise
		}

		// Fetch all nodes (returns array if node id)
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
				let promises = nodeIds.map(nodeId => fetchNode(nodeId))

				Promise.all(promises)
  					.then(values => {
						values.forEach(item => {
							nodes[item.id] = item
						})

						context.commit('setNodes', nodes)
						EventBus.$emit(AQUAPI_EVENTS.APP_LOADING, false)
					})
			}
		}
	}
}

const mutations = {
	setWidgets(state, payload) {
		state.widgets = payload
	},
	setNode(state, payload) {
		try {
			console.log('#### store dashboard setNode, payload:')
			console.log(payload);

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
	}
}

export default {
	namespaced: true,
	state,
	getters,
	actions,
	mutations
}