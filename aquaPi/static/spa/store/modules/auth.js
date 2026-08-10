import {AQUAPI_EVENTS, EventBus} from '../../components/app/EventBus.js';
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
				if (!data) {
					// non-JSON body (e.g. a 500 error page) - the status
					// code is the only useful information left
					return {ok: false, error: 'HTTP ' + response.status}
				}
			} catch (e) {
				return {ok: false, error: e.message}
			}

			if (data.result !== 'SUCCESS') {
				return {ok: false, error: data.message || 'Login failed'}
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
			this.setUser(null)
			useUsersStore().setCurrentUser(null)
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
			try {
				const response = await fetch('/reset-password', {
					method: 'post',
					mode: 'same-origin',
					cache: 'no-cache',
					headers: {
						'X-Requested-With': 'XMLHttpRequest',
						'Content-Type': 'application/x-www-form-urlencoded',
						'Accept': 'application/json',
					},
					body: new URLSearchParams({username}),
				})
				const data = await response.json().catch(() => null)
				if (!data || data.result !== 'SUCCESS') {
					return {ok: false, error: (data && data.message) || 'HTTP ' + response.status}
				}
				return {ok: true}
			} catch (e) {
				return {ok: false, error: e.message}
			}
		},

		async checkResetToken(token) {
			try {
				const response = await fetch('/reset-password/' + token, {
					method: 'get',
					mode: 'same-origin',
					cache: 'no-cache',
					headers: {
						'X-Requested-With': 'XMLHttpRequest',
						'Accept': 'application/json',
					},
				})
				const data = await response.json().catch(() => null)
				return !!(data && data.valid)
			} catch (e) {
				return false
			}
		},

		async confirmPasswordReset(token, password, password2) {
			try {
				const response = await fetch('/reset-password/' + token, {
					method: 'post',
					mode: 'same-origin',
					cache: 'no-cache',
					headers: {
						'X-Requested-With': 'XMLHttpRequest',
						'Content-Type': 'application/x-www-form-urlencoded',
						'Accept': 'application/json',
					},
					body: new URLSearchParams({password, password2}),
				})
				const data = await response.json().catch(() => null)
				if (!data || data.result !== 'SUCCESS') {
					return {ok: false, error: (data && data.message) || 'HTTP ' + response.status}
				}
				this.resetToken = null
				return {ok: true}
			} catch (e) {
				return {ok: false, error: e.message}
			}
		},
	}
})

// vim: set noet ts=4 sw=4:
