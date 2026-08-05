import './comps.js'
import {NODE_BOX_WIDTH, NODE_BOX_HEIGHT} from './comps.js'
import {registerGlobalComponent} from '../app/registry.js'
import {useDashboardStore} from '../../store/modules/dashboard.js'
import {useConfigStore} from '../../store/modules/config.js'

const CANVAS_MIN_WIDTH = 1200
const CANVAS_MIN_HEIGHT = 700

const AquapiConfig = {
	template: `
		<v-card elevation="0" tile>
			<aquapi-page-heading
				:heading="$t('pages.config.heading')"
				icon="mdi-cog-outline"
			></aquapi-page-heading>

			<v-card-text>
				<v-row justify="space-between" class="mb-2">
					<v-col cols="auto">
						<v-alert v-if="connectingFrom" dense text type="info" class="mb-0">
							{{ $t('pages.config.hintConnecting') }}
						</v-alert>
						<v-alert v-else-if="selectMode" dense text type="info" class="mb-0">
							{{ $t('pages.config.hintSelecting', {count: selectedIds.length}) }}
						</v-alert>
						<v-chip v-else-if="draftDirty" small color="warning" text-color="white">
							<v-icon left x-small>mdi-circle-medium</v-icon>
							{{ $t('pages.config.unsavedChanges') }}
						</v-chip>
					</v-col>
					<v-col cols="auto">
						<v-btn
							:color="selectMode ? 'secondary' : undefined"
							outlined class="mr-2"
							@click="toggleSelectMode"
						>
							<v-icon left small>mdi-checkbox-multiple-marked-outline</v-icon>
							{{ $t('pages.config.selectNodes') }}
						</v-btn>
						<v-btn outlined class="mr-2" @click="templatesDialogOpen = true">
							<v-icon left small>mdi-content-save-outline</v-icon>
							{{ $t('pages.config.templatesSnapshots') }}
						</v-btn>
						<v-btn color="primary" class="mr-2" @click="openAddDialog">
							<v-icon left small>mdi-plus</v-icon>
							{{ $t('pages.config.addNode') }}
						</v-btn>
						<v-btn text class="mr-2" :disabled="!draftDirty" @click="onDiscard">
							<v-icon left small>mdi-undo</v-icon>
							{{ $t('pages.config.discard') }}
						</v-btn>
						<v-btn color="success" :disabled="!draftDirty" :loading="saving" @click="onSave">
							<v-icon left small>mdi-content-save</v-icon>
							{{ $t('pages.config.saveChanges') }}
						</v-btn>
					</v-col>
				</v-row>

				<v-alert v-if="error" dense text type="error" dismissible @input="error = null">
					{{ error }}
				</v-alert>

				<v-row v-if="loading" justify="center">
					<v-col cols="12" class="text-center pa-10">
						<aquapi-loading-indicator></aquapi-loading-indicator>
					</v-col>
				</v-row>

				<v-alert v-else-if="!nodes.length" type="info" text>
					{{ $t('pages.config.hintEmpty') }}
				</v-alert>

				<div v-else class="config-canvas-wrapper">
					<div class="config-canvas" :style="canvasStyle">
						<config-connections
							:nodes="nodesForConnections"
							:width="canvasWidth"
							:height="canvasHeight"
							@remove="onRemoveEdge"
						></config-connections>

						<config-node-box
							v-for="node in nodes"
							:key="node.identifier"
							:node="node"
							:node-types="nodeTypes"
							:connecting="connectingFrom && connectingFrom.id === node.id"
							:selected="selectedIds.includes(node.id)"
							@select="onSelect"
							@connect="onConnectStart"
							@edit="openEditDialog"
							@delete="onDelete"
							@drag="onDrag"
							@drag-end="onDragEnd"
						></config-node-box>
					</div>
				</div>
			</v-card-text>

			<config-node-dialog
				v-model="dialogOpen"
				:node-types="nodeTypes"
				:nodes="nodes"
				:edit-node="editingNode"
			></config-node-dialog>

			<config-templates-dialog
				v-model="templatesDialogOpen"
				:selected-ids="selectedIds"
				@saved="onTemplateSaved"
			></config-templates-dialog>
		</v-card>
	`,

	data: function() {
		return {
			loading: true,
			saving: false,
			dialogOpen: false,
			templatesDialogOpen: false,
			editingNode: null,
			connectingFrom: null,
			selectMode: false,
			selectedIds: [],
			error: null,
			dragPositions: {},
		}
	},

	computed: {
		dashboardStore() {
			return useDashboardStore()
		},
		configStore() {
			return useConfigStore()
		},
		nodes: function() {
			return this.configStore.draftNodes
		},
		nodesById: function() {
			const map = {}
			this.nodes.forEach(n => { map[n.id] = n })
			return map
		},
		draftDirty: function() {
			return this.configStore.draftDirty
		},
		nodeTypes: function() {
			return this.configStore.nodeTypes
		},
		nodesForConnections: function() {
			// Overlay any in-progress drag position so connections visibly
			// follow a card while it's being dragged, not just after drop.
			return this.nodes.map(node => {
				const drag = this.dragPositions[node.id]
				if (!drag) return node
				return Object.assign({}, node, {pos_x: drag.x, pos_y: drag.y})
			})
		},
		canvasWidth: function() {
			const maxX = this.nodes.reduce((m, n) => Math.max(m, (n.pos_x || 0) + NODE_BOX_WIDTH + 60), 0)
			return Math.max(CANVAS_MIN_WIDTH, maxX)
		},
		canvasHeight: function() {
			const maxY = this.nodes.reduce((m, n) => Math.max(m, (n.pos_y || 0) + NODE_BOX_HEIGHT + 60), 0)
			return Math.max(CANVAS_MIN_HEIGHT, maxY)
		},
		canvasStyle: function() {
			return {width: this.canvasWidth + 'px', height: this.canvasHeight + 'px'}
		},
	},

	methods: {
		async loadAll() {
			this.loading = true
			await Promise.all([
				this.dashboardStore.fetchNodes(),
				this.configStore.fetchNodeTypes(),
			])
			this.configStore.initDraft()
			this.loading = false
		},

		async onSave() {
			this.saving = true
			try {
				const result = await this.configStore.saveDraft()
				if (!result.ok) {
					this.error = result.error
					this.$toast.error(result.error || this.$t('misc.toast.saveError'))
					return
				}
				this.configStore.initDraft()
				this.$toast.success(this.$t('misc.toast.saveSuccess'))
			} finally {
				this.saving = false
			}
		},

		async onDiscard() {
			const ok = await this.$confirm(this.$t('pages.config.confirmDiscard'))
			if (!ok) {
				return
			}
			this.configStore.initDraft()
			this.selectMode = false
			this.selectedIds = []
			this.$toast.success(this.$t('pages.config.changesDiscarded'))
		},

		async reinitDraft() {
			this.selectMode = false
			this.selectedIds = []
			this.configStore.initDraft()
		},

		openAddDialog: function() {
			this.connectingFrom = null
			this.editingNode = null
			this.dialogOpen = true
		},

		openEditDialog: function(node) {
			this.connectingFrom = null
			this.editingNode = node
			this.dialogOpen = true
		},

		toggleSelectMode: function() {
			this.selectMode = !this.selectMode
			this.selectedIds = []
		},

		onTemplateSaved: function() {
			this.reinitDraft()
		},

		onSelect: function(node) {
			if (this.selectMode) {
				const idx = this.selectedIds.indexOf(node.id)
				if (idx === -1) {
					this.selectedIds.push(node.id)
				} else {
					this.selectedIds.splice(idx, 1)
				}
				return
			}
			if (!this.connectingFrom) {
				return
			}
			if (this.connectingFrom.id === node.id) {
				this.connectingFrom = null
				return
			}
			this.connectTo(node)
		},

		onConnectStart: function(node) {
			this.connectingFrom = (this.connectingFrom && this.connectingFrom.id === node.id) ? null : node
		},

		connectTo(target) {
			const schema = this.nodeTypes[target.type]
			if (!schema || schema.receives === 'none') {
				this.error = target.name + ': ' + (this.$t('pages.config.errNameType'))
				this.connectingFrom = null
				return
			}

			let receives
			if (schema.receives === 'multi') {
				receives = (target.receives || []).slice()
				if (!receives.includes(this.connectingFrom.id)) {
					receives.push(this.connectingFrom.id)
				}
			} else {
				receives = [this.connectingFrom.id]
			}

			this.configStore.draftUpdateNode({
				nodeId: target.id,
				changes: {receives},
			})
			this.connectingFrom = null
		},

		onRemoveEdge(edge) {
			const target = this.nodesById[edge.targetId]
			if (!target) return
			const receives = (target.receives || []).filter(id => id !== edge.sourceId)
			this.configStore.draftUpdateNode({
				nodeId: target.id,
				changes: {receives},
			})
		},

		onDrag: function(payload) {
			// local-only override for live-tracking connection lines while
			// dragging; the draft store position is only committed on drag-end.
			this.dragPositions[payload.node.id] = {x: payload.x, y: payload.y}
		},

		onDragEnd(payload) {
			this.configStore.draftUpdateNode({
				nodeId: payload.node.id,
				changes: {pos_x: payload.x, pos_y: payload.y},
			})
			delete this.dragPositions[payload.node.id]
		},

		async onDelete(node) {
			const ok = await this.$confirm(this.$t('pages.config.confirmDelete', {name: node.name}))
			if (!ok) {
				return
			}
			this.configStore.draftDeleteNode({nodeId: node.id})
			if (this.selectMode) {
				this.selectedIds = this.selectedIds.filter(id => id !== node.id)
			}
		},
	},

	mounted: function() {
		this.loadAll()
	},
}

registerGlobalComponent('AquapiConfig', AquapiConfig)
export {AquapiConfig}

// vim: set noet ts=4 sw=4:
