// Simple, dependency-free node box + SVG connector overlay for the
// /wiring graph editor. Free-form drag&drop positioning is implemented
// with plain mouse events (rather than vuedraggable, which targets
// sortable *lists*, not absolute x/y placement) - no new dependency,
// works fully offline/without a build step like the rest of the SPA.

import {registerGlobalComponent} from '../app/registry.js'
import {NODE_BOX_WIDTH, NODE_BOX_HEIGHT} from './constants.js'
import {targetAcceptsReceives, isUsableSource} from './wiringConnect.js'
import './wiringNodeDialog.js'
import './wiringTemplatesDialog.js'

const CONNECTION_STUB = 30
// pointer must travel this far (px) before a press turns into a move-drag
// rather than a tap; below it, pointerup is treated as a click/tap
const DRAG_THRESHOLD = 4
// two taps within this window (ms) = double-tap -> edit; a lone tap after
// it = select. Same idea for mouse, so no reliance on synthetic dblclick
// (unreliable/absent on touch).
const DOUBLE_TAP_MS = 280
// how far back from a port's exact position the connection line's
// invisible delete-hit-region is trimmed, so it stops overlapping (and
// stealing clicks from) the port dot itself - see WiringConnections.edges
const PORT_CLEARANCE = 14

const ROLE_COLORS = {
	IN_ENDP: 'blue',
	OUT_ENDP: 'orange darken-2',
	CTRL: 'green',
	AUX: 'purple',
	HISTORY: 'grey',
	ALERTS: 'red',
}

// Which port dots a card shows. Both come straight from wiringConnect.js
// (data-type rules, not a role whitelist) so the affordance and the
// drop-validity check in index.js can never disagree:
//  - input dot  = the card can receive wires (targetAcceptsReceives)
//  - output dot = the card produces usable data (isUsableSource):
//    everything except a History (constant keep-alive) and a STRING
//    source (Alert, TextInput).
function nodeHasInputPort(node, nodeTypes) {
	return targetAcceptsReceives(node, nodeTypes)
}
function nodeHasOutputPort(node, nodeTypes) {
	return isUsableSource(node, nodeTypes)
}

const WiringNodeBox = {
	props: {
		node: {type: Object, required: true},
		nodeTypes: {type: Object, default: () => ({})},
		connecting: {type: Boolean, default: false},
		selected: {type: Boolean, default: false},
		dropTarget: {type: String, default: null},
	},
	template: `
		<v-sheet
			:elevation="dragging ? 8 : 2"
			outlined
			class="wiring-node-box"
			:class="{
				'wiring-node-box--connecting': connecting,
				'wiring-node-box--selected': selected,
				'wiring-node-box--drop-valid': dropTarget === 'valid',
				'wiring-node-box--drop-invalid': dropTarget === 'invalid',
			}"
			:style="style"
			@pointerdown.stop="onPointerDown"
		>
			<div class="d-flex align-center justify-space-between px-2 pt-1">
				<div class="d-flex align-center" style="flex: 1 1 0; min-width: 0; overflow: hidden">
					<v-chip x-small label :color="color" text-color="white" class="flex-shrink-0">{{ node.role }}</v-chip>
					<span v-if="node.group" class="text-caption grey--text text-truncate ml-1" :title="node.group">{{ node.group }}</span>
				</div>
     <v-btn icon size="x-small" variant="text" color="grey-darken-1" class="flex-shrink-0" @pointerdown.stop @click.stop="$emit('delete', node)" :title="$t('misc.actions.delete')">
					<v-icon size="small">mdi-delete</v-icon>
				</v-btn>
			</div>
			<div class="px-2 pb-1">
				<div class="font-weight-medium text-truncate">{{ node.name }}</div>
				<div class="text-caption grey--text text-truncate">{{ displayType }}</div>
			</div>
		</v-sheet>
	`,
	data: function() {
		return {
			dragging: false,
			dragOffset: {x: 0, y: 0},
			localX: this.node.pos_x || 0,
			localY: this.node.pos_y || 0,
		}
	},
	watch: {
		'node.pos_x': function(val) { if (!this.dragging) this.localX = val || 0 },
		'node.pos_y': function(val) { if (!this.dragging) this.localY = val || 0 },
	},
	computed: {
		color: function() {
			return ROLE_COLORS[this.node.role] || 'grey'
		},
		displayType: function() {
			if ((this.node.role === 'IN_ENDP' || this.node.role === 'OUT_ENDP') && this.node.port) {
				return this.node.type + ' (' + this.node.port + ')'
			}
			return this.node.type
		},
		style: function() {
			return {
				left: this.localX + 'px',
				top: this.localY + 'px',
				width: NODE_BOX_WIDTH + 'px',
			}
		},
	},
	methods: {
		// One pointer handler for mouse, touch and pen: a small move turns
		// the press into a drag (emit drag / drag-end); a press that never
		// moves is a tap - a lone tap selects, two within DOUBLE_TAP_MS
		// open the editor. No separate "select mode" and no dependence on
		// synthetic click/dblclick, so it behaves the same on a touch
		// screen with no mouse.
		onPointerDown: function(ev) {
			if (ev.button && ev.button !== 0) return   // ignore right/middle click
			const el = ev.currentTarget
			this._startX = ev.clientX
			this._startY = ev.clientY
			this._moved = false
			try { el.setPointerCapture(ev.pointerId) } catch (e) { /* older engines */ }
			const onMove = (mv) => {
				if (!this.dragging) {
					if (Math.hypot(mv.clientX - this._startX, mv.clientY - this._startY) < DRAG_THRESHOLD) {
						return
					}
					this.dragging = true
					this._moved = true
					this.dragOffset = {x: mv.clientX - this.localX, y: mv.clientY - this.localY}
				}
				this.localX = Math.max(0, mv.clientX - this.dragOffset.x)
				this.localY = Math.max(0, mv.clientY - this.dragOffset.y)
				this.$emit('drag', {node: this.node, x: this.localX, y: this.localY})
			}
			const onUp = () => {
				el.removeEventListener('pointermove', onMove)
				el.removeEventListener('pointerup', onUp)
				el.removeEventListener('pointercancel', onUp)
				if (this.dragging) {
					this.dragging = false
					this.$emit('drag-end', {node: this.node, x: this.localX, y: this.localY})
				} else if (!this._moved) {
					this.onTap()
				}
			}
			el.addEventListener('pointermove', onMove)
			el.addEventListener('pointerup', onUp)
			el.addEventListener('pointercancel', onUp)
		},
		onTap: function() {
			const now = (typeof performance !== 'undefined' ? performance.now() : Date.now())
			if (now - (this._lastTap || 0) < DOUBLE_TAP_MS) {
				clearTimeout(this._tapTimer)
				this._lastTap = 0
				this.$emit('edit', this.node)
			} else {
				this._lastTap = now
				this._tapTimer = setTimeout(() => {
					this._lastTap = 0
					this.$emit('select', this.node)
				}, DOUBLE_TAP_MS)
			}
		},
	},
	beforeUnmount: function() {
		clearTimeout(this._tapTimer)
	},
}
registerGlobalComponent('WiringNodeBox', WiringNodeBox)

const WiringConnections = {
	props: {
		nodes: {type: Array, required: true},
		nodeTypes: {type: Object, default: () => ({})},
		width: {type: Number, required: true},
		height: {type: Number, required: true},
		preview: {type: Object, default: null},
	},
	template: `
		<svg class="wiring-connections" :width="width" :height="height">
			<g
				v-for="edge in edges"
				:key="edge.key"
				class="wiring-connection-group"
				@mouseenter="hoveredEdgeKey = edge.key"
				@mouseleave="hoveredEdgeKey = null"
			>
				<path
					:d="edge.hitPath"
					fill="none"
					class="wiring-connection-hit"
				></path>
				<path
					:d="edge.diagonalPath"
					fill="none"
					stroke="#90a4ae" stroke-width="2" stroke-dasharray="4 3"
					class="wiring-connection-line"
					:class="{'wiring-connection-line--hover': hoveredEdgeKey === edge.key}"
				></path>
				<path
					:d="edge.stubPath"
					fill="none"
					stroke="#90a4ae" stroke-width="2" marker-end="url(#wiring-arrow)"
					class="wiring-connection-line"
					:class="{'wiring-connection-line--hover': hoveredEdgeKey === edge.key}"
				></path>
				<g
					v-if="edge.deletable && hoveredEdgeKey === edge.key"
					class="wiring-connection-delete"
					:transform="'translate(' + edge.midX + ',' + edge.midY + ')'"
					@click="$emit('remove', edge)"
				>
					<title>{{ $t('pages.wiring.deleteConnection') }}</title>
					<circle r="9" fill="#f44336"></circle>
					<path d="M-4,-4 L4,4 M4,-4 L-4,4" stroke="white" stroke-width="1.6" stroke-linecap="round"></path>
				</g>
			</g>
			<path
				v-if="preview"
				:d="'M' + preview.x1 + ',' + preview.y1 + ' L' + preview.x2 + ',' + preview.y2"
				fill="none"
				stroke="#1976d2" stroke-width="2"
				:marker-end="preview.arrowAtStart ? null : 'url(#wiring-arrow-preview)'"
				:marker-start="preview.arrowAtStart ? 'url(#wiring-arrow-preview)' : null"
				class="wiring-connection-preview"
			></path>
			<circle
				v-for="port in ports"
				:key="port.node.id + '-' + port.kind"
				:cx="port.x" :cy="port.y" r="8"
				:class="['wiring-node-port-svg', 'wiring-node-port-svg--' + port.kind]"
				@pointerdown.stop="$emit('port-pointerdown', {node: port.node, port: port.kind, clientX: $event.clientX, clientY: $event.clientY})"
			>
				<title>{{ $t(port.kind === 'input' ? 'pages.wiring.portIn' : 'pages.wiring.portOut') }}</title>
			</circle>
			<defs>
				<marker id="wiring-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
					<path d="M0,0 L8,4 L0,8 z" fill="#90a4ae"></path>
				</marker>
				<marker id="wiring-arrow-preview" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
					<path d="M0,0 L8,4 L0,8 z" fill="#1976d2"></path>
				</marker>
			</defs>
		</svg>
	`,
	data: function() {
		return {
			hoveredEdgeKey: null,
		}
	},
	computed: {
		byId: function() {
			const map = {}
			this.nodes.forEach(n => { map[n.id] = n })
			return map
		},
		ports: function() {
			const ports = []
			this.nodes.forEach(node => {
				const y = (node.pos_y || 0) + NODE_BOX_HEIGHT / 2
				if (nodeHasInputPort(node, this.nodeTypes)) {
					ports.push({node, kind: 'input', x: (node.pos_x || 0), y})
				}
				if (nodeHasOutputPort(node, this.nodeTypes)) {
					ports.push({node, kind: 'output', x: (node.pos_x || 0) + NODE_BOX_WIDTH, y})
				}
			})
			return ports
		},
		edges: function() {
			const edges = []
			this.nodes.forEach(target => {
				(target.receives || []).forEach(sourceId => {
					const source = this.byId[sourceId]
					if (!source) return
					const x1 = (source.pos_x || 0) + NODE_BOX_WIDTH
					const y1 = (source.pos_y || 0) + NODE_BOX_HEIGHT / 2
					const x2 = (target.pos_x || 0)
					const y2 = (target.pos_y || 0) + NODE_BOX_HEIGHT / 2
					// Bundled route: a short exit/entry stub at a fixed offset
					// from each port (not the dynamic midpoint of both
					// endpoints), connected by a direct diagonal. Every edge
					// leaving the same source shares its exit stub, and every
					// edge entering the same target shares its entry stub -
					// reads as a schematic bus fanning out/merging - while the
					// diagonal (the one part of the route that's individual per
					// edge, and most likely to need manual dragging to
					// untangle) is drawn separately/dashed so the shared stubs
					// stay the visually dominant, easy-to-read part.
					const sourceTrunkX = x1 + CONNECTION_STUB
					const targetTrunkX = x2 - CONNECTION_STUB
					const midX = (sourceTrunkX + targetTrunkX) / 2
					const midY = (y1 + y2) / 2
					const stubPath = 'M' + x1 + ',' + y1 + ' H' + sourceTrunkX
						+ ' M' + targetTrunkX + ',' + y2 + ' H' + x2
					const diagonalPath = 'M' + sourceTrunkX + ',' + y1 + ' L' + targetTrunkX + ',' + y2
					// combined, for the (invisible, wide) click-to-delete hit-area -
					// trimmed back by PORT_CLEARANCE at each end so it doesn't sit on
					// top of the port dot itself (the visible stub still starts exactly
					// AT the port; only this invisible hit-region is pulled back -
					// otherwise, being above the port in stacking order, it swallows
					// clicks meant for the port)
					const hitStartX = Math.min(x1 + PORT_CLEARANCE, sourceTrunkX)
					const hitEndX = Math.max(x2 - PORT_CLEARANCE, targetTrunkX)
					const hitPath = 'M' + hitStartX + ',' + y1 + ' H' + sourceTrunkX
						+ ' L' + targetTrunkX + ',' + y2 + ' H' + hitEndX
					edges.push({
						key: sourceId + '->' + target.id,
						sourceId, targetId: target.id,
						x1, y1, x2, y2,
						hitPath,
						stubPath,
						diagonalPath,
						midX,
						midY,
						// Alert.receives is derived from its conditions, not
						// directly editable - the generic delete-X (which
						// stages a plain receives edit) doesn't apply here;
						// Alert nodes also never render an input port to
						// drag a new connection onto in the first place.
						deletable: target.role !== 'ALERTS',
					})
				})
			})
			return edges
		},
	},
}
registerGlobalComponent('WiringConnections', WiringConnections)

export {NODE_BOX_WIDTH, NODE_BOX_HEIGHT}

// vim: set noet ts=4 sw=4:
