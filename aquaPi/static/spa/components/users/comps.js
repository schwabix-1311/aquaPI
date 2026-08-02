import {registerGlobalComponent} from '../app/registry.js'

const UserDialog = {
	props: {
		value: {type: Boolean, default: false},
		editUser: {type: Object, default: null},
	},
	emits: ['input', 'saved'],
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
						v-model="form.password"
						:label="editUser ? $t('pages.users.newPassword') : $t('pages.users.password')"
						type="password"
						:hint="editUser ? $t('pages.users.passwordHintOptional') : ''"
						persistent-hint
						outlined dense
					></v-text-field>

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
			form: {username: '', password: '', role: 'viewer'},
			roles: ['viewer', 'operator', 'admin'],
			error: null,
			saving: false,
		}
	},
	computed: {
		show: {
			get() {
				return this.value
			},
			set(value) {
				this.$emit('input', value)
			}
		},
	},
	watch: {
		value(visible) {
			if (visible) {
				this.error = null
				this.form = this.editUser
					? {username: this.editUser.username, password: '', role: this.editUser.role}
					: {username: '', password: '', role: 'viewer'}
			}
		},
	},
	methods: {
		close() {
			this.show = false
		},
		async save() {
			this.error = null

			if (this.editUser) {
				const changes = {role: this.form.role}
				if (this.form.password) {
					changes.password = this.form.password
				}
				this.saving = true
				const result = await this.$store.dispatch('users/update', {userId: this.editUser.id, changes})
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
				const result = await this.$store.dispatch('users/create', {
					username: this.form.username,
					password: this.form.password,
					role: this.form.role,
				})
				this.saving = false
				if (!result.ok) {
					this.error = result.error
					return
				}
			}

			this.$emit('saved')
			this.show = false
		},
	},
}
registerGlobalComponent('UserDialog', UserDialog)

export {UserDialog}

// vim: set noet ts=4 sw=4:
