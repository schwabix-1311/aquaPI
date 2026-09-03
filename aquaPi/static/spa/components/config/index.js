import './comps.js'
import {NODE_BOX_WIDTH, NODE_BOX_HEIGHT, SOURCEABLE_ROLES} from './comps.js'
import {registerGlobalComponent} from '../app/registry.js'
import {useDashboardStore} from '../../store/modules/dashboard.js'
import {useConfigStore} from '../../store/modules/config.js'
import {isRoot, isHistOrAlert, descendants, flattenEntries} from '../settings/chains.js'

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
						<v-alert v-if="selectMode" dense text type="info" class="mb-0">
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
					<div class="config-canvas" ref="canvas" :style="canvasStyle">
						<config-connections
							:nodes="nodesForConnections"
							:node-types="nodeTypes"
							:width="canvasWidth"
							:height="canvasHeight"
							:preview="previewEdge"
							@remove="onRemoveEdge"
							@port-mousedown="onConnectDragStart"
						></config-connections>

						<config-node-box
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
			connectDrag: null,
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
				this.configStore.fetchNodeTypes(),
			])
			this.configStore.initDraft()
			// nobody has ever positioned anything yet (fresh/default wiring) -
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
			// Longest chains first (by total descendant count): placing a
			// tall chain into whatever's already a dense block of short
			// ones (rather than the reverse) tends to force it further
			// right/down than it needs, fragmenting the layout more than
			// starting with the tall ones and filling shorter ones in
			// around them. Sort key is the FLATTENED descendant count -
			// tree.length itself is only the number of direct children
			// (descendants() returns a nested {node, children} tree, not
			// a flat list), which underweights deep-but-narrow chains and
			// left equal-direct-children roots ordered by array insertion
			// order instead of actual chain size.
			const roots = nodes.filter(n => isRoot(n) && !isHistOrAlert(n))
				.map(root => ({root, tree: descendants(root, byId)}))
				.sort((a, b) => flattenEntries(b.tree).length - flattenEntries(a.tree).length)
			roots.forEach(({root, tree}) => {
				if (placed.has(root.id)) return
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
			// row = the MEDIAN row among its sources, so it lands near where
			// most of them are instead of chasing whichever single source
			// happens to sit lowest. Math.max() here used to mean one short,
			// late-placed source (e.g. a leaf root chain with no
			// descendants, sorted to the very end above) could drag a sink
			// far down even though its other sources sit much higher - the
			// sink inherited the worst case instead of the typical one.
			// col = one past their rightmost column, instead of column 0 -
			// pinning it to column 0 like a real root previously sent its
			// incoming connection's target-side trunk stub
			// (targetTrunkX = pos_x - CONNECTION_STUB) to a negative x, off
			// the left edge of the canvas and invisible. Falls back to its
			// own fresh row/col 0 if nothing resolves (e.g. only `'*'`, a
			// missing id, or no receives at all).
			nodes.filter(isHistOrAlert).forEach(node => {
				const sourcePositions = (node.receives || [])
					.map(id => positions.get(id))
					.filter(Boolean)
				if (sourcePositions.length) {
					const rows = sourcePositions.map(p => p.row).sort((a, b) => a - b)
					const mid = Math.floor(rows.length / 2)
					const row = rows.length % 2
						? rows[mid]
						: Math.round((rows[mid - 1] + rows[mid]) / 2)
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
				// nodes with more than one incoming connection get nudged
				// down by half their own box height - their several
				// diagonals converge from different rows, so centering on
				// any one of those rows sends at least one wire straight
				// through the box above/below; splitting the difference
				// keeps them all visually distinct. Half the box's OWN
				// height (not half a full row) keeps this unconditionally
				// safe: even a same-column neighbor in the very next row
				// still keeps LAYOUT_ROW_GAP/2 of clearance instead of
				// overlapping it, so there's no need to check whether that
				// cell happens to be occupied first.
				const receivesCount = (byId[nodeId]?.receives || []).length
				const rowOffsetPx = receivesCount > 1 ? NODE_BOX_HEIGHT / 2 : 0
				this.configStore.draftUpdateNode({
					nodeId,
					changes: {
						pos_x: pos.col * (NODE_BOX_WIDTH + LAYOUT_COL_GAP),
						pos_y: pos.row * (NODE_BOX_HEIGHT + LAYOUT_ROW_GAP) + rowOffsetPx,
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
			this.connectDrag = null
			this.editingNode = null
			this.dialogOpen = true
		},

		openEditDialog: function(node) {
			this.connectDrag = null
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
			// connecting is now drag-driven (see onConnectDragStart) - a
			// plain click only ever mattered for select-mode's multi-select
			if (!this.selectMode) {
				return
			}
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
				document.removeEventListener('mousemove', onMove)
				document.removeEventListener('mouseup', onUp)
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
			document.addEventListener('mousemove', onMove)
			document.addEventListener('mouseup', onUp)
		},

		// validity only depends on the receiving end: for an output-drag
		// that's whatever's hovered, for an input-drag it's the fixed
		// drag origin itself (already guaranteed valid - hasInput only
		// renders that port when receives !== 'none' in the first place)
		isValidConnection(dragOriginNode, port, hoverNode) {
			const source = port === 'output' ? dragOriginNode : hoverNode
			const receiver = port === 'output' ? hoverNode : dragOriginNode
			if (!SOURCEABLE_ROLES.includes(source.role)) return false
			const schema = this.nodeTypes[receiver.type]
			return !!schema && schema.receives !== 'none' && receiver.role !== 'ALERTS'
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

			this.configStore.draftUpdateNode({
				nodeId: target.id,
				changes: {receives},
			})
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
