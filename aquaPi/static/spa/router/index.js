import {AuthLayout} from '../layouts/Auth.vue.js'
import {DefaultLayout} from '../layouts/Default.vue.js'
import {AquapiDummy} from '../components/app/index.js'
import {loadSfc} from '../sfc/loadSfc.js'

import {Settings} from '../pages/Settings.vue.js'
import {Config} from '../pages/Config.vue.js'
import {Home} from '../pages/Home.vue.js'

const routes = [
	{
		path: '/login',
		// redirect: 'login',
		component: AuthLayout,
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
		component: DefaultLayout,
		children: [
			{
				path: '',
				name: 'home',
				alias: 'app',
				components: {
					default: Home
				}
			},
			{
				path: 'settings',
				name: 'settings',
				components: {
					default: Settings,
					view_bottom: AquapiDummy
				},
			},
			{
				path: 'config',
				name: 'config',
				components: {
					default: Config
				},
			},
			{
				path: 'about',
				name: 'about',
				components: {
					default: () => loadSfc('/static/spa/pages/About.vue')
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
