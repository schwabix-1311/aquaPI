import {registerGlobalComponent} from '../app/registry.js'
import {useSettingsStore} from '../../store/modules/settings.js'
import {useDashboardStore} from '../../store/modules/dashboard.js'
import {useConfigStore} from '../../store/modules/config.js'
import {isHistOrAlert, chainAnchor, ancestors, descendants, flattenEntries} from './chains.js'

const SettingNumber = {
	props: {
		item: {type: Object, required: true},
		disabled: {type: Boolean, default: false},
	},
	template: `
		<v-text-field
			:label="item.label"
			v-model.number="localValue"
			type="number"
			:min="attrs.min"
			:max="attrs.max"
			:step="attrs.step || 'any'"
			:disabled="disabled"
			dense
			outlined
			hide-details="auto"
			@change="onChange"
		></v-text-field>
	`,
	data: function() {
		return {
			localValue: this.item.value
		}
	},
	computed: {
		attrs: function() {
			return this.item.attrs || {}
		}
	},
	watch: {
		'item.value': function(val) {
			this.localValue = val
		}
	},
	methods: {
		onChange: function() {
			this.$emit('update', parseFloat(this.localValue))
		}
	}
}
registerGlobalComponent('SettingNumber', SettingNumber)

const SettingSlider = {
	props: {
		item: {type: Object, required: true},
		disabled: {type: Boolean, default: false},
	},
	template: `
		<div>
			<div class="d-flex justify-space-between align-center">
				<span>{{ item.label }}</span>
				<v-text-field
					v-model.number="localValue"
					type="number"
					:min="attrs.min"
					:max="attrs.max"
					:step="attrs.step || 'any'"
					:disabled="disabled"
					density="compact"
					variant="underlined"
					hide-details
					class="text-right text-body-2"
					style="max-width: 72px;"
					@change="onChange"
				></v-text-field>
			</div>
			<div class="d-flex align-center" style="gap: 8px;">
				<span class="text-body-2 text-grey" style="min-width: 2em;">{{ attrs.min }}</span>
				<v-slider
					v-model="localValue"
					:min="Number(attrs.min || 0)"
					:max="Number(attrs.max || 100)"
					:step="Number(attrs.step || 1)"
					:disabled="disabled"
					color="primary"
					track-color="primary"
					density="compact"
					hide-details
					@end="onEnd"
				></v-slider>
				<span class="text-body-2 text-grey text-right" style="min-width: 2em;">{{ attrs.max }}</span>
			</div>
		</div>
	`,
	data: function() {
		return {
			localValue: this.item.value
		}
	},
	computed: {
		attrs: function() {
			return this.item.attrs || {}
		}
	},
	watch: {
		'item.value': function(val) {
			this.localValue = val
		}
	},
	methods: {
		onEnd: function(val) {
			this.$emit('update', val)
		},
		onChange: function() {
			this.$emit('update', parseFloat(this.localValue))
		},
	}
}
registerGlobalComponent('SettingSlider', SettingSlider)

const SettingSwitch = {
	props: {
		item: {type: Object, required: true},
		disabled: {type: Boolean, default: false},
	},
	template: `
		<v-switch
			:label="item.label"
			v-model="localValue"
			:disabled="disabled"
			dense
			hide-details
			@change="onChange"
		></v-switch>
	`,
	data: function() {
		return {
			localValue: !!this.item.value
		}
	},
	watch: {
		'item.value': function(val) {
			this.localValue = !!val
		}
	},
	methods: {
		onChange: function(val) {
			this.$emit('update', !!val)
		}
	}
}
registerGlobalComponent('SettingSwitch', SettingSwitch)

const SettingSchedule = {
	props: {
		item: {type: Object, required: true},
		disabled: {type: Boolean, default: false},
	},
	template: `
		<v-text-field
			:label="item.label"
			v-model="localValue"
			:disabled="disabled"
			dense
			outlined
			:hint="$t('pages.settings.scheduleHint')"
			persistent-hint
			@change="onChange"
		></v-text-field>
	`,
	data: function() {
		return {
			localValue: this.item.value
		}
	},
	watch: {
		'item.value': function(val) {
			this.localValue = val
		}
	},
	methods: {
		onChange: function() {
			this.$emit('update', this.localValue)
		}
	}
}
registerGlobalComponent('SettingSchedule', SettingSchedule)

const SettingText = {
	props: {
		item: {type: Object, required: true},
		disabled: {type: Boolean, default: false},
	},
	template: `
		<v-text-field
			:label="item.label"
			v-model="localValue"
			:disabled="disabled"
			dense
			outlined
			hide-details="auto"
			@change="onChange"
		></v-text-field>
	`,
	data: function() {
		return {
			localValue: this.item.value
		}
	},
	watch: {
		'item.value': function(val) {
			this.localValue = val
		}
	},
	methods: {
		onChange: function() {
			this.$emit('update', this.localValue)
		}
	}
}
registerGlobalComponent('SettingText', SettingText)

const SettingReadonly = {
	props: {
		item: {type: Object, required: true},
	},
	template: `
		<div>
			<div class="grey--text text-caption">{{ item.label }}</div>
			<div>{{ item.value }}</div>
		</div>
	`
}
registerGlobalComponent('SettingReadonly', SettingReadonly)

function settingWidgetType(item) {
	if (!item.editable) {
		return 'SettingReadonly'
	}
	if (item.key === 'cronspec') {
		return 'SettingSchedule'
	}

	const attrs = item.attrs || {}
	if (attrs.type === 'checkbox') {
		return 'SettingSwitch'
	}
	if (attrs.type === 'number') {
		return (attrs.min !== undefined && attrs.max !== undefined) ? 'SettingSlider' : 'SettingNumber'
	}
	return 'SettingText'
}

// The settings-grid renderer for a single node - reusable both for a
// chain's anchor (depth 0) and for each nested Eingänge/Ausgänge member
// (depth > 0, with a small sub-heading identifying which node the fields
// below belong to).
const NodeSettingsFields = {
	props: {
		node: {type: Object, required: true},
		depth: {type: Number, default: 0},
	},
	template: `
		<div>
			<div v-if="depth > 0" class="d-flex align-center text-subtitle-2 mb-1 mt-3">
				<v-icon size="small" class="mr-1">mdi-subdirectory-arrow-right</v-icon>
				{{ node.name }}
			</div>
			<div v-if="loading" class="pa-4 text-center">
				<aquapi-loading-indicator></aquapi-loading-indicator>
			</div>
			<v-alert v-else-if="error && !settings.length" type="error" text dense>
				{{ error }}
			</v-alert>
			<template v-else>
				<v-alert v-if="error" type="error" text dense class="mb-2">
					{{ error }}
				</v-alert>
				<v-row>
					<v-col
						v-for="(item, idx) in settings"
						:key="node.id + '.' + (item.key || idx)"
						cols="12" sm="6" md="4"
						class="mb-2"
					>
						<component
							:is="widgetType(item)"
							:item="item"
							:disabled="!item.editable"
							@update="onUpdate(item, $event)"
						></component>
					</v-col>
				</v-row>
			</template>
		</div>
	`,
	data: function() {
		return {
			loading: true,
		}
	},
	computed: {
		settingsStore() {
			return useSettingsStore()
		},
		settings: function() {
			return this.settingsStore.settingsForNode(this.node.id)
		},
		error: function() {
			return this.settingsStore.errorForNode(this.node.id)
		},
	},
	methods: {
		widgetType: settingWidgetType,
		async onUpdate(item, value) {
			const ok = await this.settingsStore.updateNodeSetting({
				nodeId: this.node.id,
				key: item.key,
				value: value
			})
			if (ok) {
				this.$toast.success(this.$t('misc.toast.saveSuccess'))
			} else {
				this.$toast.error(this.error || this.$t('misc.toast.saveError'))
			}
		},
	},
	mounted: function() {
		this.loading = true
		this.settingsStore.fetchNodeSettings(this.node.id)
			.finally(() => { this.loading = false })
	},
}
registerGlobalComponent('NodeSettingsFields', NodeSettingsFields)

// HISTORY/ALERTS nodes don't get a nested Eingänge tree (see chains.js) -
// instead, a quick multi-select for their `receives` directly, mirroring
// the /config page's own node-edit dialog (config/comps.js's `receivesKind`/
// `receivesItems` pattern) and reusing its exact save mechanism
// (configStore.updateNode -> PUT /api/nodes/<id>), not the settings API.
const NodeReceivesEditor = {
	props: {
		node: {type: Object, required: true},
	},
	template: `
		<v-select
			v-model="selected"
			:items="receivesItems"
			multiple chips
			:label="$t('pages.settings.inputs')"
			outlined dense
			:loading="saving"
			@update:modelValue="onChange"
		></v-select>
	`,
	data: function() {
		return {
			selected: (this.node.receives || []).filter(id => id !== '*'),
			saving: false,
		}
	},
	computed: {
		configStore() {
			return useConfigStore()
		},
		dashboardStore() {
			return useDashboardStore()
		},
		receivesItems: function() {
			return Object.values(this.dashboardStore.nodes)
				.filter(n => n.id !== this.node.id)
				.map(n => ({title: n.name + ' (' + n.type + ')', value: n.id}))
		},
	},
	watch: {
		'node.receives': function(val) {
			this.selected = (val || []).filter(id => id !== '*')
		},
	},
	methods: {
		async onChange(value) {
			this.saving = true
			const result = await this.configStore.updateNode({
				nodeId: this.node.id,
				changes: {receives: value},
			})
			this.saving = false
			if (result.ok) {
				this.$toast.success(this.$t('misc.toast.saveSuccess'))
			} else {
				this.selected = (this.node.receives || []).filter(id => id !== '*')
				this.$toast.error(result.error || this.$t('misc.toast.saveError'))
			}
		},
	},
	mounted: function() {
		this.configStore.fetchNodeTypes()
	},
}
registerGlobalComponent('NodeReceivesEditor', NodeReceivesEditor)

// Orchestrates one root's whole card: resolves the chain's display anchor
// (see chains.js), then either the HISTORY/ALERTS receives-combobox, or the
// anchor's own fields plus nested Eingänge (upstream)/Ausgänge (downstream)
// sections built from the same chain-walking logic index.js uses for
// root-finding.
const NodeSettingsCard = {
	props: {
		node: {type: Object, required: true}
	},
	template: `
		<v-card variant="outlined" elevation="3" tile class="mb-3" style="border-color: rgba(0,0,0,0.3);">
			<v-card-title class="text-subtitle-1 py-2">
				{{ anchor.name }}<span v-if="isHistOrAlert(anchor)" class="text-body-2 text--secondary"> ({{ $t('misc.nodeTypes.' + anchor.role.toLowerCase()) }})</span>
			</v-card-title>
			<v-card-text>
				<node-settings-fields :node="anchor"></node-settings-fields>

				<node-receives-editor v-if="isHistOrAlert(anchor)" :node="anchor"></node-receives-editor>

				<template v-else>
					<template v-if="inputs.length">
						<div class="text-overline mt-2">{{ $t('pages.settings.inputs') }}</div>
						<node-settings-fields
							v-for="inputNode in inputs"
							:key="inputNode.id"
							:node="inputNode"
							:depth="1"
						></node-settings-fields>
					</template>
					<template v-if="outputs.length">
						<div class="text-overline mt-2">{{ $t('pages.settings.outputs') }}</div>
						<node-settings-fields
							v-for="outputNode in outputs"
							:key="outputNode.id"
							:node="outputNode"
							:depth="1"
						></node-settings-fields>
					</template>
				</template>
			</v-card-text>
		</v-card>
	`,
	computed: {
		dashboardStore() {
			return useDashboardStore()
		},
		anchor: function() {
			return chainAnchor(this.node, this.dashboardStore.nodes)
		},
		// flattened (not deeply indented - NodeSettingsFields' own depth=1
		// sub-heading is enough) since NodeSettingsFields expects a plain
		// node, not a {node, children} entry
		inputs: function() {
			return flattenEntries(ancestors(this.anchor, this.dashboardStore.nodes))
		},
		outputs: function() {
			return flattenEntries(descendants(this.anchor, this.dashboardStore.nodes))
		},
	},
	methods: {
		isHistOrAlert,
	},
}
registerGlobalComponent('NodeSettingsCard', NodeSettingsCard)

// vim: set noet ts=4 sw=4:
