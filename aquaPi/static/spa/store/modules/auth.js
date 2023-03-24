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
	login(context, payload) {
		// TODO: implement server side ...
		if (window.localStorage) {
			window.localStorage.setItem('aquapi.user', JSON.stringify({username: payload.username}))
		}

		context.commit('setUser', {username: payload.username})
		EventBus.$emit(AQUAPI_EVENTS.AUTH_LOGGED_IN)
	},
	logout(context) {
		// TODO: implement server side ...
		if (window.localStorage) {
			window.localStorage.setItem('aquapi.user', null)
		}
		context.commit('setUser', null)
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
