import auth from './modules/auth.js'
import ui from './modules/ui.js'
import dashboard from './modules/dashboard.js'
import settings from './modules/settings.js'

Vue.use(Vuex)

export default new Vuex.Store({
	modules: {
		ui,
		auth,
		dashboard,
		settings
	},
	strict: false,
})

// vim: set noet ts=4 sw=4:
