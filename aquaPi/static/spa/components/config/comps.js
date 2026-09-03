// Simple, dependency-free node box + SVG connector overlay for the
// /config graph editor. Free-form drag&drop positioning is implemented
// with plain mouse events (rather than vuedraggable, which targets
// sortable *lists*, not absolute x/y placement) - no new dependency,
// works fully offline/without a build step like the rest of the SPA.

import {registerGlobalComponent} from '../app/registry.js'
import './configNodeDialog.js'
import './configTemplatesDialog.js'

const NODE_BOX_WIDTH = 240
const NODE_BOX_HEIGHT = 76
const CONNECTION_STUB = 30
// how far back from a port's exact position the connection line's
// invisible delete-hit-region is trimmed, so it stops overlapping (and
// stealing clicks from) the port dot itself - see ConfigConnections.edges
const PORT_CLEARANCE = 14

const ROLE_COLORS = {
	IN_ENDP: 'blue',
	OUT_ENDP: 'orange darken-2',
	CTRL: 'green',
	AUX: 'purple',
	HISTORY: 'grey',
	ALERTS: 'red',
}

// Which roles may act as a connection's SOURCE (i.e. show a draggable
// output port, and be a valid drop target when dragging FROM another
// node's input port). Checked against each role's actual runtime
// behavior, not just what the live topology happens to use today:
// - IN_ENDP/CTRL/AUX: their whole purpose is producing new data other
//   nodes subscribe to - always sourceable.
// - OUT_ENDP (output devices): SwitchDevice/SlowPwmDevice/AnalogDevice
//   all genuinely self.post(MsgData(...)) their real, changing actuated
//   value (out_nodes.py) - real data (e.g. History graphing what a
//   device actually did, distinct from what its controller commanded)
//   - sourceable.
// - HISTORY: posts a hardcoded constant 0 on every message
//   (hist_nodes.py, "just anything for MsgHello") - a keep-alive, not
//   real data. Nothing downstream could meaningfully use it - excluded.
// - ALERTS: does post real content (the joined alert-message string),
//   but it's STRING-typed and no current consumer handles that safely -
//   History would crash on it, AlertCond's numeric comparison would
//   TypeError - this is exactly the still-deferred
//   config-receives-type-filtering gap, so excluded here too rather
//   than opening a new instance of the same problem.
// Enforced at both ends: hasOutput below hides the affordance for a
// forward (output-port-initiated) drag, and
// AquapiConfig.isValidConnection (index.js) independently re-checks the
// SOURCE role too, since a reverse (input-port-initiated) drag can
// hover any card regardless of whether that card shows its own output
// dot.
const SOURCEABLE_ROLES = ['IN_ENDP', 'CTRL', 'AUX', 'OUT_ENDP']

// Shared by ConfigConnections, which owns rendering AND hit-testing for
// both port kinds (see below - ports live in the SVG overlay, not on
// the card itself, specifically so they can paint above connection
// lines; a div nested inside ConfigNodeBox never could, since the card
// establishes its own stacking context that can't out-rank a sibling
// one no matter its own z-index).
function nodeHasInputPort(node, nodeTypes) {
	const schema = nodeTypes[node.type]
	return !schema || schema.receives !== 'none'
}
function nodeHasOutputPort(node) {
	return SOURCEABLE_ROLES.includes(node.role)
}

const ConfigNodeBox = {
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
			class="config-node-box"
			:class="{
				'config-node-box--connecting': connecting,
				'config-node-box--selected': selected,
				'config-node-box--drop-valid': dropTarget === 'valid',
				'config-node-box--drop-invalid': dropTarget === 'invalid',
			}"
			:style="style"
			@mousedown.stop="onDragStart"
			@click.stop="onClick"
		>
			<div class="d-flex align-center justify-space-between px-2 pt-1">
				<v-chip x-small label :color="color" text-color="white">{{ node.role }}</v-chip>
				<div>
     <v-btn icon size="x-small" variant="text" color="grey-darken-1" @click.stop="$emit('edit', node)" :title="$t('pages.config.edit')">
						<v-icon size="small">mdi-pencil</v-icon>
					</v-btn>
     <v-btn icon size="x-small" variant="text" color="grey-darken-1" @click.stop="$emit('delete', node)" :title="$t('pages.config.delete')">
						<v-icon size="small">mdi-delete</v-icon>
					</v-btn>
				</div>
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
		onClick: function() {
			this.$emit('select', this.node)
		},
		onDragStart: function(ev) {
			this.dragging = true
			this.dragOffset = {x: ev.clientX - this.localX, y: ev.clientY - this.localY}
			const onMove = (mv) => {
				this.localX = Math.max(0, mv.clientX - this.dragOffset.x)
				this.localY = Math.max(0, mv.clientY - this.dragOffset.y)
				this.$emit('drag', {node: this.node, x: this.localX, y: this.localY})
			}
			const onUp = () => {
				this.dragging = false
				document.removeEventListener('mousemove', onMove)
				document.removeEventListener('mouseup', onUp)
				this.$emit('drag-end', {node: this.node, x: this.localX, y: this.localY})
			}
			document.addEventListener('mousemove', onMove)
			document.addEventListener('mouseup', onUp)
		},
	},
}
registerGlobalComponent('ConfigNodeBox', ConfigNodeBox)

const ConfigConnections = {
	props: {
		nodes: {type: Array, required: true},
		nodeTypes: {type: Object, default: () => ({})},
		width: {type: Number, required: true},
		height: {type: Number, required: true},
		preview: {type: Object, default: null},
	},
	template: `
		<svg class="config-connections" :width="width" :height="height">
			<g
				v-for="edge in edges"
				:key="edge.key"
				class="config-connection-group"
				@mouseenter="hoveredEdgeKey = edge.key"
				@mouseleave="hoveredEdgeKey = null"
			>
				<path
					:d="edge.hitPath"
					fill="none"
					class="config-connection-hit"
				></path>
				<path
					:d="edge.diagonalPath"
					fill="none"
					stroke="#90a4ae" stroke-width="2" stroke-dasharray="4 3"
					class="config-connection-line"
					:class="{'config-connection-line--hover': hoveredEdgeKey === edge.key}"
				></path>
				<path
					:d="edge.stubPath"
					fill="none"
					stroke="#90a4ae" stroke-width="2" marker-end="url(#config-arrow)"
					class="config-connection-line"
					:class="{'config-connection-line--hover': hoveredEdgeKey === edge.key}"
				></path>
				<g
					v-if="edge.deletable && hoveredEdgeKey === edge.key"
					class="config-connection-delete"
					:transform="'translate(' + edge.midX + ',' + edge.midY + ')'"
					@click="$emit('remove', edge)"
				>
					<title>{{ $t('pages.config.deleteConnection') }}</title>
					<circle r="9" fill="#f44336"></circle>
					<path d="M-4,-4 L4,4 M4,-4 L-4,4" stroke="white" stroke-width="1.6" stroke-linecap="round"></path>
				</g>
			</g>
			<path
				v-if="preview"
				:d="'M' + preview.x1 + ',' + preview.y1 + ' L' + preview.x2 + ',' + preview.y2"
				fill="none"
				stroke="#1976d2" stroke-width="2"
				:marker-end="preview.arrowAtStart ? null : 'url(#config-arrow-preview)'"
				:marker-start="preview.arrowAtStart ? 'url(#config-arrow-preview)' : null"
				class="config-connection-preview"
			></path>
			<circle
				v-for="port in ports"
				:key="port.node.id + '-' + port.kind"
				:cx="port.x" :cy="port.y" r="8"
				:class="['config-node-port-svg', 'config-node-port-svg--' + port.kind]"
				@mousedown.stop="$emit('port-mousedown', {node: port.node, port: port.kind, clientX: $event.clientX, clientY: $event.clientY})"
			>
				<title>{{ $t(port.kind === 'input' ? 'pages.config.portIn' : 'pages.config.portOut') }}</title>
			</circle>
			<defs>
				<marker id="config-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
					<path d="M0,0 L8,4 L0,8 z" fill="#90a4ae"></path>
				</marker>
				<marker id="config-arrow-preview" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
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
				if (nodeHasOutputPort(node)) {
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
registerGlobalComponent('ConfigConnections', ConfigConnections)

export {NODE_BOX_WIDTH, NODE_BOX_HEIGHT, SOURCEABLE_ROLES}

// vim: set noet ts=4 sw=4:
