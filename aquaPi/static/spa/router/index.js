import {loadSfc} from '../sfc/loadSfc.js'

// Home/Config/Settings only wrap their respective `aquapi-dashboard` /
// `aquapi-config` / `aquapi-settings` tags, whose actual component
// definitions still live in these plain, eagerly-loaded `.js` modules
// (self-registering into the global component registry, see
// components/app/registry.js) - a `.vue` SFC's `<script>` can't `import`
// them directly (see the comment in sfc/loadSfc.js).
import '../components/app/index.js'
import '../components/dashboard/index.js'
import '../components/config/index.js'
import '../components/settings/index.js'
import '../components/users/index.js'
import {useUsersStore} from '../store/modules/users.js'

const routes = [
	{
		// TODO: maybe change /app to / when 'old app' is not used any longer
		// partly DONE: old app is now /home, and / redirects to /#/
		path: '/',
		// name: 'app',
		component: () => loadSfc('/static/spa/layouts/Default.vue'),
		children: [
			{
				path: '',
				name: 'home',
				alias: 'app',
				components: {
					default: () => loadSfc('/static/spa/pages/Home.vue')
				}
			},
			{
				path: 'settings',
				name: 'settings',
				components: {
					default: () => loadSfc('/static/spa/pages/Settings.vue')
				},
			},
			{
				path: 'config',
				name: 'config',
				components: {
					default: () => loadSfc('/static/spa/pages/Config.vue')
				},
			},
			{
				path: 'about',
				name: 'about',
				components: {
					default: () => loadSfc('/static/spa/pages/About.vue')
				},
			},
			{
				path: 'users',
				name: 'users',
				components: {
					default: () => loadSfc('/static/spa/pages/Users.vue')
				},
				beforeEnter: async (to, from, next) => {
					const usersStore = useUsersStore()
					if (!usersStore.currentUser) {
						await usersStore.fetchCurrentUser()
					}
					if (usersStore.isAdmin) {
						next()
					} else {
						next({name: 'home'})
					}
				},
			},
		]
	}
];

const router = VueRouter.createRouter({
	// TODO: maybe switch to createWebHistory(), when we do not need old URL paths any longer
	history: VueRouter.createWebHashHistory(),
	routes,
	scrollBehavior(to, from, savedPosition) {
		// Vuetify 3 no longer renders a `.v-main__wrap` child div (that was
		// a Vuetify 2 implementation detail) - see app.css's own comment on
		// `.v-main { overflow-y: auto }` - `.v-main` itself is now the
		// actual scroll container in this app.
		const mainWrapper = document.querySelector('.v-main')
		if (mainWrapper) {
			mainWrapper.scrollTop = 0
		}
		// vue-router 4 expects {left, top}, not {x, y}
		return {left: 0, top: 0}
	}
});

export default router;

// vim: set noet ts=4 sw=4:
