import {EventBus, AQUAPI_EVENTS} from '../../components/app/EventBus.js';

const state = () => ({
	appLoading: false,
	darkMode: false,
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
})

const getters = {
	darkMode: (state) => {
		return state.darkMode
	},
	appLoaderVisible: (state, getters) => {
		return state.appLoading;
	},
	isActiveDialog: (state, getters) => (dialog) => {
		let dialogs = state.activeDialogs
		if (dialogs[dialog] == undefined || dialogs[dialog] == null) {
			dialogs[dialog] = false
			state.activeDialogs = Object.assign({}, dialogs)
		}

		return state.activeDialogs[dialog]
	}
}

const actions = {
	showAppLoader(context, value) {
		context.state.appLoading = value
	},
	setDarkMode(context, value) {
		context.state.darkMode = value
		try {
			window.localStorage.setItem('aquapi.theme', (context.state.darkMode ? 'dark' : 'light'))
		} catch(e) {}
	},
	showDialog(context, dialog, hideOthers=true) {
		if (hideOthers) context.dispatch('hideAllDialogs', dialog)

		let dialogs = context.state.activeDialogs
		dialogs[dialog] = true
		context.state.activeDialogs = Object.assign({}, dialogs)
		EventBus.$emit(AQUAPI_EVENTS.DIALOG_OPENED, {id: dialog})
	},
	hideDialog(context, dialog) {
		let dialogs = context.state.activeDialogs
		dialogs[dialog] = false
		context.state.activeDialogs = Object.assign({}, dialogs)
		EventBus.$emit(AQUAPI_EVENTS.DIALOG_CLOSED, {id: dialog})
	},
	hideAllDialogs(context, except=null) {
		const dialogs = context.state.activeDialogs
		for (const [dialog, value] of Object.entries(dialogs)) {
			if (except && except == dialog) {
				continue
			}
			dialogs[dialog] = false
		}
		context.state.activeDialogs = Object.assign({}, dialogs)
	}
}

const mutations = {
}

export default {
	namespaced: true,
	state,
	getters,
	actions,
	mutations
}

// vim: set noet ts=4 sw=4:
