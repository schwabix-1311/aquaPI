import {EventBus, AQUAPI_EVENTS} from '../../components/app/EventBus.js';
import i18n from '../../i18n/index.js';
import {apiRequest} from '../apiRequest.js';

export const useUsersStore = Pinia.defineStore('users', {
	state: () => ({
		list: [],
		listLoaded: false,
		currentUser: null,
	}),

	getters: {
		all: (state) => {
			return state.list
		},
		role: (state) => {
			return state.currentUser ? state.currentUser.role : null
		},
		isAdmin: (state) => {
			return !!state.currentUser && state.currentUser.role === 'admin'
		},
		isOperatorOrAdmin: (state) => {
			return !!state.currentUser
				&& (state.currentUser.role === 'operator' || state.currentUser.role === 'admin')
		},
		isAnonymous: (state) => {
			return !!state.currentUser && !!state.currentUser.is_anonymous
		},
	},

	actions: {
		async fetchCurrentUser() {
			// not logged in (yet), or network error - keep currentUser null,
			// no error log (this is the expected state before a session exists)
			const res = await apiRequest('get', '/api/users/me')
			this.setCurrentUser(res.ok ? res.data : null)
			return res.ok ? res.data : null
		},

		async fetchAll() {
			const res = await apiRequest('get', '/api/users/')
			if (!res.ok) {
				console.error('ERROR loading users: ' + res.error)
				EventBus.$emit(AQUAPI_EVENTS.TOAST_REQUESTED, {
					message: i18n.global.t('misc.toast.loadError', {what: i18n.global.t('misc.toast.what.users')}),
					color: 'error',
					timeout: 6000,
				})
				return []
			}
			this.setList(res.data)
			return res.data
		},

		async suggestPassword() {
			const res = await apiRequest('get', '/api/users/suggest-password')
			if (!res.ok) {
				console.error('ERROR suggesting password: ' + res.error)
				return null
			}
			return res.data.password
		},

		async create(payload) {
			const res = await apiRequest('post', '/api/users/', payload)
			if (res.status === 201) {
				await this.fetchAll()
				return {ok: true, user: res.data}
			}
			return {ok: false, error: res.error}
		},

		async update(payload) {
			const {userId, changes} = payload
			const res = await apiRequest('put', '/api/users/' + userId, changes)
			if (res.status === 200) {
				await this.fetchAll()
				return {ok: true, user: res.data}
			}
			return {ok: false, error: res.error}
		},

		async remove(userId) {
			const res = await apiRequest('delete', '/api/users/' + userId)
			if (res.status === 204) {
				await this.fetchAll()
				return {ok: true}
			}
			return {ok: false, error: res.error}
		},

		setCurrentUser(user) {
			this.currentUser = user
		},
		setList(list) {
			this.list = list
			this.listLoaded = true
		},
	}
})

// vim: set noet ts=4 sw=4:
