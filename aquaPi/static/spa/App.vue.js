import {EventBus, AQUAPI_EVENTS} from './components/app/EventBus.js'
import {useDashboardStore} from './store/modules/dashboard.js'
import {sseIsStale, CHECK_EVERY_MS} from './components/app/sseWatchdog.js'

const App = {
	template: `
		<router-view></router-view>
	`,
	name: 'App',
	data: () => ({
		sseSource: null,
		sseLastActivity: 0,
		sseWatchdog: null,
	}),

	computed: {
		dashboardStore() {
			return useDashboardStore()
		},
	},

	methods: {
		initEventListeners() {
			this.connectSSE()
			document.addEventListener('visibilitychange', this.checkSSE)
			window.addEventListener('online', this.checkSSE)
			this.sseWatchdog = window.setInterval(this.checkSSE, CHECK_EVERY_MS)
			EventBus.$on(AQUAPI_EVENTS.SSE_NODE_UPDATE, this.handleSSE)
		},
		detachEventListeners() {
			document.removeEventListener('visibilitychange', this.checkSSE)
			window.removeEventListener('online', this.checkSSE)
			window.clearInterval(this.sseWatchdog)
			this.sseWatchdog = null
			this.disconnectSSE()
			EventBus.$off(AQUAPI_EVENTS.SSE_NODE_UPDATE)
		},
		connectSSE() {
			if (typeof EventSource === 'undefined') {
				return
			}

			const urlSSE = `${window.location.protocol}//${window.location.host}/api/sse`
			this.sseSource = new EventSource(urlSSE)
			this.sseLastActivity = Date.now()

			// any traffic, including the server's idle 'ping', proves the
			// connection alive - see sseWatchdog.js
			const touch = () => { this.sseLastActivity = Date.now() }
			this.sseSource.onopen = touch
			this.sseSource.addEventListener('ping', touch)

			this.sseSource.onmessage = (e) => {
				touch()
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
				// drop; a dead connection it doesn't notice is replaced by
				// checkSSE() once the pings stop
				console.debug('[App] SSE connection error, browser will retry', e)
			}
		},
		disconnectSSE() {
			if (this.sseSource) {
				this.sseSource.close()
				this.sseSource = null
			}
		},
		checkSSE() {
			// runs every CHECK_EVERY_MS, and on tab-visible / network-online.
			// After a suspend the first check sees hours without pings,
			// even when the tab stayed visible and visibilitychange never
			// fired. Updates sent meanwhile are lost with the old
			// connection, so every node is refreshed as if it had changed -
			// which also reloads the history charts.
			if (!this.sseSource || !sseIsStale(Date.now(), this.sseLastActivity)) {
				return
			}
			console.debug('[App] SSE silent too long, reconnecting')
			this.disconnectSSE()
			this.connectSSE()
			Object.keys(this.dashboardStore.nodes).forEach((id) => {
				EventBus.$emit(AQUAPI_EVENTS.SSE_NODE_UPDATE, {id: id, identifier: 'node__' + id})
			})
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
			if (!nodeId) {
				return
			}

			let response
			try {
				response = await fetch('/api/nodes/' + encodeURIComponent(nodeId))
			} catch (e) {
				console.error(`SSE: network error fetching node ${nodeId}`, e)
				return
			}

			// the SSE event can race a delete: the node is already gone by the
			// time we fetch it. That's expected - drop it from the store, don't
			// try to parse a 404's (empty/HTML) body as JSON. The browser's own
			// network log still shows the 404 itself (not ours to suppress);
			// this just labels it so it doesn't read as a bug.
			if (response.status === 404) {
				console.debug(`SSE: node ${nodeId} already deleted (404 above is expected)`)
				this.dashboardStore.removeNode(nodeId)
				return
			}
			if (!response.ok) {
				console.error(`SSE: fetching node ${nodeId} failed (${response.status})`)
				return
			}

			try {
				const {data} = await response.json()
				this.dashboardStore.setNode(data)
			} catch (e) {
				console.error(`SSE: could not parse node ${nodeId}`, e)
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
