import {AquapiDummy} from '../components/app/index.js'
import {loadSfc} from '../sfc/loadSfc.js'

// Home/Config/Settings only wrap their respective `aquapi-dashboard` /
// `aquapi-config` / `aquapi-settings` tags, whose actual component
// definitions still live in these plain, eagerly-loaded `.js` modules
// (self-registering into the global component registry, see
// components/app/registry.js) - a `.vue` SFC's `<script>` can't `import`
// them directly (see the comment in sfc/loadSfc.js).
import '../components/dashboard/index.js'
import '../components/config/index.js'
import '../components/settings/index.js'
import '../components/users/index.js'
import store from '../store/index.js'

const routes = [
	{
		path: '/login',
		// redirect: 'login',
		component: () => loadSfc('/static/spa/layouts/Auth.vue'),
		// name: 'login',
		// component: DefaultLayout,
		children: [
			{
				path: '',
				name: 'login',
				components: {
					default: () => loadSfc('/static/spa/components/auth/AquapiLoginForm.vue')
				},
				// meta: {
				//	 title: i18n.t("routes.login"),
				// },
			},
		],
	},
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
					default: () => loadSfc('/static/spa/pages/Settings.vue'),
					view_bottom: AquapiDummy
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
					if (!store.getters['users/currentUser']) {
						await store.dispatch('users/fetchCurrentUser')
					}
					if (store.getters['users/isAdmin']) {
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
		const mainWrapper = document.querySelector('div.v-main__wrap')
		if (mainWrapper) {
			mainWrapper.scrollTop = 0
		}
		return {x: 0, y: 0}
	}
});

router.beforeEach((to, from, next) => {
	// TODO: implement authentication
	console.log('[router/index.js] ROUTER BEFORE EACH')

	// if (to.name !== 'login' && !isAuthenticated) {
	if (to.name !== 'login' && !(999 == 999)) {
		next({name: 'login'});
	} else {
		next();
	}
});

export default router;

// vim: set noet ts=4 sw=4:
