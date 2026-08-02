const state = () => ({
	list: [],
	listLoaded: false,
	currentUser: null,
})

const getters = {
	all: (state) => {
		return state.list
	},
	currentUser: (state) => {
		return state.currentUser
	},
	role: (state) => {
		return state.currentUser ? state.currentUser.role : null
	},
	isAdmin: (state) => {
		return !!state.currentUser && state.currentUser.role === 'admin'
	},
}

const actions = {
	async fetchCurrentUser({commit}) {
		try {
			const response = await fetch('/api/users/me', {
				method: 'get',
				mode: 'same-origin',
				cache: 'no-cache',
				headers: {
					'X-Requested-With': 'XMLHttpRequest',
					'Accept': 'application/json'
				},
			})

			if (response.status == 200) {
				const user = await response.json()
				commit('setCurrentUser', user)
				return user
			}
		} catch (e) {
			// not logged in (yet), or network error - keep currentUser null
		}
		commit('setCurrentUser', null)
		return null
	},

	async fetchAll({commit}) {
		const response = await fetch('/api/users/', {
			method: 'get',
			mode: 'same-origin',
			cache: 'no-cache',
			headers: {
				'X-Requested-With': 'XMLHttpRequest',
				'Accept': 'application/json'
			},
		})

		if (response.status == 200) {
			const users = await response.json()
			commit('setList', users)
			return users
		}
		return []
	},

	async create({dispatch}, payload) {
		try {
			const response = await fetch('/api/users/', {
				method: 'post',
				mode: 'same-origin',
				cache: 'no-cache',
				headers: {
					'X-Requested-With': 'XMLHttpRequest',
					'Accept': 'application/json',
					'Content-Type': 'application/json',
				},
				body: JSON.stringify(payload),
			})

			const body = await response.json().catch(() => null)

			if (response.status == 201) {
				await dispatch('fetchAll')
				return {ok: true, user: body}
			}
			return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
		} catch (e) {
			return {ok: false, error: e.message}
		}
	},

	async update({dispatch}, payload) {
		const {userId, changes} = payload
		try {
			const response = await fetch('/api/users/' + userId, {
				method: 'put',
				mode: 'same-origin',
				cache: 'no-cache',
				headers: {
					'X-Requested-With': 'XMLHttpRequest',
					'Accept': 'application/json',
					'Content-Type': 'application/json',
				},
				body: JSON.stringify(changes),
			})

			const body = await response.json().catch(() => null)

			if (response.status == 200) {
				await dispatch('fetchAll')
				return {ok: true, user: body}
			}
			return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
		} catch (e) {
			return {ok: false, error: e.message}
		}
	},

	async remove({dispatch}, userId) {
		try {
			const response = await fetch('/api/users/' + userId, {
				method: 'delete',
				mode: 'same-origin',
				cache: 'no-cache',
				headers: {
					'X-Requested-With': 'XMLHttpRequest',
					'Accept': 'application/json',
				},
			})

			if (response.status == 204) {
				await dispatch('fetchAll')
				return {ok: true}
			}
			const body = await response.json().catch(() => null)
			return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
		} catch (e) {
			return {ok: false, error: e.message}
		}
	},
}

const mutations = {
	setCurrentUser(state, user) {
		state.currentUser = user
	},
	setList(state, list) {
		state.list = list
		state.listLoaded = true
	},
}

export default {
	namespaced: true,
	state,
	getters,
	actions,
	mutations
}

// vim: set noet ts=4 sw=4:
