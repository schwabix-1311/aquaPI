// Vue 3 instances no longer support $on/$off/$emit, so `new Vue()` can't
// be used as a lightweight cross-component event bus anymore. This tiny
// class keeps the exact same $on/$off/$emit API so all existing call
// sites (EventBus.$on(...), .$off(...), .$emit(...)) stay unchanged.
class MiniEmitter {
	constructor() {
		this._listeners = new Map()
	}

	$on(event, fn) {
		if (!this._listeners.has(event)) {
			this._listeners.set(event, new Set())
		}
		this._listeners.get(event).add(fn)
	}

	$off(event, fn) {
		if (!this._listeners.has(event)) {
			return
		}
		if (fn) {
			this._listeners.get(event).delete(fn)
		} else {
			this._listeners.delete(event)
		}
	}

	$emit(event, ...args) {
		if (!this._listeners.has(event)) {
			return
		}
		this._listeners.get(event).forEach(fn => fn(...args))
	}
}

const EventBus = new MiniEmitter()

const AQUAPI_EVENTS = {
	AUTH_LOGGED_IN: 'auth:logged_in',
	AUTH_LOGGED_OUT: 'auth:logged_out',
	SSE_NODE_UPDATE: 'sse:node_update',
	APP_LOADING: 'app:loading',
	DIALOG_CLOSED: 'ui:dialog_closed',
	DIALOG_OPENED: 'ui:dialog_opened',
	CONFIRM_REQUESTED: 'ui:confirm_requested'
}
export {EventBus, AQUAPI_EVENTS}

// vim: set noet ts=4 sw=4:
