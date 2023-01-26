import {EventBus, AQUAPI_EVENTS} from './components/app/EventBus.js'

const App = {
	template: `
    <v-app>
        <router-view></router-view>
    </v-app>
  `,
	name: 'App',
	data: () => ({
	}),

	methods: {
		initEventListeners() {
		 	this.initSSEListener()
		},
		detachEventListeners() {
		 	EventBus.$off(AQUAPI_EVENTS.SSE_NODE_UPDATE)
			// EventBus.$off(AQUAPI_EVENTS.SSE_NODE_UPDATE, this.handleSSE)
		},
		initSSEListener() {
			if (typeof EventSource !== 'undefined') {
				const urlSSE = `${window.location.protocol}//${window.location.host}/api/sse`
				const source = new EventSource(urlSSE);

				source.onmessage = function(e) {
					// this is an array of node ids that were modified
					const items = JSON.parse(e.data);
					if (items.length) {
						items.forEach((item) => {
							console.log('[App] >> emit event "sse:node_update" with item: ' + item)
							EventBus.$emit(AQUAPI_EVENTS.SSE_NODE_UPDATE, {id: item, identifier: 'node__' + item})
						})
					}
				}
			}

			EventBus.$on(AQUAPI_EVENTS.SSE_NODE_UPDATE, this.handleSSE)
		},
		loadNodes() {
			this.$store.dispatch('dashboard/loadNodes')
		},
		async handleSSE(payload) {
			console.log('[App] listenSSE, payload:')
			console.log(payload)

			let nodeId = null
			if (typeof payload == 'string') {
				nodeId = payload
			} else if (typeof payload == 'object') {
				nodeId = payload.id
			}

			const response = await fetch('/api/nodes/' + nodeId)

			try {
				const {result, data} = await response.json()
				this.$store.commit('dashboard/setNode', data)
			} catch (e) {
				console.error(`Could not fetch node ${nodeId}`)
				console.log(e)
			}
		}
	},

	created() {
		this.initEventListeners()
	},

	beforeMount() {
		this.loadNodes()
	},

	destroyed() {
		this.detachEventListeners()
	}
};

export default App;
