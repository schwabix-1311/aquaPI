import './comps.js'
import {NODE_BOX_WIDTH, NODE_BOX_HEIGHT} from './comps.js'
import {registerGlobalComponent} from '../app/registry.js'
import {useDashboardStore} from '../../store/modules/dashboard.js'
import {useConfigStore} from '../../store/modules/config.js'
import {isRoot, isHistOrAlert, descendants} from '../settings/chains.js'

const CANVAS_MIN_WIDTH = 1200
const CANVAS_MIN_HEIGHT = 700
const LAYOUT_COL_GAP = 70
const LAYOUT_ROW_GAP = 50

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
						<v-btn outlined class="mr-2" @click="applyChainLayout">
							<v-icon left small>mdi-sitemap</v-icon>
							{{ $t('pages.config.autoArrange') }}
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
			// nobody has ever positioned anything yet (fresh/default topology) -
			// lay it out by chain instead of leaving every node stacked at (0,0)
			if (this.configStore.draftNodes.length > 0
				&& this.configStore.draftNodes.every(n => !n.pos_x && !n.pos_y)) {
				this.applyChainLayout()
			}
			this.loading = false
		},

		// One row per chain (or standalone node); within a chain, column =
		// depth from its root so pipeline stages line up vertically, and a
		// node's first (real, non-History/Alert) listener continues its own
		// row while every further listener fans out to a new row beneath -
		// keeps sibling branches from overlapping in the same row.
		applyChainLayout() {
			const nodes = this.configStore.draftNodes
			const byId = {}
			nodes.forEach(n => { byId[n.id] = n })

			const positions = new Map()
			const placed = new Set()
			const usedCells = new Set()   // 'row:col' - collision guard, since
			                               // History/Alert placement below can
			                               // reuse an already-claimed row
			let nextRow = 0

			// bumps row down (same col) until free, so two nodes can never
			// land on the exact same cell; returns the row actually used
			const place = (nodeId, row, col) => {
				while (usedCells.has(row + ':' + col)) row++
				usedCells.add(row + ':' + col)
				positions.set(nodeId, {row, col})
				placed.add(nodeId)
				return row
			}

			// like place(), but bumps the COLUMN instead on a collision - for
			// History/Alert sinks, which have no listeners of their own, so
			// nudging one a slot further right is harmless. Bumping their ROW
			// instead (like place()) is a real bug: a column can be legitimately
			// reused by many unrelated chains at different rows (e.g. each
			// happens to be exactly deep enough to reach that same column), so
			// row-bumping can march a sink down through many rows that have
			// nothing to do with its own source before finding a gap - dragging
			// it far away even when fed by a node in row 0.
			const placeSink = (nodeId, row, col) => {
				while (usedCells.has(row + ':' + col)) col++
				usedCells.add(row + ':' + col)
				positions.set(nodeId, {row, col})
				placed.add(nodeId)
			}

			// Pass 1: real chain roots (empty/wildcard receives) - column =
			// depth from root. History/Alert nodes are NOT included here even
			// though isRoot() treats them as roots too (that's grouping
			// semantics for /settings, where they always get their own card) -
			// spatially they're sinks, not chain starts, handled in Pass 2
			// below once every real node has its final position.
			nodes.filter(n => isRoot(n) && !isHistOrAlert(n)).forEach(root => {
				if (placed.has(root.id)) return
				const tree = descendants(root, byId)
				place(root.id, nextRow, 0)
				const endRow = tree.length
					? this.assignRows(tree, 1, nextRow, positions, placed, usedCells)
					: nextRow + 1
				nextRow = Math.max(endRow, nextRow + 1)
			})

			// Pass 2: History/Alert sinks. Every real node is positioned by
			// now, so each one just drops in relative to its own (fully
			// resolved) sources - no need to track "is this one ready yet"
			// during Pass 1, and it naturally handles a sink fed by several
			// different chains too, since all of them are already placed.
			// row = the highest (bottom-most) row among its sources, so it
			// lands right below whatever it's watching instead of many rows
			// further down; col = one past their rightmost column, instead of
			// column 0 - pinning it to column 0 like a real root previously
			// sent its incoming connection's target-side trunk stub
			// (targetTrunkX = pos_x - CONNECTION_STUB) to a negative x, off
			// the left edge of the canvas and invisible. Falls back to its
			// own fresh row/col 0 if nothing resolves (e.g. only `'*'`, a
			// missing id, or no receives at all).
			nodes.filter(isHistOrAlert).forEach(node => {
				const sourcePositions = (node.receives || [])
					.map(id => positions.get(id))
					.filter(Boolean)
				if (sourcePositions.length) {
					const row = Math.max(...sourcePositions.map(p => p.row))
					const col = Math.max(...sourcePositions.map(p => p.col)) + 1
					placeSink(node.id, row, col)
				} else {
					placeSink(node.id, nextRow, 0)
					nextRow++
				}
			})

			// orphaned edge case (e.g. a receives-cycle with no root) - still
			// give any leftover node its own row rather than skipping it
			nodes.forEach(node => {
				if (placed.has(node.id)) return
				nextRow = place(node.id, nextRow, 0) + 1
			})

			positions.forEach((pos, nodeId) => {
				this.configStore.draftUpdateNode({
					nodeId,
					changes: {
						pos_x: pos.col * (NODE_BOX_WIDTH + LAYOUT_COL_GAP),
						pos_y: pos.row * (NODE_BOX_HEIGHT + LAYOUT_ROW_GAP),
					},
				})
			})
		},

		// entries: descendants()'s [{node, children}] tree at this depth;
		// returns the next free row after placing this whole subtree
		assignRows(entries, depth, startRow, positions, placed, usedCells) {
			let row = startRow
			entries.forEach(entry => {
				const nodeRow = row
				row = entry.children.length
					? this.assignRows(entry.children, depth + 1, row, positions, placed, usedCells)
					: row + 1
				positions.set(entry.node.id, {row: nodeRow, col: depth})
				placed.add(entry.node.id)
				usedCells.add(nodeRow + ':' + depth)
			})
			return row
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
			const ok = await this.$confirm(this.$t('pages.config.confirmDiscard'), {
				confirmLabel: this.$t('pages.config.discard'),
				confirmColor: 'error',
			})
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
			const ok = await this.$confirm(this.$t('pages.config.confirmDelete', {name: node.name}), {
				confirmLabel: this.$t('pages.config.delete'),
				confirmColor: 'error',
			})
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
