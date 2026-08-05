<template>
	<v-card>
		<v-form ref="form" v-model="valid" @submit.prevent="validate">
			<v-card-title>
				<h1 class="text-h5">{{ $t('auth.login.form.heading') }}</h1>
			</v-card-title>
			<v-card-text>
				<v-alert v-if="loginError" type="error" text dense class="mb-4">
					{{ loginError }}
				</v-alert>

				<v-text-field
					:label="$t('auth.login.form.username.label')"
					prepend-icon="mdi-account"
					v-model="form.username"
					:rules="usernameRules"
					required
				></v-text-field>

				<v-text-field
					:label="$t('auth.login.form.password.label')"
					prepend-icon="mdi-lock"
					type="password"
					v-model="form.password"
					:rules="passwordRules"
					required
				></v-text-field>
			</v-card-text>
			<v-card-actions>
				<v-spacer></v-spacer>

				<v-btn v-if="addCancel"
					@click="cancelLogin"
					text
					color="primary"
					:disabled="loading"
				>
					{{ $t('auth.login.form.btnCancel.label') }}
				</v-btn>
				<v-btn
					:loading="loading"
					color="primary"
					type="submit"
				>
					{{ $t('auth.login.form.btnSubmit.label') }}
				</v-btn>
			</v-card-actions>
		</v-form>
	</v-card>
</template>

<script>
import {useUiStore} from 'store/ui'
import {useAuthStore} from 'store/auth'

export default {
	name: 'AquapiLoginForm',

	props: [
		'addCancel'
	],

	data() {
		return {
			valid: false,
			loading: false,
			form: {
				username: null,
				password: null,
			},
			usernameRules: [
				v => !!v || this.$t('auth.login.form.username.errors.empty')
			],
			passwordRules: [
				v => !!v || this.$t('auth.login.form.password.errors.empty')
			],
			loginError: null,
		};
	},

	computed: {
		uiStore() {
			return useUiStore()
		},
		authStore() {
			return useAuthStore()
		},
	},

	methods: {
		cancelLogin() {
			this.uiStore.hideDialog('AquapiLoginDialog')
		},
		async login(payload) {
			return await this.authStore.login(payload)
		},
		async validate() {
			const vm = this
			if (vm.$refs.form.validate()) {
				vm.loading = true
				vm.loginError = null
				const result = await this.login(this.form)
				vm.loading = false
				if (!result.ok) {
					vm.loginError = this.$t('auth.login.form.errors.invalid')
				}
				// on success, the login dialog is closed by the app-wide
				// AUTH_LOGGED_IN listener in main.js
			}
		},
	},
}
</script>
