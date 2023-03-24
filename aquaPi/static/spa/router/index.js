import {AuthLayout} from '../layouts/Auth.vue.js'
import {DefaultLayout} from '../layouts/Default.vue.js'
import {AquapiLoginForm} from '../components/auth/AquapiLoginForm.vue.js'
import {AquapiDummy} from '../components/app/index.js'

import {Settings} from '../pages/Settings.vue.js'
import {Config} from '../pages/Config.vue.js'
import {Home} from '../pages/Home.vue.js'
import {About} from '../pages/About.vue.js'

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
					default: AquapiLoginForm
				},
				// meta: {
				//   title: i18n.t("routes.login"),
				// },
			},
		],
	},
	{
		// TODO: maybe change /app to / when 'old app' is not use any longer
		path: '/app',
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
					default: About
				},
			},
		]
	}
];

const router = new VueRouter({
	// TODO: maybe switch to mode 'history', when we do not need old URL paths any longer
	mode: 'hash', //'history',
	// base: process.env.BASE_URL,
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
	// console.log('... to:')
	// console.log(to)
	// console.log('... from:')
	// console.log(from)
	// console.log('this:')
	// console.log(this)

	// if (to.name !== 'login' && !isAuthenticated) {
	if (to.name !== 'login' && !(999 == 999)) {
		next({name: 'login'});
	} else {
		next();
	}
});

export default router;