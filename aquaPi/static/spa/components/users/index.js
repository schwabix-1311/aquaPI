import './comps.js'
import {registerGlobalComponent} from '../app/registry.js'

const AquapiUsers = {
	template: `
		<v-card elevation="0" tile>
			<aquapi-page-heading
				:heading="$t('pages.users.heading')"
				:icon="'mdi-account-multiple'"
				:buttons="[{icon: 'mdi-account-plus', action: onAdd}]"
			></aquapi-page-heading>

			<v-card-text>
				<v-row v-if="loading" justify="center">
					<v-col cols="12" class="text-center pa-10">
						<aquapi-loading-indicator></aquapi-loading-indicator>
					</v-col>
				</v-row>

				<v-data-table
					v-else
					:headers="headers"
					:items="users"
					item-key="id"
					disable-pagination
					hide-default-footer
				>
					<template #item.role="{ item }">
						<v-chip small :color="roleColor(item.role)" dark>{{ item.role }}</v-chip>
					</template>
					<template #item.actions="{ item }">
						<v-btn icon small @click="onEdit(item)" :title="$t('pages.config.edit')">
							<v-icon small>mdi-pencil</v-icon>
						</v-btn>
						<v-btn icon small @click="onDelete(item)" :title="$t('pages.config.delete')">
							<v-icon small>mdi-delete</v-icon>
						</v-btn>
					</template>
				</v-data-table>
			</v-card-text>

			<user-dialog
				v-model="dialogOpen"
				:edit-user="editingUser"
				@saved="onSaved"
			></user-dialog>
		</v-card>
	`,

	data() {
		return {
			loading: true,
			dialogOpen: false,
			editingUser: null,
		}
	},

	computed: {
		users() {
			return this.$store.getters['users/all']
		},
		currentUserId() {
			const user = this.$store.getters['users/currentUser']
			return user ? user.id : null
		},
		headers() {
			return [
				{text: this.$t('pages.users.username'), value: 'username'},
				{text: this.$t('pages.users.role'), value: 'role'},
				{text: '', value: 'actions', sortable: false, align: 'end'},
			]
		},
	},

	methods: {
		roleColor(role) {
			return {viewer: 'grey', operator: 'blue', admin: 'deep-orange'}[role] || 'grey'
		},
		onAdd() {
			this.editingUser = null
			this.dialogOpen = true
		},
		onEdit(user) {
			this.editingUser = user
			this.dialogOpen = true
		},
		onSaved() {
			this.editingUser = null
		},
		async onDelete(user) {
			const ok = await this.$confirm(this.$t('pages.users.confirmDelete', {name: user.username}))
			if (!ok) {
				return
			}
			const result = await this.$store.dispatch('users/remove', user.id)
			if (!result.ok) {
				await this.$alert(result.error)
			}
		},
		async loadUsers() {
			this.loading = true
			await this.$store.dispatch('users/fetchAll')
			this.loading = false
		},
	},

	mounted() {
		this.loadUsers()
	},
}

registerGlobalComponent('AquapiUsers', AquapiUsers)
export {AquapiUsers}

// vim: set noet ts=4 sw=4:
