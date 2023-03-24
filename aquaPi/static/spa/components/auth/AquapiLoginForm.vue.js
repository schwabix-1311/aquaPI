const AquapiLoginForm = {
	name: 'AquapiLoginForm',
	template: `
		<v-card>
			<v-form ref="form" v-model="valid" @submit.prevent="validate">
				<v-card-title>
					<h1 class="text-h5">{{ $t('auth.login.form.heading') }}</h1>
				</v-card-title>
				<v-card-text>
					<v-text-field
						:label="$t('auth.login.form.username.label')"
						prepend-icon="mdi-account"
						v-model="form.username"
						:rules="usernameRules"
						required
						:error-messages="errorMessages.email"
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
  `,

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
			errorMessages: {},
		};
	},

	methods: {
		cancelLogin() {
			this.$store.dispatch('ui/hideDialog', 'AquapiLoginDialog')
		},
		async login(payload) {
			await this.$store.dispatch('auth/login', payload)
		},
		async validate() {
			const vm = this
			if (vm.$refs.form.validate()) {
				vm.loading = true;
				// TODO: implement login action
				await this.login(this.form);
				let tmo = window.setTimeout(function(){
					vm.loading = false
					vm.active = false
				}, 3500)
			}
		},
	},
}

Vue.component('AquapiLoginForm', AquapiLoginForm)
export {AquapiLoginForm}
