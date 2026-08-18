import {registerGlobalComponent} from '../app/registry.js'
import {useConfigStore} from '../../store/modules/config.js'

const ConfigTemplatesDialog = {
	props: {
		modelValue: {type: Boolean, default: false},
		selectedIds: {type: Array, default: () => []},
	},
	template: `
		<v-dialog v-model="show" max-width="640" :persistent="restoring">
			<v-card class="position-relative">
				<v-overlay v-if="restoring" contained :model-value="true" :opacity="0.85" color="white">
					<div class="text-center black--text">
						<aquapi-loading-indicator color="primary"></aquapi-loading-indicator>
						<div class="mt-3">{{ $t('pages.config.restoringSnapshot') }}</div>
					</div>
				</v-overlay>
				<v-card-title>{{ $t('pages.config.templatesSnapshots') }}</v-card-title>
				<v-tabs v-model="tab">
					<v-tab>{{ $t('pages.config.templates') }}</v-tab>
					<v-tab>{{ $t('pages.config.snapshots') }}</v-tab>
				</v-tabs>
				<v-card-text>
					<v-alert v-if="error" type="error" dense text class="mb-3">{{ error }}</v-alert>

					<v-window v-model="tab">
						<v-window-item>
							<div class="d-flex align-center mt-3 mb-2">
								<v-text-field
									v-model="newTemplateName"
									:label="$t('pages.config.templateName')"
									dense outlined hide-details
									class="mr-2"
								></v-text-field>
								<v-btn
									color="primary"
									:disabled="!newTemplateName || !selectedIds.length"
									:loading="saving"
									@click="saveTemplate"
								>{{ $t('pages.config.saveSelection') }}</v-btn>
							</div>
							<div class="text-caption grey--text mb-3">
								{{ $t('pages.config.selectedCount', {count: selectedIds.length}) }}
							</div>

							<v-list dense v-if="templates.length">
								<v-list-item v-for="tpl in templates" :key="tpl.name">
									<v-list-item-title>{{ tpl.name }}</v-list-item-title>
									<v-list-item-subtitle>{{ tpl.descr }} ({{ tpl.node_count }})</v-list-item-subtitle>
									<template #append>
        <v-btn icon variant="text" color="grey-darken-1" @click="insertTemplate(tpl)" :title="$t('pages.config.insert')">
											<v-icon>mdi-tray-arrow-down</v-icon>
										</v-btn>
        <v-btn icon variant="text" color="grey-darken-1" @click="deleteTemplate(tpl)" :title="$t('pages.config.delete')">
											<v-icon>mdi-delete</v-icon>
										</v-btn>
									</template>
								</v-list-item>
							</v-list>
							<v-alert v-else type="info" text dense>{{ $t('pages.config.hintNoTemplates') }}</v-alert>
						</v-window-item>

						<v-window-item>
							<div class="d-flex align-center mt-3 mb-2">
								<v-text-field
									v-model="newSnapshotName"
									:label="$t('pages.config.snapshotName')"
									dense outlined hide-details
									class="mr-2"
								></v-text-field>
								<v-btn
									color="primary"
									:disabled="!newSnapshotName"
									:loading="saving"
									@click="saveSnapshot"
								>{{ $t('pages.config.saveSnapshot') }}</v-btn>
							</div>

							<v-list dense v-if="snapshots.length">
								<v-list-item v-for="snap in snapshots" :key="snap.name">
									<v-list-item-title>{{ snap.name }}</v-list-item-title>
									<v-list-item-subtitle>{{ snap.created_at }}</v-list-item-subtitle>
									<template #append>
        <v-btn icon variant="text" color="grey-darken-1" :disabled="restoring" @click="restoreSnapshot(snap)" :title="$t('pages.config.restore')">
											<v-icon>mdi-restore</v-icon>
										</v-btn>
        <v-btn icon variant="text" color="grey-darken-1" :disabled="restoring" @click="deleteSnapshot(snap)" :title="$t('pages.config.delete')">
											<v-icon>mdi-delete</v-icon>
										</v-btn>
									</template>
								</v-list-item>
							</v-list>
							<v-alert v-else type="info" text dense>{{ $t('pages.config.hintNoSnapshots') }}</v-alert>
						</v-window-item>
					</v-window>
				</v-card-text>
				<v-card-actions>
					<v-spacer></v-spacer>
					<v-btn text @click="show = false">{{ $t('pages.config.close') }}</v-btn>
				</v-card-actions>
			</v-card>
		</v-dialog>
	`,
	data: function() {
		return {
			tab: 0,
			newTemplateName: '',
			newSnapshotName: '',
			saving: false,
			restoring: false,
			error: null,
		}
	},
	computed: {
		configStore() {
			return useConfigStore()
		},
		show: {
			get: function() { return this.modelValue },
			set: function(val) { this.$emit('update:modelValue', val) },
		},
		templates: function() {
			return this.configStore.templates
		},
		snapshots: function() {
			return this.configStore.snapshots
		},
	},
	watch: {
		modelValue: function(val) {
			if (val) {
				this.error = null
				this.configStore.fetchTemplates()
				this.configStore.fetchSnapshots()
			}
		},
	},
	methods: {
		async saveTemplate() {
			this.saving = true
			try {
				const result = await this.configStore.createTemplate({
					name: this.newTemplateName,
					node_ids: this.selectedIds,
				})
				if (result.ok) {
					this.newTemplateName = ''
					this.$toast.success(this.$t('misc.toast.saveSuccess'))
					this.$emit('saved')
				} else {
					this.error = result.error
					this.$toast.error(result.error || this.$t('misc.toast.saveError'))
				}
			} finally {
				this.saving = false
			}
		},
		async insertTemplate(tpl) {
			const result = await this.configStore.insertTemplate({name: tpl.name})
			if (!result.ok) {
				this.error = result.error
				this.$toast.error(result.error || this.$t('misc.toast.saveError'))
			} else {
				this.$toast.success(this.$t('misc.toast.saveSuccess'))
				this.show = false
				this.$emit('saved')
			}
		},
		async deleteTemplate(tpl) {
			const ok = await this.$confirm(this.$t('pages.config.confirmDeleteTemplate', {name: tpl.name}), {
				confirmLabel: this.$t('pages.config.delete'),
				confirmColor: 'error',
			})
			if (!ok) {
				return
			}
			const result = await this.configStore.deleteTemplate({name: tpl.name})
			if (!result.ok) {
				this.error = result.error
				this.$toast.error(result.error || this.$t('misc.toast.deleteError'))
			} else {
				this.$toast.success(this.$t('misc.toast.deleteSuccess'))
			}
		},
		async saveSnapshot() {
			this.saving = true
			try {
				const result = await this.configStore.createSnapshot({name: this.newSnapshotName})
				if (result.ok) {
					this.newSnapshotName = ''
					this.$toast.success(this.$t('misc.toast.saveSuccess'))
				} else {
					this.error = result.error
					this.$toast.error(result.error || this.$t('misc.toast.saveError'))
				}
			} finally {
				this.saving = false
			}
		},
		async restoreSnapshot(snap) {
			const ok = await this.$confirm(this.$t('pages.config.confirmRestoreSnapshot', {name: snap.name}), {
				confirmLabel: this.$t('pages.config.restore'),
				confirmColor: 'error',
			})
			if (!ok) {
				return
			}
			this.restoring = true
			try {
				const result = await this.configStore.restoreSnapshot({name: snap.name})
				if (!result.ok) {
					this.error = result.error
					this.$toast.error(result.error || this.$t('misc.toast.saveError'))
				} else {
					this.$toast.success(this.$t('misc.toast.saveSuccess'))
					this.show = false
					this.$emit('saved')
				}
			} finally {
				this.restoring = false
			}
		},
		async deleteSnapshot(snap) {
			const ok = await this.$confirm(this.$t('pages.config.confirmDeleteSnapshot', {name: snap.name}), {
				confirmLabel: this.$t('pages.config.delete'),
				confirmColor: 'error',
			})
			if (!ok) {
				return
			}
			const result = await this.configStore.deleteSnapshot({name: snap.name})
			if (!result.ok) {
				this.error = result.error
				this.$toast.error(result.error || this.$t('misc.toast.deleteError'))
			} else {
				this.$toast.success(this.$t('misc.toast.deleteSuccess'))
			}
		},
	},
}
registerGlobalComponent('ConfigTemplatesDialog', ConfigTemplatesDialog)

// vim: set noet ts=4 sw=4:
