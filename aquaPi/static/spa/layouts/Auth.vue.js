const AuthLayout = {
	template: `
		<v-container :class="($vuetify.theme.dark ? $store.state.ui.colors.darkMode.bg.app : $store.state.ui.colors.lightMode.bg.app)" fluid fill-height id="page-login">
			<v-layout align-center justify-center>
				<v-flex :style="{ 'max-width': '350px' }">
					<router-view name="default" class="view"></router-view>
				</v-flex>
			</v-layout>
		</v-container>
	`
}

export {AuthLayout};

// vim: set noet ts=4 sw=4:
