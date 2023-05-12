import {EventBus, AQUAPI_EVENTS} from '../components/app/EventBus.js'
import '../components/dashboard/index.js'

const Home = {
	template: `
		<div>
			<aquapi-dashboard></aquapi-dashboard>
		</div>
	`,

	methods: {
		// async handleSSE(payload) {
		//	console.log('[page Home] listenSSE, payload:')
		//	console.log(payload)
		//
		//	let nodeId = null
		//	if (typeof payload == 'string') {
		//		nodeId = payload
		//	} else if (typeof payload == 'object') {
		//		nodeId = payload.id
		//	}
		//
		//	const response = await fetch('/api/nodes/' + nodeId)
		//
		//	try {
		//		const {result, data} = await response.json()
		//		this.$store.commit('dashboard/setNode', data)
		//	} catch (e) {
		//		console.error(`Could not fetch node ${nodeId}`)
		//		console.log(e)
		//	}
		// }
	},

	created() {
		// EventBus.$on(AQUAPI_EVENTS.SSE_NODE_UPDATE, this.handleSSE)
	},
	destroyed() {
		// EventBus.$off(AQUAPI_EVENTS.SSE_NODE_UPDATE, this.handleSSE)
	}
};

export { Home };

// vim: set noet ts=4 sw=4:
