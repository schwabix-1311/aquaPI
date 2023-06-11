import {AppFooComp} from '../comps.js';
// import {AquapiNavDrawer} from '../components/app/AquapiNavDrawer.vue.js'
// import {AquapiNavDrawer, AquapiTestComp} from '../components/app/index.js'
import '../components/app/index.js'
import {AquapiLoginDialog} from '../components/auth/AquapiLoginDialog.vue.js'
import {AQUAPI_EVENTS, EventBus} from '../components/app/EventBus.js';

const DefaultLayout = {
	components: {
		// AquapiNavDrawer,
		AquapiLoginDialog,
		AppFooComp,
		// AquapiTestComp
	},
	template: `
		<v-app id="aquaPi">
			<v-overlay :value="$store.getters['ui/appLoaderVisible']" :z-index="20" :opacity="$store.state.ui.overlay.opacity">
				<v-sheet :class="'rounded-circle pa-1 white'" elevation="6">
					<v-progress-circular
						indeterminate
						color="primary"
						size="100"
						width="6"
					>
						<div class="text-center" v-html="$t('app.loading.message')"></div>
					</v-progress-circular>
				</v-sheet>
			</v-overlay>

			<aquapi-nav-drawer :items="navItems"></aquapi-nav-drawer>

			<v-app-bar
				app
				:color="($vuetify.theme.dark ? $store.state.ui.colors.darkMode.bg.appBar : $store.state.ui.colors.lightMode.bg.appBar)"
				elevation="4"
			>
				<v-app-bar-nav-icon class="white--text" @click="$root.toggleNavDrawer"></v-app-bar-nav-icon>
				<v-toolbar-title class="white--text" style="cursor: pointer" @click="$root.navigate({route: 'home'})">
					<h1 class="text-h4 font-weight-normal">{{ $t('app.name') }}</h1>
				</v-toolbar-title>
				<v-spacer></v-spacer>

				<template v-if="authenticated">
					<v-sheet dark color="transparent" class="mr-3">
						<v-icon class="mr-1">mdi-account-circle-outline</v-icon>{{ username }}
					</v-sheet>
					<v-btn title="Logout" icon class="white--text" @click.stop="$store.dispatch('auth/logout')">
						<v-icon>mdi-logout</v-icon>
					</v-btn>
				</template>
				<template v-else>
					<v-btn title="Login" icon class="white--text" @click.stop="$store.dispatch('ui/showDialog', 'AquapiLoginDialog', true);">
						<v-icon>mdi-login</v-icon>
					</v-btn>
				</template>

				<v-btn icon class="white--text" @click="$root.toggleDarkMode">
					<v-icon>mdi-circle-half-full</v-icon>
				</v-btn>
			</v-app-bar>

			<v-main style="max-height: 100vh;">
				<v-container :fluid="containerFluid" class="pa-5">
					 <transition name="fade" mode="out-in" :duration="$store.state.ui.navigation.transitionDuration">
						<router-view name="default" class="view"></router-view>
					</transition>

					<router-view name="view_bottom" class="view-bottom"></router-view>
				</v-container>
			</v-main>

			<v-footer dark :class="($vuetify.theme.dark ? $store.state.ui.colors.darkMode.bg.footer : $store.state.ui.colors.lightMode.bg.footer)" app elevation="4">
				<app-foo-comp></app-foo-comp>
				<v-spacer></v-spacer>
				<v-icon ref="sse_signal" :color="sseSignalColor">{{ sseSignalIcon }}</v-icon>
			</v-footer>

			<aquapi-login-dialog></aquapi-login-dialog>
		</v-app>
	`,

	data: () => ({
		// navDrawerVisible: false,
		dialogLogin: false,
		sseSignalIcon: 'mdi-network-outline',
		sseSignalColor: 'grey darken-3',
	}),
	computed: {
		nodes() {
			return this.$store.getters['dashboard/nodes']
		},
		authenticated() {
			return this.$store.getters['auth/authenticated']
		},
		username() {
			return this.$store.getters['auth/username']
		},
		navItems() {
			// console.log('[layout Default] computed navItems, this', this)
			return [
				{
					name: 'home',
					icon: 'mdi-view-dashboard',
					route: 'home'
				},
				{
					name: 'settings',
					icon: 'mdi-tune',
					route: 'settings'
				},
				{
					name: 'config',
					icon: 'mdi-cog-outline',
					route: 'config'
				},
				{
					name: 'about',
					icon: 'mdi-information-outline',
					route: 'about'
				}
			]
		},
		containerFluid() {
			// TODO: maybe render container as 'fluid' (full viewport width) on all pages
			return ['home', 'dashboard'].includes(this.$route.name)
		}
	},

	methods: {
		hideAppLoader() {
			this.$store.dispatch('ui/showAppLoader', false)
		},
		showSSESignal() {
			const vm = this
			vm.sseSignalColor = 'light-green darken-2'
			// vm.sseSignalIcon = 'mdi-download-network'
			vm.sseSignalIcon = 'mdi-download-network-outline'
			let tmo = window.setTimeout(function(){
				vm.sseSignalColor = 'grey darken-3'
				vm.sseSignalIcon = 'mdi-network-outline'
				window.clearTimeout(tmo)
			}, 500)
		},
	},

	created() {
		EventBus.$on(AQUAPI_EVENTS.SSE_NODE_UPDATE, this.showSSESignal)
	},
	destroyed() {
		EventBus.$off(AQUAPI_EVENTS.SSE_NODE_UPDATE, this.showSSESignal)
	}
}

export {DefaultLayout};

// vim: set noet ts=4 sw=4:
