<template>
	<v-card>
		<v-card-title>
			<h1 class="text-h5">{{ $t(headingKey) }}</h1>
		</v-card-title>
		<v-window v-model="mode">
			<v-window-item value="login">
				<v-form ref="loginForm" v-model="valid" @submit.prevent="validate">
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

						<a href="#" @click.prevent="mode = 'request-reset'">
							{{ $t('auth.resetPassword.request.linkLabel') }}
						</a>
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
			</v-window-item>

			<v-window-item value="request-reset">
				<v-card-text>
					<v-alert v-if="resetSent" type="success" text dense class="mb-4">
						{{ $t('auth.resetPassword.request.sentHint') }}
					</v-alert>
					<template v-else>
						<div class="mb-3">{{ $t('auth.resetPassword.request.hint') }}</div>
						<v-alert v-if="resetError" type="error" text dense class="mb-4">
							{{ resetError }}
						</v-alert>
						<v-text-field
							:label="$t('auth.resetPassword.request.username.label')"
							prepend-icon="mdi-account"
							v-model="resetUsername"
							required
						></v-text-field>
					</template>
				</v-card-text>
				<v-card-actions>
					<v-spacer></v-spacer>
					<v-btn text color="primary" @click="mode = 'login'">
						{{ $t('auth.resetPassword.request.btnBack.label') }}
					</v-btn>
					<v-btn v-if="!resetSent"
						:loading="loading"
						color="primary"
						@click="submitRequestReset"
					>
						{{ $t('auth.resetPassword.request.btnSubmit.label') }}
					</v-btn>
				</v-card-actions>
			</v-window-item>

			<v-window-item value="confirm-reset">
				<v-card-text>
					<template v-if="checkingToken">
						<div class="text-center py-4">
							<aquapi-loading-indicator color="primary"></aquapi-loading-indicator>
						</div>
					</template>
					<template v-else-if="!tokenValid">
						<v-alert type="error" text dense class="mb-4">
							{{ $t('auth.resetPassword.confirm.invalidHint') }}
						</v-alert>
					</template>
					<template v-else>
						<v-alert v-if="resetError" type="error" text dense class="mb-4">
							{{ resetError }}
						</v-alert>
						<v-text-field
							:label="$t('auth.resetPassword.confirm.password.label')"
							prepend-icon="mdi-lock"
							type="password"
							v-model="newPassword"
							required
						></v-text-field>
						<v-text-field
							:label="$t('auth.resetPassword.confirm.password2.label')"
							prepend-icon="mdi-lock-check"
							type="password"
							v-model="newPassword2"
							required
						></v-text-field>
					</template>
				</v-card-text>
				<v-card-actions>
					<v-spacer></v-spacer>
					<v-btn v-if="!checkingToken && !tokenValid" text color="primary" @click="mode = 'request-reset'">
						{{ $t('auth.resetPassword.confirm.btnRequestNew.label') }}
					</v-btn>
					<v-btn v-else-if="!checkingToken" text color="primary" @click="mode = 'login'">
						{{ $t('auth.resetPassword.request.btnBack.label') }}
					</v-btn>
					<v-btn v-if="!checkingToken && tokenValid"
						:loading="loading"
						color="primary"
						@click="submitConfirmReset"
					>
						{{ $t('auth.resetPassword.confirm.btnSubmit.label') }}
					</v-btn>
				</v-card-actions>
			</v-window-item>
		</v-window>
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
			mode: useAuthStore().resetToken ? 'confirm-reset' : 'login',
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

			resetUsername: null,
			resetSent: false,
			resetError: null,

			checkingToken: false,
			tokenValid: false,
			newPassword: null,
			newPassword2: null,
		};
	},

	computed: {
		uiStore() {
			return useUiStore()
		},
		authStore() {
			return useAuthStore()
		},
		headingKey() {
			if (this.mode === 'request-reset' || this.mode === 'confirm-reset') {
				return this.mode === 'request-reset'
					? 'auth.resetPassword.request.heading'
					: 'auth.resetPassword.confirm.heading'
			}
			return 'auth.login.form.heading'
		},
	},

	watch: {
		mode(value) {
			if (value === 'confirm-reset') {
				this.checkToken()
			}
		},
	},

	created() {
		if (this.mode === 'confirm-reset') {
			this.checkToken()
		}
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
			if (vm.$refs.loginForm.validate()) {
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
		async submitRequestReset() {
			if (!this.resetUsername) return
			this.loading = true
			this.resetError = null
			const result = await this.authStore.requestPasswordReset(this.resetUsername)
			this.loading = false
			if (!result.ok) {
				this.resetError = result.error
				return
			}
			this.resetSent = true
		},
		async checkToken() {
			this.checkingToken = true
			this.tokenValid = await this.authStore.checkResetToken(this.authStore.resetToken)
			this.checkingToken = false
		},
		async submitConfirmReset() {
			if (!this.newPassword || this.newPassword !== this.newPassword2) {
				this.resetError = this.$t('auth.resetPassword.confirm.errors.mismatch')
				return
			}
			this.loading = true
			this.resetError = null
			const result = await this.authStore.confirmPasswordReset(
				this.authStore.resetToken, this.newPassword, this.newPassword2)
			this.loading = false
			if (!result.ok) {
				this.resetError = result.error
				return
			}
			this.$toast.success(this.$t('auth.resetPassword.confirm.successToast'))
			this.mode = 'login'
		},
	},
}
</script>
