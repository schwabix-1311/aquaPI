import {registerGlobalComponent} from '../app/registry.js'
import {useWiringStore} from '../../store/modules/wiring.js'
import {connectableSources} from './wiringConnect.js'
// side effect: registers SettingNumber/SettingSlider/SettingDuration/... -
// db.py's get_node_type_schema() returns the same Setting.to_dict() shape
// /settings' own node settings API does, so this dialog can reuse those
// widgets instead of its own plain inputs.
import {settingWidgetType} from '../settings/comps.js'

const WiringNodeDialog = {
	props: {
		modelValue: {type: Boolean, default: false},
		nodeTypes: {type: Object, required: true},
		nodes: {type: Array, required: true},
		editNode: {type: Object, default: null},
	},
	template: `
		<v-dialog v-model="show" max-width="700" persistent>
			<v-card>
				<v-card-title>
					{{ editNode ? $t('pages.wiring.editNode', {name: editNode.name}) : $t('pages.wiring.addNode') }}
				</v-card-title>
				<v-card-text>
					<v-alert v-if="error" type="error" dense text class="mb-3">{{ error }}</v-alert>

					<v-select
						v-if="!editNode"
						v-model="form.type"
						:items="typeItems"
						:label="$t('pages.wiring.nodeType')"
						outlined dense
						autocomplete="off"
						@change="onTypeChange"
					></v-select>

					<v-text-field
						v-if="!editNode"
						v-model="form.name"
						:label="$t('pages.wiring.nodeName')"
						outlined dense
						autocomplete="off"
					></v-text-field>

					<v-select
						v-if="receivesKind !== 'none'"
						v-model="form.receives"
						:items="receivesItems"
						item-title="title"
						item-value="value"
						:multiple="receivesKind === 'multi'"
						:label="$t('pages.wiring.receives')"
						outlined dense
						clearable
						autocomplete="off"
					></v-select>

					<v-combobox
						v-model="form.group"
						:items="groupItems"
						:label="$t('pages.wiring.group')"
						outlined dense
						clearable
						autocomplete="off"
					></v-combobox>

					<div v-for="item in formFieldItems" :key="item.key + '.' + dialogInstanceKey" class="mb-3">
						<component
							:is="widgetType(item)"
							:item="item"
							:owner-node-id="editNode ? editNode.id : null"
							@update="form.fields[item.key] = $event"
						></component>
					</div>
				</v-card-text>
				<v-card-actions>
					<v-spacer></v-spacer>
					<v-btn text @click="cancel">{{ $t('misc.actions.cancel') }}</v-btn>
					<v-btn color="primary" @click="save" :loading="saving">{{ $t('misc.actions.save') }}</v-btn>
				</v-card-actions>
			</v-card>
		</v-dialog>
	`,
	data: function() {
		return {
			form: {type: '', name: '', receives: null, group: '', fields: {}},
			saving: false,
			error: null,
			dialogInstanceKey: 0,
		}
	},
	computed: {
		wiringStore() {
			return useWiringStore()
		},
		show: {
			get: function() { return this.modelValue },
			set: function(val) { this.$emit('update:modelValue', val) },
		},
		typeItems: function() {
			return Object.keys(this.nodeTypes).sort()
		},
		// existing group names across all nodes, offered as combobox
		// suggestions so a node can be added to a known group without
		// retyping (and risking a typo that splits the group); the
		// combobox still accepts a freely typed new name.
		groupItems: function() {
			const seen = new Set()
			this.nodes.forEach(n => {
				if (n.group) {
					seen.add(n.group)
				}
			})
			return Array.from(seen).sort((a, b) => a.localeCompare(b))
		},
		schema: function() {
			const typeName = this.editNode ? this.editNode.type : this.form.type
			return this.nodeTypes[typeName] || {receives: 'none', fields: []}
		},
		receivesKind: function() {
			return this.schema.receives || 'none'
		},
		// this dialog's generic create/edit form is a batched draft (only
		// committed to the backend on a later "Save changes"/save()
		// PUT/POST), unlike /settings' own per-field-immediate-commit
		// PUT - see Setting.live_only/creation_only in msg_bus.py. A
		// liveOnly field (e.g. UiSwitchInput.value) must never round-trip
		// through here at all: submitting it on edit would setattr() the
		// node's live value property, silently flipping real state as a
		// side effect of an unrelated field edit. A creationOnly field
		// (e.g. initval) is consumed once by the constructor and never
		// re-read afterward, so editing an existing node's copy of it is a
		// no-op that only looks like it did something - only offer it
		// while creating.
		visibleFields: function() {
			return this.schema.fields.filter(field => {
				if (field.liveOnly) return false
				if (field.creationOnly && this.editNode) return false
				return true
			})
		},
		// what the Setting* widgets (SettingNumber/SettingSlider/...) render:
		// each schema field's static metadata, plus its label resolved from
		// an i18n key (Setting.label convention, see msg_bus.py - same
		// resolution NodeSettingsFields does for /settings) and its current
		// value overlaid from the live draft state (form.fields, already
		// seeded for both create and edit by buildFieldValues() below) -
		// the schema's own 'value' is only ever a suggested default, not
		// this field's actual current value.
		formFieldItems: function() {
			return this.visibleFields.map(field => ({
				...field,
				label: this.$t('pages.settings.fields.' + field.label),
				value: this.form.fields[field.key],
			}))
		},
		// only nodes that may actually feed this one (see wiringConnect.js):
		// a data producer that isn't STRING-typed or a History. The target
		// is the node being edited, or - while creating - a stand-in with
		// just the type/role canConnect() needs.
		receivesItems: function() {
			const target = this.editNode
				|| {id: null, type: this.form.type, role: this.schema.role}
			return connectableSources(target, this.nodes, this.nodeTypes)
				.map(n => ({title: n.name + ' (' + n.type + ')', value: n.id, text: n.name + ' (' + n.type + ')'}))
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
		widgetType: settingWidgetType,
		resetForm: function() {
			this.error = null
			this.dialogInstanceKey++
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
			this.visibleFields.forEach(field => {
				values[field.key] = node ? this.valueFromLiveNode(node, field) : this.valueFromSchemaDefault(field)
			})
			return values
		},
		// node[field.key] is the node's own live attribute, in whatever
		// internal unit it stores (e.g. History.capacity in hours) -
		// convert to the wire unit (seconds) the Setting* widgets expect,
		// the same conversion get_settings()/api_set_node_settings() do
		// server-side. See Setting.to_dict()'s attrs.factor. Falls back to
		// the schema default if this node doesn't carry the field at all
		// (e.g. a field added to the type after this node was created).
		// attrs.factor is only ever set for duration fields (msg_bus.py's
		// Setting.to_dict() sends null whenever factor == 1, i.e. for
		// every non-duration field) - `|| 1` used to paper over that with
		// a multiply-by-1 no-op for plain numbers, but for a non-numeric
		// field (e.g. a 'select' port value, a string) `"GPIO 13 out" * 1`
		// is NaN, not a no-op. Skip the multiplication entirely instead of
		// defaulting the factor to 1.
		valueFromLiveNode: function(node, field) {
			if (node[field.key] === undefined) {
				return this.valueFromSchemaDefault(field)
			}
			const value = node[field.key]
			return field.attrs.factor ? value * field.attrs.factor : value
		},
		valueFromSchemaDefault: function(field) {
			if (field.value !== undefined && field.value !== null) {
				return field.value
			}
			return ['multiselect', 'record-list'].includes(field.attrs.type) ? [] : ''
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
		save: async function() {
			this.error = null
			this.saving = true
			try {
				if (this.editNode) {
					const changes = Object.assign({group: this.form.group}, this.form.fields)
					if (this.receivesKind !== 'none') {
						changes.receives = this.asReceivesList()
					}
					this.wiringStore.draftUpdateNode({
						nodeId: this.editNode.id,
						changes: changes,
					})
				} else {
					if (!this.form.type || !this.form.name) {
						this.error = this.$t('pages.wiring.errNameType')
						return
					}
					this.wiringStore.draftCreateNode(Object.assign({
						type: this.form.type,
						role: this.schema.role,
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
registerGlobalComponent('WiringNodeDialog', WiringNodeDialog)

// vim: set noet ts=4 sw=4:
