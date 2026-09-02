import {EventBus, AQUAPI_EVENTS} from './components/app/EventBus.js'
import {useDashboardStore} from './store/modules/dashboard.js'

const App = {
	template: `
		<router-view></router-view>
	`,
	name: 'App',
	data: () => ({
		sseSource: null,
	}),

	computed: {
		dashboardStore() {
			return useDashboardStore()
		},
	},

	methods: {
		initEventListeners() {
			this.connectSSE()
			document.addEventListener('visibilitychange', this.handleVisibilityChange)
			EventBus.$on(AQUAPI_EVENTS.SSE_NODE_UPDATE, this.handleSSE)
		},
		detachEventListeners() {
			document.removeEventListener('visibilitychange', this.handleVisibilityChange)
			this.disconnectSSE()
			EventBus.$off(AQUAPI_EVENTS.SSE_NODE_UPDATE)
		},
		connectSSE() {
			if (typeof EventSource === 'undefined') {
				return
			}

			const urlSSE = `${window.location.protocol}//${window.location.host}/api/sse`
			this.sseSource = new EventSource(urlSSE)

			this.sseSource.onmessage = function(e) {
				// this is an array of node ids that were modified
				const items = JSON.parse(e.data)
				if (items.length) {
					items.forEach((item) => {
						//console.log('[App] >> emit event "sse:node_update" with item: ' + item)
						EventBus.$emit(AQUAPI_EVENTS.SSE_NODE_UPDATE, {id: item, identifier: 'node__' + item})
					})
				}
			}

			this.sseSource.onerror = function(e) {
				// the browser retries on its own for a plain connection
				// drop; logged here since this also fires for a connection
				// that turns out to be a client-suspend zombie, right
				// before handleVisibilityChange forces a reconnect
				console.debug('[App] SSE connection error, browser will retry', e)
			}
		},
		disconnectSSE() {
			if (this.sseSource) {
				this.sseSource.close()
				this.sseSource = null
			}
		},
		handleVisibilityChange() {
			// a suspended/hibernated client's EventSource can keep
			// reporting readyState OPEN after resume even though the
			// underlying TCP connection is dead (no FIN/RST was ever
			// exchanged across the suspend) - force a fresh connection
			// whenever the tab becomes visible again rather than trusting
			// the stale one
			if (document.visibilityState === 'visible') {
				this.disconnectSSE()
				this.connectSSE()
			}
		},
		async fetchNodes() {
			await this.dashboardStore.fetchNodes()
		},
		async handleSSE(payload) {
			let nodeId = null
			if (typeof payload == 'string') {
				nodeId = payload
			} else if (typeof payload == 'object') {
				nodeId = payload.id
			}

			const response = await fetch('/api/nodes/' + nodeId)

			try {
				const {result, data} = await response.json()
				this.dashboardStore.setNode(data)
			} catch (e) {
				console.error(`Could not fetch node ${nodeId}`)
				console.log(e)
			}
		}
	},

	async created() {
		await this.fetchNodes()
		this.initEventListeners()
	},

	unmounted() {
		this.detachEventListeners()
	}
};

export default App;

// vim: set noet ts=4 sw=4:
