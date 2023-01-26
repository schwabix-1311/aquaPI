const EventBus = new Vue()

const AQUAPI_EVENTS = {
	AUTH_LOGGED_IN: 'auth:logged_in',
	AUTH_LOGGED_OUT: 'auth:logged_out',
	SSE_NODE_UPDATE: 'sse:node_update',
	APP_LOADING: 'app:loading',
}
export {EventBus, AQUAPI_EVENTS}
