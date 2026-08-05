// Simple, dependency-free node box + SVG connector overlay for the
// /config graph editor. Free-form drag&drop positioning is implemented
// with plain mouse events (rather than vuedraggable, which targets
// sortable *lists*, not absolute x/y placement) - no new dependency,
// works fully offline/without a build step like the rest of the SPA.

import {registerGlobalComponent} from '../app/registry.js'

const NODE_BOX_WIDTH = 240
const NODE_BOX_HEIGHT = 76

const ROLE_COLORS = {
	IN_ENDP: 'blue',
	OUT_ENDP: 'deep-orange',
	CTRL: 'green',
	AUX: 'purple',
	HISTORY: 'grey',
	ALERTS: 'red',
}

const ConfigNodeBox = {
	props: {
		node: {type: Object, required: true},
		connecting: {type: Boolean, default: false},
		selected: {type: Boolean, default: false},
	},
	template: `
		<v-sheet
			:elevation="dragging ? 8 : 2"
			outlined
			class="config-node-box"
			:class="{'config-node-box--connecting': connecting, 'config-node-box--selected': selected}"
			:style="style"
			@mousedown.stop="onDragStart"
			@click.stop="onClick"
		>
			<div class="d-flex align-center justify-space-between px-2 pt-1">
				<v-chip x-small label :color="color" text-color="white">{{ node.role }}</v-chip>
				<div>
     <v-btn icon size="x-small" variant="text" color="grey-darken-1" @click.stop="$emit('connect', node)" :title="$t('pages.config.connect')">
						<v-icon size="small">mdi-vector-line</v-icon>
					</v-btn>
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
				<div class="text-caption grey--text text-truncate">{{ node.type }}</div>
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
		width: {type: Number, required: true},
		height: {type: Number, required: true},
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
					:d="edge.path"
					fill="none"
					class="config-connection-hit"
				></path>
				<path
					:d="edge.path"
					fill="none"
					stroke="#90a4ae" stroke-width="2" marker-end="url(#config-arrow)"
					class="config-connection-line"
					:class="{'config-connection-line--hover': hoveredEdgeKey === edge.key}"
				></path>
				<g
					v-if="hoveredEdgeKey === edge.key"
					class="config-connection-delete"
					:transform="'translate(' + edge.midX + ',' + edge.midY + ')'"
					@click="$emit('remove', edge)"
				>
					<title>{{ $t('pages.config.deleteConnection') }}</title>
					<circle r="9" fill="#f44336"></circle>
					<path d="M-4,-4 L4,4 M4,-4 L-4,4" stroke="white" stroke-width="1.6" stroke-linecap="round"></path>
				</g>
			</g>
			<defs>
				<marker id="config-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
					<path d="M0,0 L8,4 L0,8 z" fill="#90a4ae"></path>
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
					const midX = (x1 + x2) / 2
					const midY = (y1 + y2) / 2
					// Angled (elbow) route: horizontal-vertical-horizontal, so the
					// side of a card a connection touches (right = output, left =
					// input) stays visually clear, instead of a plain diagonal line.
					const path = 'M' + x1 + ',' + y1 + ' H' + midX + ' V' + y2 + ' H' + x2
					edges.push({
						key: sourceId + '->' + target.id,
						sourceId, targetId: target.id,
						x1, y1, x2, y2,
						path,
						midX,
						midY,
					})
				})
			})
			return edges
		},
	},
}
registerGlobalComponent('ConfigConnections', ConfigConnections)

const ConfigNodeDialog = {
	props: {
		modelValue: {type: Boolean, default: false},
		nodeTypes: {type: Object, required: true},
		nodes: {type: Array, required: true},
		editNode: {type: Object, default: null},
	},
	template: `
		<v-dialog v-model="show" max-width="520" persistent>
			<v-card>
				<v-card-title>
					{{ editNode ? $t('pages.config.editNode') : $t('pages.config.addNode') }}
				</v-card-title>
				<v-card-text>
					<v-alert v-if="error" type="error" dense text class="mb-3">{{ error }}</v-alert>

					<v-select
						v-if="!editNode"
						v-model="form.type"
						:items="typeItems"
						:label="$t('pages.config.nodeType')"
						outlined dense
						@change="onTypeChange"
					></v-select>

					<v-text-field
						v-if="!editNode"
						v-model="form.name"
						:label="$t('pages.config.nodeName')"
						outlined dense
					></v-text-field>

					<v-select
						v-if="receivesKind !== 'none'"
						v-model="form.receives"
						:items="receivesItems"
						:multiple="receivesKind === 'multi'"
						:label="$t('pages.config.receives')"
						outlined dense
						clearable
					></v-select>

					<v-text-field
						v-model="form.group"
						:label="$t('pages.config.group')"
						outlined dense
					></v-text-field>

					<div v-for="field in schemaFields" :key="field.key">
						<v-switch
							v-if="field.type === 'checkbox'"
							v-model="form.fields[field.key]"
							:label="field.label"
							dense
						></v-switch>
						<v-text-field
							v-else-if="field.type === 'number'"
							v-model.number="form.fields[field.key]"
							:label="field.label"
							type="number"
							:min="field.min" :max="field.max"
							outlined dense
						></v-text-field>
						<v-text-field
							v-else
							v-model="form.fields[field.key]"
							:label="field.label"
							outlined dense
						></v-text-field>
					</div>
				</v-card-text>
				<v-card-actions>
					<v-spacer></v-spacer>
					<v-btn text @click="cancel">{{ $t('pages.config.cancel') }}</v-btn>
					<v-btn color="primary" @click="save" :loading="saving">{{ $t('pages.config.save') }}</v-btn>
				</v-card-actions>
			</v-card>
		</v-dialog>
	`,
	data: function() {
		return {
			form: {type: '', name: '', receives: null, group: '', fields: {}},
			saving: false,
			error: null,
		}
	},
	computed: {
		show: {
			get: function() { return this.modelValue },
			set: function(val) { this.$emit('update:modelValue', val) },
		},
		typeItems: function() {
			return Object.keys(this.nodeTypes).sort()
		},
		schema: function() {
			const typeName = this.editNode ? this.editNode.type : this.form.type
			return this.nodeTypes[typeName] || {receives: 'none', fields: []}
		},
		schemaFields: function() {
			return this.schema.fields || []
		},
		receivesKind: function() {
			return this.schema.receives || 'none'
		},
		receivesItems: function() {
			const selfId = this.editNode ? this.editNode.id : null
			return this.nodes
				.filter(n => n.id !== selfId)
				.map(n => ({text: n.name + ' (' + n.type + ')', value: n.id}))
		},
	},
	watch: {
		modelValue: function(val) {
			if (val) {
				this.resetForm()
			}
		},
	},
	methods: {
		resetForm: function() {
			this.error = null
			if (this.editNode) {
				this.form = {
					type: this.editNode.type,
					name: this.editNode.name,
					receives: this.receivesKind === 'multi'
						? (this.editNode.receives || []).slice()
						: ((this.editNode.receives || [])[0] || null),
					group: this.editNode.group || '',
					fields: this.buildFieldValues(this.editNode),
				}
			} else {
				this.form = {type: '', name: '', receives: null, group: '', fields: {}}
			}
		},
		buildFieldValues: function(node) {
			const values = {}
			this.schemaFields.forEach(field => {
				values[field.key] = (node && node[field.key] !== undefined) ? node[field.key]
					: (field.default !== undefined ? field.default : '')
			})
			return values
		},
		onTypeChange: function() {
			this.form.receives = this.receivesKind === 'multi' ? [] : null
			this.form.fields = this.buildFieldValues(null)
		},
		asReceivesList: function() {
			if (this.receivesKind === 'none') return []
			if (this.receivesKind === 'multi') return this.form.receives || []
			return this.form.receives ? [this.form.receives] : []
		},
		cancel: function() {
			this.show = false
		},
		save: function() {
			this.error = null
			this.saving = true
			try {
				if (this.editNode) {
					this.$store.dispatch('config/draftUpdateNode', {
						nodeId: this.editNode.id,
						changes: Object.assign(
							{receives: this.asReceivesList(), group: this.form.group},
							this.form.fields
						),
					})
				} else {
					if (!this.form.type || !this.form.name) {
						this.error = this.$t('pages.config.errNameType')
						return
					}
					this.$store.dispatch('config/draftCreateNode', Object.assign({
						type: this.form.type,
						name: this.form.name,
						receives: this.asReceivesList(),
						group: this.form.group,
						pos_x: 20,
						pos_y: 20,
					}, this.form.fields))
				}
				this.$toast.success(this.$t('misc.toast.saveSuccess'))
				this.show = false
			} finally {
				this.saving = false
			}
		},
	},
}
registerGlobalComponent('ConfigNodeDialog', ConfigNodeDialog)

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
		show: {
			get: function() { return this.modelValue },
			set: function(val) { this.$emit('update:modelValue', val) },
		},
		templates: function() {
			return this.$store.getters['config/templates']
		},
		snapshots: function() {
			return this.$store.getters['config/snapshots']
		},
	},
	watch: {
		modelValue: function(val) {
			if (val) {
				this.error = null
				this.$store.dispatch('config/fetchTemplates')
				this.$store.dispatch('config/fetchSnapshots')
			}
		},
	},
	methods: {
		async saveTemplate() {
			this.saving = true
			try {
				const result = await this.$store.dispatch('config/createTemplate', {
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
			const result = await this.$store.dispatch('config/insertTemplate', {name: tpl.name})
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
			const ok = await this.$confirm(this.$t('pages.config.confirmDeleteTemplate', {name: tpl.name}))
			if (!ok) {
				return
			}
			const result = await this.$store.dispatch('config/deleteTemplate', {name: tpl.name})
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
				const result = await this.$store.dispatch('config/createSnapshot', {name: this.newSnapshotName})
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
			const ok = await this.$confirm(this.$t('pages.config.confirmRestoreSnapshot', {name: snap.name}))
			if (!ok) {
				return
			}
			this.restoring = true
			try {
				const result = await this.$store.dispatch('config/restoreSnapshot', {name: snap.name})
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
			const ok = await this.$confirm(this.$t('pages.config.confirmDeleteSnapshot', {name: snap.name}))
			if (!ok) {
				return
			}
			const result = await this.$store.dispatch('config/deleteSnapshot', {name: snap.name})
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

export {NODE_BOX_WIDTH, NODE_BOX_HEIGHT}

// vim: set noet ts=4 sw=4:
