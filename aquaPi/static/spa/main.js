import store from './store/index.js'
import router from './router/index.js'
import i18n from './i18n/index.js'
import App from './App.vue.js'
import {AQUAPI_EVENTS, EventBus} from './components/app/EventBus.js'
import {installGlobalComponents} from './components/app/registry.js'

const vuetify = Vuetify.createVuetify({
	icons: {
		defaultSet: 'mdi', // 'mdi' || 'mdiSvg' || 'md' || 'fa' || 'fa4' || 'faSvg'
	},
	theme: {
		defaultTheme: 'light',
		themes: {
			light: {
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
	methods: {
		toggleNavDrawer() {
			const dialogName = 'AquapiNavDrawer'
			let active = this.$store.getters['ui/isActiveDialog'](dialogName)
			if (active) {
				this.$store.dispatch('ui/hideDialog', dialogName)
			} else {
				this.$store.dispatch('ui/showDialog', dialogName)
			}
		},
		toggleDarkMode() {
			if (this.$vuetify.theme.dark) {
				this.$vuetify.theme.dark = false
				this.$store.dispatch('ui/setDarkMode', false)
			} else {
				this.$vuetify.theme.dark = true
				this.$store.dispatch('ui/setDarkMode', true)
			}
		},
		navigate(item) {
			if (item.route == this.$route.name) return
			this.$router.push({name: item.route})
		},

		initEventListeners() {
			EventBus.$on(AQUAPI_EVENTS.APP_LOADING, (value) => {
				this.$store.dispatch('ui/showAppLoader', value)
			})

			EventBus.$on(AQUAPI_EVENTS.AUTH_LOGGED_IN, () => {
				this.$store.dispatch('ui/hideDialog', 'AquapiLoginDialog')
				this.$store.dispatch('ui/hideDialog', 'AquapiNavDrawer')

				// TODO: adapt to final root (dashboard on home)
				this.$router.replace({name: 'home'})
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

	beforeMount() {
		EventBus.$emit(AQUAPI_EVENTS.APP_LOADING, true)

		// TODO: implement server side check ...
		// Check localStorage for authenticated user
		try {
			const itemUser = JSON.parse(window.localStorage.getItem('aquapi.user'))
			if (itemUser && itemUser.username) {
				this.$store.commit('auth/setUser', {username: itemUser.username})
			} else {
				this.$store.commit('auth/setUser', null)
			}
		} catch(e) {
			this.$store.commit('auth/setUser', null)
		}

		// Check localStorage for theme mode
		try {
			const itemTheme = window.localStorage.getItem('aquapi.theme')
			if (itemTheme) {
				this.$vuetify.theme.dark = (itemTheme == 'dark')
				this.$store.dispatch('ui/setDarkMode', (itemTheme == 'dark'))
			}
		} catch(e) {}
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

app.use(store)
app.use(router)
app.use(i18n)
app.use(vuetify)

installGlobalComponents(app)

app.mount('#app')

// vim: set noet ts=4 sw=4:
