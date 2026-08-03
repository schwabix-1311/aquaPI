import {registerGlobalComponent} from '../app/registry.js'

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
			<div class="d-flex justify-space-between">
				<span>{{ item.label }}</span>
				<span class="grey--text">{{ localValue }}</span>
			</div>
			<v-slider
				v-model="localValue"
				:min="Number(attrs.min || 0)"
				:max="Number(attrs.max || 100)"
				:step="Number(attrs.step || 1)"
				:disabled="disabled"
				color="primary"
				track-color="primary"
				thumb-label
				hide-details
				@end="onEnd"
			></v-slider>
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
		}
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

const NodeSettingsCard = {
	props: {
		node: {type: Object, required: true}
	},
	template: `
		<v-card outlined tile class="mb-3">
			<v-card-title class="text-subtitle-1 py-2">
				{{ node.name }}
			</v-card-title>
			<v-card-text>
				<div v-if="loading" class="pa-6 text-center">
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
							class="mb-4"
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
			</v-card-text>
		</v-card>
	`,
	data: function() {
		return {
			loading: true,
		}
	},
	computed: {
		settings: function() {
			return this.$store.getters['settings/settingsForNode'](this.node.id)
		},
		error: function() {
			return this.$store.getters['settings/errorForNode'](this.node.id)
		},
	},
	methods: {
		widgetType: settingWidgetType,
		onUpdate: function(item, value) {
			this.$store.dispatch('settings/updateNodeSetting', {
				nodeId: this.node.id,
				key: item.key,
				value: value
			})
		},
	},
	mounted: function() {
		this.loading = true
		this.$store.dispatch('settings/fetchNodeSettings', this.node.id)
			.finally(() => { this.loading = false })
	},
}
registerGlobalComponent('NodeSettingsCard', NodeSettingsCard)

// vim: set noet ts=4 sw=4:
