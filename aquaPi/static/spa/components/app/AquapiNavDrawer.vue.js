import {registerGlobalComponent} from './registry.js'
import {useUiStore} from '../../store/modules/ui.js'
import {useAuthStore} from '../../store/modules/auth.js'

const AquapiNavDrawer = {
	template: `
		<v-navigation-drawer 
			v-model="navDrawerVisible" 
			:color="($vuetify.theme.global.current.dark ? uiStore.colors.darkMode.bg.navDrawer : uiStore.colors.lightMode.bg.navDrawer)"
			app
			dark
			fixed
			temporary
			:width="uiStore.navigation.drawerWidth"
		>
			<v-list-item @click="$root.navigate({route: 'home'})">
				<v-list-item-title class="text-h6">
					{{ $t('app.name') }}
				</v-list-item-title>
				<v-list-item-subtitle>
				{{ $t('app.subtitle') }}
				</v-list-item-subtitle>
				<v-btn
					icon
					variant="text"
					@click.stop="navDrawerVisible = false"
				>
					<v-icon>mdi-chevron-left</v-icon>
				</v-btn>
			</v-list-item>

			<v-divider></v-divider>
			
			<v-list
				dense
				nav
			>
				<v-list-item
					v-for="item in items"
					:key="item.name"
					:class="(item.route == $route.name ? 'current' : '')"
					link
					@click="$root.navigate(item)"
				>
					<template #prepend>
						<v-icon v-if="item.icon" class="mr-3">
							{{ item.icon }}
						</v-icon>
					</template>
					<v-list-item-title>
						{{ $t('pages.' + item.name + '.label') }}
					</v-list-item-title>
				</v-list-item>

				<v-divider class="mb-1"></v-divider>

				<template v-if="authenticated">
					<v-list-item
						link
						@click="authStore.logout()"
					>
						<template #prepend>
							<v-icon class="mr-3">
								mdi-logout
							</v-icon>
						</template>
						<v-list-item-title>
							{{ $t('pages.logout.label') }}
						</v-list-item-title>
					</v-list-item>
				</template>
				<template v-else>
					<v-list-item
						link
						@click="$root.navigate({route: 'login'})"
					>
						<template #prepend>
							<v-icon class="mr-3">
								mdi-login
							</v-icon>
						</template>
						<v-list-item-title>
							{{ $t('pages.login.label') }}
						</v-list-item-title>
					</v-list-item>
				</template>
			</v-list>
		</v-navigation-drawer>
	`,
	props: ['items'],

	data() {
		return {
			dialogName: 'AquapiNavDrawer'
		}
	},

	computed: {
		uiStore() {
			return useUiStore()
		},
		authStore() {
			return useAuthStore()
		},
		navDrawerVisible: {
			get() {
				return this.uiStore.isActiveDialog(this.dialogName)
			},
			set(value) {
				let active = this.uiStore.isActiveDialog(this.dialogName)
				if (value !== active) {
					if (value == true) {
						this.uiStore.showDialog(this.dialogName)
					} else {
						this.uiStore.hideDialog(this.dialogName)
					}
				}
			}
		},
		authenticated() {
			return this.authStore.authenticated
		},
	},
}

// export {AquapiNavDrawer}
registerGlobalComponent('AquapiNavDrawer', AquapiNavDrawer)

// vim: set noet ts=4 sw=4:
