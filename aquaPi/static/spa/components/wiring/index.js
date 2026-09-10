import './comps.js'
import {canConnect} from './wiringConnect.js'
import {NODE_BOX_WIDTH, NODE_BOX_HEIGHT} from './constants.js'
import {computeLayout} from './wiringLayout.js'
import {registerGlobalComponent} from '../app/registry.js'
import {useDashboardStore} from '../../store/modules/dashboard.js'
import {useWiringStore} from '../../store/modules/wiring.js'

const CANVAS_MIN_WIDTH = 1200
const CANVAS_MIN_HEIGHT = 700

const AquapiWiring = {
	template: `
		<v-card elevation="0" tile>
			<aquapi-page-heading
				:heading="$t('pages.wiring.heading')"
				icon="mdi-cog-outline"
			></aquapi-page-heading>

			<v-card-text>
				<v-row justify="space-between" class="mb-2">
					<v-col cols="auto">
						<v-alert v-if="selectedIds.length" dense text type="info" class="mb-0">
							{{ $t('pages.wiring.hintSelecting', {count: selectedIds.length}) }}
						</v-alert>
					</v-col>
					<v-col cols="auto">
						<v-btn color="primary" class="mr-2" @click="openTemplates(0)">
							<v-icon left small>mdi-shape-outline</v-icon>
							{{ $t('pages.wiring.templates') }}
						</v-btn>
						<v-btn outlined class="mr-2" @click="openAddDialog">
							<v-icon left small>mdi-plus</v-icon>
							{{ $t('pages.wiring.addNode') }}
						</v-btn>
						<v-btn outlined class="mr-2" @click="openTemplates(1)">
							<v-icon left small>mdi-backup-restore</v-icon>
							{{ $t('pages.wiring.snapshots') }}
						</v-btn>
						<v-btn outlined class="mr-2" @click="applyChainLayout">
							<v-icon left small>mdi-sitemap</v-icon>
							{{ $t('pages.wiring.autoArrange') }}
						</v-btn>
						<v-btn text class="mr-2" :disabled="!draftDirty" @click="onDiscard">
							<v-icon left small>mdi-undo</v-icon>
							{{ $t('pages.wiring.discard') }}
						</v-btn>
						<v-btn color="success" :disabled="!draftDirty" :loading="saving" @click="onSave">
							<v-icon left small>mdi-content-save</v-icon>
							{{ $t('pages.wiring.saveChanges') }}
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
					{{ $t('pages.wiring.hintEmpty') }}
				</v-alert>

				<div v-else class="wiring-canvas-wrapper">
					<div class="wiring-canvas" ref="canvas" :style="canvasStyle"
						@pointerdown.self="clearSelection">
						<wiring-connections
							:nodes="nodesForConnections"
							:node-types="nodeTypes"
							:width="canvasWidth"
							:height="canvasHeight"
							:preview="previewEdge"
							@remove="onRemoveEdge"
							@port-pointerdown="onConnectDragStart"
						></wiring-connections>

						<wiring-node-box
							v-for="node in nodes"
							:key="node.identifier"
							:node="node"
							:node-types="nodeTypes"
							:connecting="connectDrag && connectDrag.sourceNode.id === node.id"
							:drop-target="connectDrag && connectDrag.hoverTargetId === node.id ? (connectDrag.validDrop ? 'valid' : 'invalid') : null"
							:selected="selectedIds.includes(node.id)"
							@select="onSelect"
							@edit="openEditDialog"
							@delete="onDelete"
							@drag="onDrag"
							@drag-end="onDragEnd"
						></wiring-node-box>
					</div>
				</div>
			</v-card-text>

			<wiring-node-dialog
				v-model="dialogOpen"
				:node-types="nodeTypes"
				:nodes="nodes"
				:edit-node="editingNode"
			></wiring-node-dialog>

			<wiring-templates-dialog
				v-model="templatesDialogOpen"
				:initial-tab="templatesInitialTab"
				:selected-ids="selectedIds"
				@saved="onTemplateSaved"
			></wiring-templates-dialog>
		</v-card>
	`,

	data: function() {
		return {
			loading: true,
			saving: false,
			dialogOpen: false,
			templatesDialogOpen: false,
			templatesInitialTab: 0,
			editingNode: null,
			connectDrag: null,
			selectedIds: [],
			error: null,
			dragPositions: {},
		}
	},

	computed: {
		dashboardStore() {
			return useDashboardStore()
		},
		wiringStore() {
			return useWiringStore()
		},
		nodes: function() {
			return this.wiringStore.draftNodes
		},
		nodesById: function() {
			const map = {}
			this.nodes.forEach(n => { map[n.id] = n })
			return map
		},
		draftDirty: function() {
			return this.wiringStore.draftDirty
		},
		nodeTypes: function() {
			return this.wiringStore.nodeTypes
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
		previewEdge: function() {
			if (!this.connectDrag) return null
			const {x1, y1, x2, y2, port} = this.connectDrag
			return {x1, y1, x2, y2, arrowAtStart: port === 'input'}
		},
	},

	methods: {
		async loadAll() {
			this.loading = true
			await Promise.all([
				this.dashboardStore.fetchNodes(),
				this.wiringStore.fetchNodeTypes(),
			])
			this.wiringStore.initDraft()
			// nobody has ever positioned anything yet (fresh/default wiring) -
			// lay it out by chain instead of leaving every node stacked at (0,0)
			if (this.wiringStore.draftNodes.length > 0
				&& this.wiringStore.draftNodes.every(n => !n.pos_x && !n.pos_y)) {
				this.applyChainLayout()
			}
			this.loading = false
		},

		// Lay the whole graph out by chain (pure algorithm in
		// wiringLayout.js) and stage every resulting position into the
		// draft.
		applyChainLayout() {
			computeLayout(this.wiringStore.draftNodes).forEach((pos, nodeId) => {
				this.wiringStore.draftUpdateNode({nodeId, changes: pos})
			})
		},

		async onSave() {
			this.saving = true
			try {
				const result = await this.wiringStore.saveDraft()
				if (!result.ok) {
					this.error = result.error
					this.$toast.error(result.error || this.$t('misc.toast.saveError'))
					return
				}
				this.wiringStore.initDraft()
				this.$toast.success(this.$t('misc.toast.saveSuccess'))
			} finally {
				this.saving = false
			}
		},

		async onDiscard() {
			const ok = await this.$confirm(this.$t('pages.wiring.confirmDiscard'), {
				confirmLabel: this.$t('pages.wiring.discard'),
				confirmColor: 'error',
			})
			if (!ok) {
				return
			}
			this.wiringStore.initDraft()
			this.selectedIds = []
			this.$toast.success(this.$t('pages.wiring.changesDiscarded'))
		},

		async reinitDraft() {
			this.selectedIds = []
			this.wiringStore.initDraft()
		},

		openAddDialog: function() {
			this.connectDrag = null
			this.editingNode = null
			this.dialogOpen = true
		},

		openEditDialog: function(node) {
			this.connectDrag = null
			this.editingNode = node
			this.dialogOpen = true
		},

		clearSelection: function() {
			this.selectedIds = []
		},

		openTemplates: function(tab) {
			this.templatesInitialTab = tab
			this.templatesDialogOpen = true
		},

		onTemplateSaved: function() {
			this.reinitDraft()
		},

		// a single click / tap on a node toggles it in the selection set
		// (used by "save selection as template"); no mode, no button
		onSelect: function(node) {
			const idx = this.selectedIds.indexOf(node.id)
			if (idx === -1) {
				this.selectedIds.push(node.id)
			} else {
				this.selectedIds.splice(idx, 1)
			}
		},

		// Regardless of which port a drag starts from, it always resolves
		// to a (source, target) pair where target.receives is what
		// actually changes: dragging from a node's OUTPUT port means "the
		// node I drop on receives from me" (source = drag origin, target
		// = drop node); dragging from a node's INPUT port means "I
		// receive from the node I drop on" (source = drop node, target =
		// drag origin).
		onConnectDragStart(payload) {
			const {node, port, clientX, clientY} = payload
			const canvasEl = this.$refs.canvas
			if (!canvasEl) return
			const toLocal = (cx, cy) => {
				const rect = canvasEl.getBoundingClientRect()
				return {x: cx - rect.left, y: cy - rect.top}
			}
			const start = toLocal(clientX, clientY)
			const portX = port === 'output' ? (node.pos_x || 0) + NODE_BOX_WIDTH : (node.pos_x || 0)
			const portY = (node.pos_y || 0) + NODE_BOX_HEIGHT / 2

			this.connectDrag = {
				sourceNode: node, port,
				x1: portX, y1: portY,
				x2: start.x, y2: start.y,
				hoverTargetId: null, validDrop: false,
			}

			const onMove = (mv) => {
				const p = toLocal(mv.clientX, mv.clientY)
				this.connectDrag.x2 = p.x
				this.connectDrag.y2 = p.y
				const hover = this.nodes.find(n => n.id !== node.id
					&& p.x >= (n.pos_x || 0) && p.x <= (n.pos_x || 0) + NODE_BOX_WIDTH
					&& p.y >= (n.pos_y || 0) && p.y <= (n.pos_y || 0) + NODE_BOX_HEIGHT)
				this.connectDrag.hoverTargetId = hover ? hover.id : null
				this.connectDrag.validDrop = hover ? this.isValidConnection(node, port, hover) : false
			}
			const onUp = () => {
				document.removeEventListener('pointermove', onMove)
				document.removeEventListener('pointerup', onUp)
				document.removeEventListener('pointercancel', onUp)
				if (this.connectDrag && this.connectDrag.hoverTargetId && this.connectDrag.validDrop) {
					const hover = this.nodesById[this.connectDrag.hoverTargetId]
					if (port === 'output') {
						this.wireConnection(node, hover)
					} else {
						this.wireConnection(hover, node)
					}
				}
				this.connectDrag = null
			}
			document.addEventListener('pointermove', onMove)
			document.addEventListener('pointerup', onUp)
			document.addEventListener('pointercancel', onUp)
		},

		// a drag resolves to (source, target) by which port it started
		// from; canConnect() is the single rule both port dots and this
		// drop check go through
		isValidConnection(dragOriginNode, port, hoverNode) {
			const source = port === 'output' ? dragOriginNode : hoverNode
			const target = port === 'output' ? hoverNode : dragOriginNode
			return canConnect(source, target, this.nodeTypes)
		},

		wireConnection(source, target) {
			const schema = this.nodeTypes[target.type]
			if (!schema || schema.receives === 'none') return   // already validated, shouldn't happen

			let receives
			if (schema.receives === 'multi') {
				receives = (target.receives || []).slice()
				if (!receives.includes(source.id)) {
					receives.push(source.id)
				}
			} else {
				receives = [source.id]
			}

			this.wiringStore.draftUpdateNode({
				nodeId: target.id,
				changes: {receives},
			})
		},

		onRemoveEdge(edge) {
			const target = this.nodesById[edge.targetId]
			if (!target) return
			const receives = (target.receives || []).filter(id => id !== edge.sourceId)
			this.wiringStore.draftUpdateNode({
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
			this.wiringStore.draftUpdateNode({
				nodeId: payload.node.id,
				changes: {pos_x: payload.x, pos_y: payload.y},
			})
			delete this.dragPositions[payload.node.id]
		},

		async onDelete(node) {
			const ok = await this.$confirm(this.$t('pages.wiring.confirmDelete', {name: node.name}), {
				confirmLabel: this.$t('misc.actions.delete'),
				confirmColor: 'error',
			})
			if (!ok) {
				return
			}
			this.wiringStore.draftDeleteNode({nodeId: node.id})
			this.selectedIds = this.selectedIds.filter(id => id !== node.id)
		},
	},

	mounted: function() {
		this.loadAll()
	},
}

registerGlobalComponent('AquapiWiring', AquapiWiring)
export {AquapiWiring}

// vim: set noet ts=4 sw=4:
