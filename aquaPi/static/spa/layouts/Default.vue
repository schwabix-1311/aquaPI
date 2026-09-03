<template>
	<v-app id="aquaPi">
		<v-overlay :value="uiStore.appLoaderVisible" :z-index="20" :opacity="uiStore.overlay.opacity">
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
			:color="($vuetify.theme.global.current.dark ? uiStore.colors.darkMode.bg.appBar : uiStore.colors.lightMode.bg.appBar)"
			elevation="4"
		>
			<v-app-bar-nav-icon class="white--text" @click="$root.toggleNavDrawer"></v-app-bar-nav-icon>
			<v-toolbar-title class="white--text" style="cursor: pointer" @click="$root.navigate({route: 'home'})">
				<h1 class="text-h4 font-weight-normal">{{ $t('app.name') }}</h1>
			</v-toolbar-title>
			<v-spacer></v-spacer>

			<template v-if="authenticated && !isAnonymous">
				<v-sheet dark color="transparent" class="mr-3">
					<v-icon class="mr-1">mdi-account-circle-outline</v-icon>{{ username }}
				</v-sheet>
				<v-btn :title="$t('pages.logout.label')" icon variant="text" class="white--text" @click.stop="authStore.logout()">
					<v-icon>mdi-logout</v-icon>
				</v-btn>
			</template>
			<template v-else>
				<v-btn :title="$t('pages.login.label')" icon variant="text" class="white--text" @click.stop="uiStore.showDialog('AquapiLoginDialog')">
					<v-icon>mdi-login</v-icon>
				</v-btn>
			</template>

			<v-menu>
				<template #activator="{ props }">
					<v-btn icon class="white--text" v-bind="props" :title="$t('misc.language.label')">
						<v-icon>mdi-translate</v-icon>
					</v-btn>
				</template>
				<v-list>
					<v-list-item
						v-for="loc in availableLocales"
						:key="loc"
						:active="loc === currentLocale"
						@click="$root.setLocale(loc)"
					>
						<v-list-item-title>{{ $t('misc.language.' + loc) }}</v-list-item-title>
					</v-list-item>
				</v-list>
			</v-menu>

			<v-btn icon class="white--text" @click="$root.toggleDarkMode">
				<v-icon>mdi-circle-half-full</v-icon>
			</v-btn>
		</v-app-bar>

		<v-main>
			<v-container fluid class="pa-5">
				<router-view name="default" v-slot="{ Component }">
					<transition name="fade" mode="out-in" :duration="uiStore.navigation.transitionDuration">
						<component :is="Component" class="view"></component>
					</transition>
				</router-view>
			</v-container>
		</v-main>

		<v-footer dark :class="($vuetify.theme.global.current.dark ? uiStore.colors.darkMode.bg.footer : uiStore.colors.lightMode.bg.footer)" app elevation="4" style="position: fixed; bottom: 0; width: 100%; z-index: 1005;">
			<app-foo-comp></app-foo-comp>
			<v-spacer></v-spacer>
			<v-icon ref="sse_signal" :color="sseSignalColor">{{ sseSignalIcon }}</v-icon>
		</v-footer>

		<aquapi-login-dialog></aquapi-login-dialog>
		<aquapi-confirm-dialog></aquapi-confirm-dialog>
		<aquapi-toast></aquapi-toast>
	</v-app>
</template>

<script>
// Loaded via moduleCache (not a real relative import), since vue3-sfc-loader
// can't parse a plain .js file's own `import`/`export` statements - see
// the comment in aquaPi/static/spa/sfc/loadSfc.js for details.
import Vue from 'vue'
import {loadSfc} from 'sfc/loadSfc'
import {EventBus, AQUAPI_EVENTS} from 'app/EventBus'
import {AquapiConfirmDialog} from 'app/AquapiConfirmDialog'
import {AquapiToast} from 'app/AquapiToast'
import {AppFooComp} from 'app/comps'
import {i18n} from 'app/i18n'
import {useUiStore} from 'store/ui'
import {useAuthStore} from 'store/auth'
import {useDashboardStore} from 'store/dashboard'
import {useUsersStore} from 'store/users'

export default {
	name: 'DefaultLayout',

	components: {
		// A bare `() => loadSfc(...)` factory only auto-resolves as an async
		// component for Vue Router route components; plain `components:`
		// option entries need an explicit `Vue.defineAsyncComponent()` wrapper.
		AquapiLoginDialog: Vue.defineAsyncComponent(() => loadSfc('/static/spa/components/auth/AquapiLoginDialog.vue')),
		AquapiConfirmDialog,
		AquapiToast,
		AppFooComp,
	},

	data: () => ({
		dialogLogin: false,
		sseSignalIcon: 'mdi-network-outline',
		sseSignalColor: 'grey darken-3',
	}),
	computed: {
		uiStore() {
			return useUiStore()
		},
		authStore() {
			return useAuthStore()
		},
		dashboardStore() {
			return useDashboardStore()
		},
		usersStore() {
			return useUsersStore()
		},
		nodes() {
			return this.dashboardStore.nodes
		},
		authenticated() {
			return this.authStore.authenticated
		},
		username() {
			return this.authStore.username
		},
		// the reserved <anonymous> account is technically "authenticated"
		// (see auth.py's before_request hook), but nobody actually chose
		// to log in as it - the app bar should still offer the login icon,
		// not a logout button for an account nobody deliberately entered
		isAnonymous() {
			return this.usersStore.isAnonymous
		},
		navItems() {
			const items = [
				{
					name: 'home',
					icon: 'mdi-view-dashboard',
					route: 'home'
				},
			]
			if (this.usersStore.isOperatorOrAdmin) {
				items.push({
					// 'name' stays the pages.settings.* i18n key prefix
					// (a separate concern from the route identifier) -
					// only 'route' (the actual vue-router target) changed
					// when the route itself was renamed from 'settings'
					name: 'settings',
					icon: 'mdi-tune',
					route: 'parameters'
				})
			}
			if (this.usersStore.isAdmin) {
				items.push({
					// see the 'settings' item above - 'name' stays the
					// pages.config.* i18n prefix, only 'route' changed
					name: 'config',
					icon: 'mdi-cog-outline',
					route: 'wiring'
				})
				items.push({
					name: 'users',
					icon: 'mdi-account-multiple',
					route: 'users'
				})
			}
			items.push({
				name: 'about',
				icon: 'mdi-information-outline',
				route: 'about'
			})
			return items
		},
		availableLocales() {
			return Object.keys(i18n.global.messages.value)
		},
		currentLocale() {
			return i18n.global.locale.value
		}
	},

	methods: {
		hideAppLoader() {
			this.uiStore.showAppLoader(false)
		},
		showSSESignal() {
			const vm = this
			vm.sseSignalColor = 'light-green darken-2'
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
	unmounted() {
		EventBus.$off(AQUAPI_EVENTS.SSE_NODE_UPDATE, this.showSSESignal)
	}
}
</script>
