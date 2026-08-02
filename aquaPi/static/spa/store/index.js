import auth from './modules/auth.js'
import ui from './modules/ui.js'
import dashboard from './modules/dashboard.js'
import settings from './modules/settings.js'
import config from './modules/config.js'

export default Vuex.createStore({
	modules: {
		ui,
		auth,
		dashboard,
		settings,
		config
	},
	strict: false,
})

// vim: set noet ts=4 sw=4:
