import './comps.js'
import {NODE_BOX_WIDTH, NODE_BOX_HEIGHT} from './comps.js'

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
					</v-col>
					<v-col cols="auto">
						<v-btn color="primary" @click="openAddDialog">
							<v-icon left small>mdi-plus</v-icon>
							{{ $t('pages.config.addNode') }}
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
							:nodes="nodes"
							:width="canvasWidth"
							:height="canvasHeight"
							@remove="onRemoveEdge"
						></config-connections>

						<config-node-box
							v-for="node in nodes"
							:key="node.identifier"
							:node="node"
							:connecting="connectingFrom && connectingFrom.id === node.id"
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
		</v-card>
	`,

	data: function() {
		return {
			loading: true,
			dialogOpen: false,
			editingNode: null,
			connectingFrom: null,
			error: null,
		}
	},

	computed: {
		allNodes: function() {
			return this.$store.getters['dashboard/nodes']
		},
		nodes: function() {
			return Object.values(this.allNodes)
		},
		nodeTypes: function() {
			return this.$store.getters['config/nodeTypes']
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
				this.$store.dispatch('dashboard/fetchNodes'),
				this.$store.dispatch('config/fetchNodeTypes'),
			])
			this.loading = false
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

		onSelect: function(node) {
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

		async connectTo(target) {
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

			const result = await this.$store.dispatch('config/updateNode', {
				nodeId: target.id,
				changes: {receives},
			})
			if (!result.ok) {
				this.error = result.error
			}
			this.connectingFrom = null
		},

		async onRemoveEdge(edge) {
			const target = this.allNodes[edge.targetId]
			if (!target) return
			const receives = (target.receives || []).filter(id => id !== edge.sourceId)
			const result = await this.$store.dispatch('config/updateNode', {
				nodeId: target.id,
				changes: {receives},
			})
			if (!result.ok) {
				this.error = result.error
			}
		},

		onDrag: function(payload) {
			// local-only while dragging, position is committed on drag-end
		},

		async onDragEnd(payload) {
			const result = await this.$store.dispatch('config/updateNode', {
				nodeId: payload.node.id,
				changes: {pos_x: payload.x, pos_y: payload.y},
			})
			if (!result.ok) {
				this.error = result.error
			}
		},

		async onDelete(node) {
			if (!window.confirm(this.$t('pages.config.confirmDelete', {name: node.name}))) {
				return
			}
			const result = await this.$store.dispatch('config/deleteNode', {nodeId: node.id})
			if (!result.ok) {
				this.error = result.error
			}
		},
	},

	mounted: function() {
		this.loadAll()
	},
}

Vue.component('AquapiConfig', AquapiConfig)
export {AquapiConfig}

// vim: set noet ts=4 sw=4:
