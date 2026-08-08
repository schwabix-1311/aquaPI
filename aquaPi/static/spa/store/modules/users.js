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
	},

	actions: {
		async fetchCurrentUser() {
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
					this.setCurrentUser(user)
					return user
				}
			} catch (e) {
				// not logged in (yet), or network error - keep currentUser null
			}
			this.setCurrentUser(null)
			return null
		},

		async fetchAll() {
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
				this.setList(users)
				return users
			}
			return []
		},

		async create(payload) {
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
					await this.fetchAll()
					return {ok: true, user: body}
				}
				return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
			} catch (e) {
				return {ok: false, error: e.message}
			}
		},

		async update(payload) {
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
					await this.fetchAll()
					return {ok: true, user: body}
				}
				return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
			} catch (e) {
				return {ok: false, error: e.message}
			}
		},

		async remove(userId) {
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
					await this.fetchAll()
					return {ok: true}
				}
				const body = await response.json().catch(() => null)
				return {ok: false, error: (body && body.error) || ('HTTP ' + response.status)}
			} catch (e) {
				return {ok: false, error: e.message}
			}
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
