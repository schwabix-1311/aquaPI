import {registerGlobalComponent} from '../app/registry.js'
import {useUsersStore} from '../../store/modules/users.js'

const UserDialog = {
	props: {
		modelValue: {type: Boolean, default: false},
		editUser: {type: Object, default: null},
	},
	emits: ['update:modelValue', 'saved'],
	template: `
		<v-dialog v-model="show" max-width="480" persistent>
			<v-card>
				<v-card-title>
					{{ editUser ? $t('pages.users.editUser') : $t('pages.users.addUser') }}
				</v-card-title>
				<v-card-text>
					<v-alert v-if="error" type="error" dense text class="mb-3">{{ error }}</v-alert>

					<v-text-field
						v-if="!editUser"
						v-model="form.username"
						:label="$t('pages.users.username')"
						outlined dense
					></v-text-field>

					<v-text-field
						v-model="form.email"
						:label="$t('pages.users.email')"
						:hint="isAnonymous ? $t('pages.users.anonymousFieldDisabledHint') : $t('pages.users.emailHint')"
						:disabled="isAnonymous"
						persistent-hint
						outlined dense
						class="mb-2"
					></v-text-field>

					<v-text-field
						v-model="form.password"
						:label="editUser ? $t('pages.users.newPassword') : $t('pages.users.password')"
						:type="passwordVisible ? 'text' : 'password'"
						:hint="isAnonymous ? $t('pages.users.anonymousFieldDisabledHint') : (editUser ? $t('pages.users.passwordHintOptional') : '')"
						:disabled="isAnonymous"
						persistent-hint
						outlined dense
					>
						<template #append-inner>
							<v-icon
								:title="$t('pages.users.revealPassword')"
								class="mr-1"
								@click="passwordVisible = !passwordVisible"
							>{{ passwordVisible ? 'mdi-eye-off' : 'mdi-eye' }}</v-icon>
							<v-icon
								v-if="!isAnonymous"
								:title="$t('pages.users.suggestPassword')"
								@click="suggestPassword"
							>mdi-dice-5</v-icon>
						</template>
					</v-text-field>

					<v-select
						v-model="form.role"
						:items="roles"
						:label="$t('pages.users.role')"
						outlined dense
					></v-select>
				</v-card-text>
				<v-card-actions>
					<v-spacer></v-spacer>
					<v-btn text @click="close">{{ $t('pages.config.cancel') }}</v-btn>
					<v-btn color="primary" @click="save" :loading="saving">{{ $t('pages.config.save') }}</v-btn>
				</v-card-actions>
			</v-card>
		</v-dialog>
	`,
	data() {
		return {
			form: {username: '', email: '', password: '', role: 'viewer'},
			roles: ['viewer', 'operator', 'admin'],
			error: null,
			saving: false,
			passwordVisible: false,
		}
	},
	computed: {
		usersStore() {
			return useUsersStore()
		},
		isAnonymous() {
			return !!(this.editUser && this.editUser.is_anonymous)
		},
		show: {
			get() {
				return this.modelValue
			},
			set(value) {
				this.$emit('update:modelValue', value)
			}
		},
	},
	watch: {
		modelValue(visible) {
			if (visible) {
				this.error = null
				this.passwordVisible = false
				this.form = this.editUser
					? {username: this.editUser.username, email: this.editUser.email || '', password: '', role: this.editUser.role}
					: {username: '', email: '', password: '', role: 'viewer'}
				if (!this.editUser) {
					this.suggestPassword()
				}
			}
		},
	},
	methods: {
		close() {
			this.show = false
		},
		async suggestPassword() {
			const password = await this.usersStore.suggestPassword()
			if (password) {
				this.form.password = password
			}
		},
		async save() {
			this.error = null

			if (this.editUser && this.editUser.is_anonymous && this.form.role !== 'viewer') {
				const confirmed = await this.$confirm(
					this.$t('pages.users.confirmAnonymousRoleChange'),
					{confirmColor: 'warning'}
				)
				if (!confirmed) {
					return
				}
			}

			let result

			if (this.editUser) {
				const changes = {role: this.form.role, email: this.form.email || null}
				if (this.form.password) {
					changes.password = this.form.password
				}
				this.saving = true
				result = await this.usersStore.update({userId: this.editUser.id, changes})
				this.saving = false
				if (!result.ok) {
					this.error = result.error
					return
				}
			} else {
				if (!this.form.username || !this.form.password) {
					this.error = this.$t('pages.users.errUsernamePassword')
					return
				}
				this.saving = true
				result = await this.usersStore.create({
					username: this.form.username,
					email: this.form.email || null,
					password: this.form.password,
					role: this.form.role,
				})
				this.saving = false
				if (!result.ok) {
					this.error = result.error
					return
				}
			}

			const delivery = result.user && result.user.password_delivery
			if (delivery === 'email') {
				this.$toast.success(this.$t('pages.users.passwordSentEmail', {email: this.form.email}))
			} else if (delivery === 'log') {
				this.$toast.success(this.$t('pages.users.passwordSentLog'))
			} else {
				this.$toast.success(this.$t('misc.toast.saveSuccess'))
			}
			this.$emit('saved')
			this.show = false
		},
	},
}
registerGlobalComponent('UserDialog', UserDialog)

export {UserDialog}

// vim: set noet ts=4 sw=4:
