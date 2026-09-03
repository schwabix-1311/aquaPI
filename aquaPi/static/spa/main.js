import pinia from './store/index.js'
import router from './router/index.js'
import i18n from './i18n/index.js'
import App from './App.vue.js'
import {AQUAPI_EVENTS, EventBus} from './components/app/EventBus.js'
import {installGlobalComponents} from './components/app/registry.js'
import {useUiStore} from './store/modules/ui.js'
import {useAuthStore} from './store/modules/auth.js'
import {useUsersStore} from './store/modules/users.js'

const vuetify = Vuetify.createVuetify({
	icons: {
		defaultSet: 'mdi', // 'mdi' || 'mdiSvg' || 'md' || 'fa' || 'fa4' || 'faSvg'
	},
	theme: {
		defaultTheme: 'light',
		themes: {
			light: {
				dark: false,
				colors: {
					primary: '#1976D2',
					secondary: '#424242',
					accent: '#82B1FF',
					error: '#FF5252',
					info: '#2196F3',
					success: '#4CAF50',
					warning: '#FFC107',
				},
			},
			dark: {
				dark: true,
				colors: {
					primary: '#1976D2',
					secondary: '#424242',
					accent: '#82B1FF',
					error: '#FF5252',
					info: '#2196F3',
					success: '#4CAF50',
					warning: '#FFC107',
				},
			},
		},
	},
})

// Vue.use(VueToast, {
// 	position: 'top',
// 	duration: 0
// });

const app = Vue.createApp({
	render() {
		return Vue.h(App)
	},
	computed: {
		uiStore() {
			return useUiStore()
		},
		authStore() {
			return useAuthStore()
		},
		usersStore() {
			return useUsersStore()
		},
	},
	methods: {
		toggleNavDrawer() {
			const dialogName = 'AquapiNavDrawer'
			let active = this.uiStore.isActiveDialog(dialogName)
			if (active) {
				this.uiStore.hideDialog(dialogName)
			} else {
				this.uiStore.showDialog(dialogName)
			}
		},
		toggleDarkMode() {
			if (this.$vuetify.theme.global.name === 'dark') {
				this.$vuetify.theme.change('light')
				this.uiStore.setDarkMode(false)
			} else {
				this.$vuetify.theme.change('dark')
				this.uiStore.setDarkMode(true)
			}
		},
		setLocale(locale) {
			i18n.global.locale.value = locale
			this.uiStore.setLocale(locale)
		},
		navigate(item) {
			if (item.route == this.$route.name) return
			this.$router.push({name: item.route})
		},

		initEventListeners() {
			EventBus.$on(AQUAPI_EVENTS.APP_LOADING, (value) => {
				this.uiStore.showAppLoader(value)
			})

			EventBus.$on(AQUAPI_EVENTS.AUTH_LOGGED_IN, () => {
				this.uiStore.hideDialog('AquapiLoginDialog')
				this.uiStore.hideDialog('AquapiNavDrawer')
				this.usersStore.fetchCurrentUser()

				// TODO: adapt to final root (dashboard on home)
				this.$router.replace({name: 'home'})
			})

			EventBus.$on(AQUAPI_EVENTS.AUTH_LOGGED_OUT, () => {
				// logout degrades back to the <anonymous> viewer (see
				// auth.py's before_request hook) - leave any page that
				// viewer role no longer has access to, same as the
				// beforeEnter guards would if navigated to fresh
				if (this.$route.name === 'wiring' || this.$route.name === 'parameters'
					|| this.$route.name === 'users') {
					this.$router.replace({name: 'home'})
				}
			})
		},

		detachEventListeners() {
			EventBus.$off(AQUAPI_EVENTS.APP_LOADING)
			EventBus.$off(AQUAPI_EVENTS.AUTH_LOGGED_IN)
			EventBus.$off(AQUAPI_EVENTS.AUTH_LOGGED_OUT)
		},
	},

	created() {
		this.initEventListeners()
	},

	async beforeMount() {
		EventBus.$emit(AQUAPI_EVENTS.APP_LOADING, true)

		// Resolve the real, server-side user (id/username/role) via the
		// authenticated Flask-Login session, so a browser refresh keeps
		// reflecting an already-existing session instead of defaulting
		// to logged-out until the next explicit login.
		const user = await this.usersStore.fetchCurrentUser()
		if (user && user.username) {
			this.authStore.setUser({username: user.username})
		} else {
			this.authStore.setUser(null)
		}

		// Check localStorage for theme mode
		try {
			const itemTheme = window.localStorage.getItem('aquapi.theme')
			if (itemTheme) {
				this.$vuetify.theme.change((itemTheme == 'dark') ? 'dark' : 'light')
				this.uiStore.setDarkMode((itemTheme == 'dark'))
			}
		} catch(e) {}

		// Check localStorage for a persisted language choice, otherwise
		// keep the navigator.language-derived default set in i18n/index.js
		try {
			const itemLocale = window.localStorage.getItem('aquapi.locale')
			if (itemLocale && Object.prototype.hasOwnProperty.call(i18n.global.messages.value, itemLocale)) {
				i18n.global.locale.value = itemLocale
			}
		} catch(e) {}
		this.uiStore.setLocale(i18n.global.locale.value)
	},

	beforeUnmount() {
		this.detachEventListeners()
	}
})

app.config.globalProperties.$confirm = function(message, options = {}) {
	return new Promise((resolve) => {
		EventBus.$emit(AQUAPI_EVENTS.CONFIRM_REQUESTED, {message, options, resolve})
	})
}
app.config.globalProperties.$alert = function(message, options = {}) {
	return new Promise((resolve) => {
		EventBus.$emit(AQUAPI_EVENTS.CONFIRM_REQUESTED, {
			message,
			options: Object.assign({}, options, {alertOnly: true}),
			resolve,
		})
	})
}
app.config.globalProperties.$toast = {
	success(message) {
		EventBus.$emit(AQUAPI_EVENTS.TOAST_REQUESTED, {message, color: 'success', timeout: 4000})
	},
	error(message) {
		EventBus.$emit(AQUAPI_EVENTS.TOAST_REQUESTED, {message, color: 'error', timeout: 6000})
	},
}

app.use(pinia)
app.use(router)
app.use(i18n)
app.use(vuetify)

installGlobalComponents(app)

app.mount('#app')

// vim: set noet ts=4 sw=4:
