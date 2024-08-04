const EventBus = new Vue()

const AQUAPI_EVENTS = {
	AUTH_LOGGED_IN: 'auth:logged_in',
	AUTH_LOGGED_OUT: 'auth:logged_out',
	SSE_NODE_UPDATE: 'sse:node_update',
	APP_LOADING: 'app:loading',
	DIALOG_CLOSED: 'ui:dialog_closed',
	DIALOG_OPENED: 'ui:dialog_opened'
}
export {EventBus, AQUAPI_EVENTS}

// vim: set noet ts=4 sw=4:
