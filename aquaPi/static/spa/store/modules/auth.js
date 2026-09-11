import {AQUAPI_EVENTS, EventBus} from '../../components/app/EventBus.js';
import {apiRequest} from '../apiRequest.js';
import {useUsersStore} from './users.js';

export const useAuthStore = Pinia.defineStore('auth', {
	state: () => ({
		user: {
			username: null
		},
		resetToken: null,
	}),

	getters: {
		authenticated: (state) => {
			return (state.user && state.user.username) ? true : false
		},
		username: (state) => {
			return state.user.username
		}
	},

	actions: {
		async login(payload) {
			// these are plain Flask-Login form routes, not the JSON /api/*
			// surface - {form: true} posts x-www-form-urlencoded, and a
			// wrong password/username still comes back HTTP 200 with
			// {result: 'FAIL', message}, so success is read from the body,
			// not apiRequest()'s own ok/error (HTTP-status-derived)
			const res = await apiRequest('post', '/login',
				{username: payload.username, password: payload.password}, {form: true})
			if (!res.data) {
				// non-JSON body (e.g. a 500 error page) - the status code is
				// the only useful information left
				return {ok: false, error: res.error || ('HTTP ' + res.status)}
			}
			if (res.data.result !== 'SUCCESS') {
				return {ok: false, error: res.data.message || 'Login failed'}
			}

			// the login itself only confirms the credentials - fetch the
			// real user (id/username/role) from the now-established
			// server session, instead of just guessing from the payload
			const user = await useUsersStore().fetchCurrentUser()
			this.setUser({username: (user && user.username) || payload.username})
			EventBus.$emit(AQUAPI_EVENTS.AUTH_LOGGED_IN)
			return {ok: true}
		},
		async logout() {
			// best-effort: apiRequest() never throws, and its result is
			// intentionally ignored here - either way, refresh identity below
			await apiRequest('get', '/logout')
			// the backend immediately re-establishes the reserved
			// <anonymous> session on the very next request (see auth.py's
			// before_request hook) - refetch identity instead of freezing
			// on a stale "nobody" state, symmetric to login()'s own
			// fetchCurrentUser() call above
			const user = await useUsersStore().fetchCurrentUser()
			this.setUser(user)
			EventBus.$emit(AQUAPI_EVENTS.AUTH_LOGGED_OUT)
		},

		setUser(payload) {
			if (null == payload) {
				this.user = Object.assign({}, {username: null});
			} else if (payload.username) {
				this.user = Object.assign({}, {username: payload.username})
			}
		},

		setPendingResetToken(token) {
			this.resetToken = token
		},

		async requestPasswordReset(username) {
			const res = await apiRequest('post', '/reset-password', {username}, {form: true})
			if (!res.data || res.data.result !== 'SUCCESS') {
				return {ok: false, error: (res.data && res.data.message) || res.error || ('HTTP ' + res.status)}
			}
			return {ok: true}
		},

		async checkResetToken(token) {
			const res = await apiRequest('get', '/reset-password/' + token)
			return !!(res.data && res.data.valid)
		},

		async confirmPasswordReset(token, password, password2) {
			const res = await apiRequest('post', '/reset-password/' + token,
				{password, password2}, {form: true})
			if (!res.data || res.data.result !== 'SUCCESS') {
				return {ok: false, error: (res.data && res.data.message) || res.error || ('HTTP ' + res.status)}
			}
			this.resetToken = null
			return {ok: true}
		},
	}
})

// vim: set noet ts=4 sw=4:
