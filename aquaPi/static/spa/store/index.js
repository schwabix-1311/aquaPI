import auth from './modules/auth.js'
import ui from './modules/ui.js'
import dashboard from './modules/dashboard.js'

Vue.use(Vuex)

export default new Vuex.Store({
	modules: {
		ui,
		auth,
		dashboard
	},
	strict: false,
})

// vim: set noet ts=4 sw=4:
