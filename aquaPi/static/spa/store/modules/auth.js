import {AQUAPI_EVENTS, EventBus} from '../../components/app/EventBus.js';

const state = () => ({
	user: {
		username: null
	},
})

const getters = {
	authenticated: (state) => {
		return (state.user && state.user.username) ? true : false
	},
	user: (state) => {
		return state.user
	},
	username: (state, getters) => {
		return state.user.username
	}
}

const actions = {
	async login(context, payload) {
		let data
		try {
			const response = await fetch('/login', {
				method: 'post',
				mode: 'same-origin',
				cache: 'no-cache',
				headers: {
					'X-Requested-With': 'XMLHttpRequest',
					'Content-Type': 'application/x-www-form-urlencoded',
					'Accept': 'application/json',
				},
				body: new URLSearchParams({username: payload.username, password: payload.password}),
			})
			data = await response.json().catch(() => null)
		} catch (e) {
			return {ok: false, error: e.message}
		}

		if (!data || data.result !== 'SUCCESS') {
			return {ok: false, error: (data && data.message) || 'Login failed'}
		}

		// the login itself only confirms the credentials - fetch the
		// real user (id/username/role) from the now-established
		// server session, instead of just guessing from the payload
		const user = await context.dispatch('users/fetchCurrentUser', null, {root: true})
		context.commit('setUser', {username: (user && user.username) || payload.username})
		EventBus.$emit(AQUAPI_EVENTS.AUTH_LOGGED_IN)
		return {ok: true}
	},
	async logout(context) {
		try {
			await fetch('/logout', {
				method: 'get',
				mode: 'same-origin',
				cache: 'no-cache',
				headers: {
					'X-Requested-With': 'XMLHttpRequest',
					'Accept': 'application/json',
				},
			})
		} catch (e) {
			// best-effort: still clear the local state below
		}
		context.commit('setUser', null)
		context.commit('users/setCurrentUser', null, {root: true})
		EventBus.$emit(AQUAPI_EVENTS.AUTH_LOGGED_OUT)
	}
}

const mutations = {
	setUser(state, payload) {
		if (null == payload) {
			state.user = Object.assign({}, {username: null});
		} else if (payload.username) {
			state.user = Object.assign({}, {username: payload.username})
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
