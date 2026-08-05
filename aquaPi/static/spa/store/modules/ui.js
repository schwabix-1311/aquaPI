import {EventBus, AQUAPI_EVENTS} from '../../components/app/EventBus.js';

export const useUiStore = Pinia.defineStore('ui', {
	state: () => ({
		appLoading: false,
		darkMode: false,
		locale: 'en',
		colors: {
			lightMode: {
				bg: {
					appBar: 'primary',
					// navDrawer: 'grey darken-3',
					navDrawer: '',
					// footer: 'blue-grey lighten-2',
					// footer: 'secondary',
					footer: '',
				}
			},
			darkMode: {
				bg: {
					appBar: 'primary',
					// navDrawer: 'grey darken-3',
					navDrawer: '',
					// footer: 'blue-grey lighten-2',
					// footer: 'secondary',
					footer: '',
				}
			}
		},
		navigation: {
			transitionDuration: 400,
			drawerWidth: 290,
		},
		overlay: {
			opacity: 0.75
		},
		activeDialogs: {
			AquapiLoginDialog: false,
		},
	}),

	getters: {
		appLoaderVisible: (state) => {
			return state.appLoading;
		},
		isActiveDialog: (state) => (dialog) => {
			let dialogs = state.activeDialogs
			if (dialogs[dialog] == undefined || dialogs[dialog] == null) {
				dialogs[dialog] = false
				state.activeDialogs = Object.assign({}, dialogs)
			}

			return state.activeDialogs[dialog]
		}
	},

	actions: {
		showAppLoader(value) {
			this.appLoading = value
		},
		setDarkMode(value) {
			this.darkMode = value
			try {
				window.localStorage.setItem('aquapi.theme', (this.darkMode ? 'dark' : 'light'))
			} catch(e) {}
		},
		setLocale(value) {
			this.locale = value
			try {
				window.localStorage.setItem('aquapi.locale', value)
			} catch(e) {}
		},
		showDialog(dialog, hideOthers=true) {
			if (hideOthers) this.hideAllDialogs(dialog)

			let dialogs = this.activeDialogs
			dialogs[dialog] = true
			this.activeDialogs = Object.assign({}, dialogs)
			EventBus.$emit(AQUAPI_EVENTS.DIALOG_OPENED, {id: dialog})
		},
		hideDialog(dialog) {
			let dialogs = this.activeDialogs
			dialogs[dialog] = false
			this.activeDialogs = Object.assign({}, dialogs)
			EventBus.$emit(AQUAPI_EVENTS.DIALOG_CLOSED, {id: dialog})
		},
		hideAllDialogs(except=null) {
			const dialogs = this.activeDialogs
			for (const [dialog, value] of Object.entries(dialogs)) {
				if (except && except == dialog) {
					continue
				}
				dialogs[dialog] = false
			}
			this.activeDialogs = Object.assign({}, dialogs)
		}
	}
})

// vim: set noet ts=4 sw=4:
