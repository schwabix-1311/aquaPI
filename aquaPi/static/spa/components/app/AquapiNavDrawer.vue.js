const AquapiNavDrawer = {
	template: `
		<v-navigation-drawer 
			v-model="navDrawerVisible" 
			:color="($vuetify.theme.dark ? $store.state.ui.colors.darkMode.bg.navDrawer : $store.state.ui.colors.lightMode.bg.navDrawer)"
			app
			dark
			fixed
			temporary
			:width="$store.state.ui.navigation.drawerWidth"
		>
			<v-list-item @click="$root.navigate({route: 'home'})">
				<v-list-item-content>
					<v-list-item-title class="text-h6">
						{{ $t('app.name') }}
					</v-list-item-title>
					<v-list-item-subtitle>
					{{ $t('app.subtitle') }}
					</v-list-item-subtitle>
				</v-list-item-content>
				<v-btn
					icon
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
				<v-list-item>
					<v-list-item-content>
						<v-list-item-title>
							<a href="/settings">(alte) Settings</a>
						</v-list-item-title>
					</v-list-item-content>
				</v-list-item>
			
				<v-list-item
					v-for="item in items"
					:key="item.name"
					:class="(item.route == $route.name ? 'current' : '')"
					link
					@click="$root.navigate(item)"
				>
					<v-list-item-icon class="mr-3">
						<v-icon v-if="item.icon">
							{{ item.icon }}
						</v-icon>
					</v-list-item-icon>
					<v-list-item-content>
						<v-list-item-title>
							{{ $t('pages.' + item.name + '.label') }}
						</v-list-item-title>
					</v-list-item-content>
				</v-list-item>

				<v-divider class="mb-1"></v-divider>

				<template v-if="authenticated">
					<v-list-item
						link
						@click="$store.dispatch('auth/logout')"
					>
						<v-list-item-icon class="mr-3">
							<v-icon>
								mdi-logout
							</v-icon>
						</v-list-item-icon>
						<v-list-item-content>
							<v-list-item-title>
								{{ $t('pages.logout.label') }}
							</v-list-item-title>
						</v-list-item-content>
					</v-list-item>
				</template>
				<template v-else>
					<v-list-item
						link
						@click="$root.navigate({route: 'login'})"
					>
						<v-list-item-icon class="mr-3">
							<v-icon>
								mdi-login
							</v-icon>
						</v-list-item-icon>
						<v-list-item-content>
							<v-list-item-title>
								{{ $t('pages.login.label') }}
							</v-list-item-title>
						</v-list-item-content>
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
		navDrawerVisible: {
			get() {
				return this.$store.getters['ui/isActiveDialog'](this.dialogName)
			},
			set(value) {
				let active = this.$store.getters['ui/isActiveDialog'](this.dialogName)
				if (value !== active) {
					if (value == true) {
						this.$store.dispatch('ui/showDialog', this.dialogName)
					} else {
						this.$store.dispatch('ui/hideDialog', this.dialogName)
					}
				}
			}
		},
		authenticated() {
			return this.$store.getters['auth/authenticated']
		},
	},
}

// export {AquapiNavDrawer}
Vue.component('AquapiNavDrawer', AquapiNavDrawer)

// vim: set noet ts=4 sw=4:
