import {registerGlobalComponent} from '../app/registry.js'
import {useSettingsStore} from '../../store/modules/settings.js'
import {useDashboardStore} from '../../store/modules/dashboard.js'
import {useConfigStore} from '../../store/modules/config.js'
import {useUsersStore} from '../../store/modules/users.js'
import {isHistOrAlert, cardTitle, ancestorsForward, descendants, dedupeFanIn, branchAnchor, realParents} from './chains.js'
import './alertCondEditor.js'
import './escalationEditor.js'

// a Setting is required unless attrs.optional is true, and must not be
// left empty - this is enforced server-side (api.py's _validate_and_cast),
// the client-side rule is just an earlier visual hint before submit.
function requiredRule(item, t) {
	if (item.attrs && item.attrs.optional) {
		return []
	}
	return [v => (Array.isArray(v) ? v.length > 0 : (v !== null && v !== undefined && v !== '')) || t('misc.dialog.valueRequired')]
}

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
			:rules="rules"
			density="compact"
			variant="outlined"
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
		},
		rules: function() {
			return requiredRule(this.item, this.$t)
		},
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
			<div class="d-flex justify-space-between align-end flex-wrap" style="gap: 4px 8px;">
				<span class="text-truncate aquapi-shrinkable">{{ item.label }}</span>
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
					class="text-right text-body-2 aquapi-shrinkable"
					style="flex: 0 0 64px;"
					@change="onChange"
				></v-text-field>
			</div>
			<div class="d-flex align-center" style="gap: 8px;">
				<span class="text-body-2 text-grey aquapi-setting-bound">{{ attrs.min }}</span>
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
				<span class="text-body-2 text-grey text-right aquapi-setting-bound">{{ attrs.max }}</span>
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

// type='duration' Settings always travel the API in seconds (see
// msg_bus.py's Setting.factor/max_unit) - this widget picks the largest
// whole-number-representable unit (see unitCeiling()/bestDurationUnit()
// below) to display/edit in - no persistence needed, recomputed from the
// current value on every mount - with a small dropdown to override it.
// Value/min/max/step are converted for display and converted back to
// seconds before emitting.
const DURATION_UNIT_ORDER = ['s', 'min', 'h', 'day']
const DURATION_FACTORS = {s: 1, min: 60, h: 3600, day: 86400}
// always the plural/generic i18n key - bestDurationUnit() below never
// picks a unit whose value would be exactly 1 (falls back to the next
// smaller unit instead, e.g. 3600s -> "60 min" not "1 hour"), so a
// singular form is never needed except for a genuine 1-second value,
// where it'd read as "1 s" anyway - same text as the plural abbreviation.
const DURATION_I18N_KEY = {s: 'secs', min: 'mins', h: 'hours', day: 'days'}

function bestDurationUnit(seconds, ceiling) {
	const ceilingIdx = DURATION_UNIT_ORDER.indexOf(ceiling || 's')
	for (let i = ceilingIdx; i >= 0; i--) {
		const factor = DURATION_FACTORS[DURATION_UNIT_ORDER[i]]
		// skip a unit that would show as exactly "1" (e.g. 3600s as
		// "1 hour") - drop to the next smaller unit instead, which
		// always reads as a plural amount ("60 min"). The one unavoidable
		// exception is a literal 1-second value, caught by the final
		// `return 's'` fallback below.
		if (seconds % factor === 0 && seconds !== factor) {
			return DURATION_UNIT_ORDER[i]
		}
	}
	return 's'
}

// the largest unit selectable at all for this field: derived from its
// attrs.max itself (e.g. a 600s max reads more easily as "10 min", but
// a 300s max shouldn't offer hours - "0.083 h" helps no one), so it's
// consistent instead of a hand-picked-per-field guess. A field with no
// max at all (e.g. FadeCtrl's fade_time/fade_out) is unbounded upward.
function unitCeiling(attrs) {
	return attrs.max !== undefined ? bestDurationUnit(attrs.max, 'day') : 'day'
}

// formats a seconds bound (min/max) in *its own* best-fit unit with a
// correctly pluralized suffix, independent of whichever unit the value
// itself is currently shown in - e.g. min=0/max=604800 should read
// "0 s"/"7 days" even while the current value happens to display in hours.
// caps the edit field to 4 decimal places (e.g. converting seconds to
// hours can otherwise produce long floating-point tails)
function roundDuration(value) {
	return Math.round(value * 10000) / 10000
}

function formatDurationBound(seconds, ceiling, t) {
	const u = bestDurationUnit(seconds, ceiling)
	return (seconds / DURATION_FACTORS[u]) + ' ' + t('misc.duration.' + DURATION_I18N_KEY[u])
}

const SettingDuration = {
	props: {
		item: {type: Object, required: true},
		disabled: {type: Boolean, default: false},
	},
	template: `
		<div>
			<div class="aquapi-setting-duration-grid">
				<span class="text-truncate aquapi-shrinkable">{{ item.label }}</span>
				<v-text-field
					v-model.number="localValue"
					type="number"
					:step="displayStep || 'any'"
					:disabled="disabled"
					:rules="rules"
					density="compact"
					variant="underlined"
					hide-details
					class="text-right text-body-2"
					@change="onChange"
				></v-text-field>
				<v-select
					v-model="unit"
					:items="unitOptions"
					:disabled="disabled"
					density="compact"
					variant="underlined"
					hide-details
					@update:modelValue="onUnitChange"
				></v-select>
			</div>
			<div v-if="hasRange" class="d-flex align-center" style="gap: 8px;">
				<span class="text-body-2 text-grey aquapi-setting-bound">{{ minLabel }}</span>
				<v-slider
					v-model="localValue"
					:min="displayMin"
					:max="displayMax"
					:step="displayStep || 1"
					:disabled="disabled"
					color="primary"
					track-color="primary"
					density="compact"
					hide-details
					@end="onEnd"
				></v-slider>
				<span class="text-body-2 text-grey text-right aquapi-setting-bound">{{ maxLabel }}</span>
			</div>
		</div>
	`,
	data: function() {
		const unit = bestDurationUnit(this.item.value, unitCeiling(this.item.attrs || {}))
		return {
			unit: unit,
			localValue: roundDuration(this.item.value / DURATION_FACTORS[unit]),
		}
	},
	computed: {
		attrs: function() {
			return this.item.attrs || {}
		},
		rules: function() {
			return requiredRule(this.item, this.$t)
		},
		hasRange: function() {
			return this.attrs.min !== undefined && this.attrs.max !== undefined
		},
		unitOptions: function() {
			const ceilingIdx = DURATION_UNIT_ORDER.indexOf(unitCeiling(this.attrs))
			return DURATION_UNIT_ORDER.slice(0, ceilingIdx + 1).map(u => ({
				title: this.$t('misc.duration.' + DURATION_I18N_KEY[u]),
				value: u,
			}))
		},
		factor: function() {
			return DURATION_FACTORS[this.unit]
		},
		displayMin: function() {
			return this.attrs.min !== undefined ? this.attrs.min / this.factor : undefined
		},
		displayMax: function() {
			return this.attrs.max !== undefined ? this.attrs.max / this.factor : undefined
		},
		displayStep: function() {
			return this.attrs.step !== undefined ? this.attrs.step / this.factor : undefined
		},
		// min/max shown beside the slider use their own best-fit unit
		// (capped by the same ceiling as the value's unit dropdown), not
		// necessarily the currently selected display unit - see
		// formatDurationBound() above.
		minLabel: function() {
			return this.attrs.min !== undefined
				? formatDurationBound(this.attrs.min, unitCeiling(this.attrs), this.$t) : ''
		},
		maxLabel: function() {
			return this.attrs.max !== undefined
				? formatDurationBound(this.attrs.max, unitCeiling(this.attrs), this.$t) : ''
		},
	},
	watch: {
		'item.value': function(val) {
			this.localValue = roundDuration(val / this.factor)
		}
	},
	methods: {
		onUnitChange: function(newUnit) {
			// re-derive from item.value (the canonical seconds value), not
			// from the currently displayed/rounded localValue, to avoid drift
			this.localValue = roundDuration(this.item.value / DURATION_FACTORS[newUnit])
		},
		onEnd: function(val) {
			this.$emit('update', val * this.factor)
		},
		onChange: function() {
			this.$emit('update', parseFloat(this.localValue) * this.factor)
		},
	}
}
registerGlobalComponent('SettingDuration', SettingDuration)

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
			color="primary"
			density="compact"
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
		// v-switch's plain @change is a native-DOM-change alias, not a
		// documented custom event with a reliable value argument (unlike
		// e.g. v-slider's @end) - v-model has already updated localValue
		// correctly by the time this fires, so use that instead of
		// trusting whatever @change's own argument happens to be.
		onChange: function() {
			this.$emit('update', this.localValue)
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
			density="compact"
			variant="outlined"
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
			:rules="rules"
			density="compact"
			variant="outlined"
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
		rules: function() {
			return requiredRule(this.item, this.$t)
		},
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

const SettingSelect = {
	props: {
		item: {type: Object, required: true},
		disabled: {type: Boolean, default: false},
	},
	template: `
		<v-select
			:label="item.label"
			v-model="localValue"
			:items="attrs.options || []"
			:disabled="disabled"
			:rules="rules"
			density="compact"
			variant="outlined"
			hide-details="auto"
			@update:modelValue="onChange"
		></v-select>
	`,
	data: function() {
		return {
			localValue: this.item.value
		}
	},
	computed: {
		attrs: function() {
			return this.item.attrs || {}
		},
		rules: function() {
			return requiredRule(this.item, this.$t)
		},
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
registerGlobalComponent('SettingSelect', SettingSelect)

const SettingMultiSelect = {
	props: {
		item: {type: Object, required: true},
		disabled: {type: Boolean, default: false},
	},
	template: `
		<v-select
			:label="item.label"
			v-model="localValue"
			:items="attrs.options || []"
			:disabled="disabled"
			:rules="rules"
			multiple chips
			density="compact"
			variant="outlined"
			hide-details="auto"
			@update:modelValue="onChange"
		></v-select>
	`,
	data: function() {
		return {
			localValue: this.item.value || []
		}
	},
	computed: {
		attrs: function() {
			return this.item.attrs || {}
		},
		rules: function() {
			return requiredRule(this.item, this.$t)
		},
	},
	watch: {
		'item.value': function(val) {
			this.localValue = val || []
		}
	},
	methods: {
		onChange: function() {
			this.$emit('update', this.localValue)
		}
	}
}
registerGlobalComponent('SettingMultiSelect', SettingMultiSelect)

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
	if (attrs.type === 'duration') {
		return 'SettingDuration'
	}
	if (attrs.type === 'select') {
		return 'SettingSelect'
	}
	if (attrs.type === 'multiselect') {
		return 'SettingMultiSelect'
	}
	return 'SettingText'
}

// Selects/multiselects (long option text, chips) and the schedule field
// (carries a persistent hint line) get more breathing room than the default
// 3-per-row grid used by compact fields like sliders/numbers/switches.
function settingColSpan(item, node) {
	// port selects (item.key === 'port', regardless of label - inputPort/
	// outputPort/alertPort all share this key, see PortDriverMixin) list
	// short option text (e.g. "GPIO 12 out") - no need for the wider
	// column reserved for genuinely long content like other selects'
	// option text or multiselect chips.
	if (item.key === 'port' && node.role === 'ALERTS') {
		// alertPort ("Sende an") sits right above EscalationEditor's own
		// "Eskalieren an" select (escalationEditor.js, fixed 220px) - an
		// even narrower column than other ports, to line the two up:
		// "Email #1"/"Telegram #1" are shorter than typical GPIO/PWM/ADC
		// port names, so the standard port column would just be wasted
		// space here.
		return {cols: 12, sm: 6, md: 2}
	}
	const wide = item.key !== 'port'
		&& ['SettingSelect', 'SettingMultiSelect', 'SettingSchedule'].includes(settingWidgetType(item))
	return wide ? {cols: 12, md: 6} : {cols: 12, sm: 6, md: 4}
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
						v-bind="colSpan(item, node)"
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
		// item.label arrives from the backend as a short i18n key (e.g.
		// 'setpoint'), not display text - resolved here once, centrally,
		// so none of the individual Setting* widget components below need
		// to know about i18n at all, they just render item.label as-is.
		//
		// Exception: UiSwitchInput/UiAnalogInput's own control ('value')
		// mirrors their Dashboard widgets (dashboard/comps.js's
		// settingItem computeds), which label it with the node's own
		// name rather than a generic translated word - the control *is*
		// the node, there's nothing else to distinguish it by.
		//
		// The read-only 'receives' entry (key===null, the only Setting(None,
		// ...) in the whole backend, msg_bus.py's BusListener.get_settings())
		// is unconditionally filtered out here: with 1 real parent, tree
		// position already says it unambiguously; with 0 (a root) it's
		// trivially uninformative; with 2+ it's covered by NodeSettingsTree's
		// explicit fan-in note instead of a raw field. So it never needs to
		// render as its own field anywhere anymore.
		settings: function() {
			const ownControlTypes = ['UiSwitchInput', 'UiAnalogInput']
			return this.settingsStore.settingsForNode(this.node.id)
				.filter(item => !(item.key === null && item.label === 'receives'))
				.map(item => ({
					...item,
					label: (ownControlTypes.includes(this.node.type) && item.key === 'value')
						? this.node.name
						: this.$t('pages.settings.fields.' + item.label, item.labelParams || {}),
				}))
		},
		error: function() {
			return this.settingsStore.errorForNode(this.node.id)
		},
	},
	methods: {
		widgetType: settingWidgetType,
		colSpan: settingColSpan,
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
		<setting-multi-select
			:item="pseudoSetting"
			:disabled="saving || !isAdmin"
			@update="onChange"
		></setting-multi-select>
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
		usersStore() {
			return useUsersStore()
		},
		isAdmin() {
			// PUT /api/nodes/<id> (what updateNode() below hits) is
			// admin-only, unlike the regular settings fields on this same
			// page (operator+admin) - gate this one control separately
			return this.usersStore.isAdmin
		},
		receivesItems: function() {
			return Object.values(this.dashboardStore.nodes)
				.filter(n => n.id !== this.node.id)
				.map(n => ({title: n.name + ' (' + n.type + ')', value: n.id}))
		},
		pseudoSetting: function() {
			return {
				key: 'receives',
				label: this.$t('pages.settings.inputs'),
				value: this.selected,
				attrs: {
					options: this.receivesItems,
				},
			}
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

// Renders one level of a descendants()/ancestors()-shaped {node,children}
// tree (after dedupeFanIn() for descendants) as a real nested <ul>/<li>
// tree with hop-distance indentation and per-item "elbow" connectors (see
// app.css's .aquapi-chain-tree rules) - recurses into itself for each
// level, replacing the old flattenEntries()-based flat depth=1 list.
const NodeSettingsTree = {
	name: 'NodeSettingsTree',
	props: {
		entries: {type: Array, required: true},        // [{node, children, merged?}]
		depth: {type: Number, default: 1},
		// true for the outermost <ul> directly under an "Eingänge"/
		// "Ausgänge" heading - no tree row above it to connect an upward
		// stub into.
		flat: {type: Boolean, default: false},
		// non-null once this recursion is inside a branch that was given
		// its own local anchor further up (see branchFor()) - null at the
		// very top and everywhere outside any fan-out point.
		branchAnchorId: {type: String, default: null},
		branchIsCtrl: {type: Boolean, default: false},
	},
	template: `
		<ul class="aquapi-chain-tree"
			:class="{'aquapi-chain-tree--flat': flat, 'aquapi-chain-tree--muted': branchAnchorId && !branchIsCtrl}"
		>
			<li v-for="entry in entries" :key="entry.node.id"
				class="aquapi-chain-tree__item"
				:class="{'aquapi-chain-tree__item--muted': entry.merged || (branchAnchorId && !branchIsCtrl)}"
			>
				<template v-if="entry.merged">
					<div class="d-flex align-center text-body-2 text-grey">
						<v-icon size="small" class="mr-1">mdi-call-merge</v-icon>
						{{ entry.node.name }}
					</div>
					<div class="text-caption text-grey">
						⑂ {{ $t('pages.settings.fields.receives') }}: {{ parentNames(entry.node) }}
					</div>
				</template>
				<template v-else>
					<div class="aquapi-chain-tree__anchor-badge" :class="badgeClass(entry)">
						{{ entry.node.name }}
					</div>
					<node-settings-fields :node="entry.node"></node-settings-fields>
					<div v-if="parents(entry.node).length > 1" class="text-caption text-grey">
						⑂ {{ $t('pages.settings.fields.receives') }}: {{ parentNames(entry.node) }}
					</div>
					<div v-if="isBranchHead(entry) && !branchFor(entry).isCtrl" class="text-caption text-grey font-italic">
						{{ $t('pages.settings.noControllerInBranch') }}
					</div>
				</template>

				<node-settings-tree
					v-if="entry.children.length"
					:entries="entry.children"
					:depth="depth + 1"
					:branch-anchor-id="branchContext(entry).id"
					:branch-is-ctrl="branchContext(entry).isCtrl"
				></node-settings-tree>
			</li>
		</ul>
	`,
	computed: {
		dashboardStore() {
			return useDashboardStore()
		},
	},
	methods: {
		parents(node) {
			return realParents(node, this.dashboardStore.nodes)
		},
		parentNames(node) {
			return this.parents(node).map(n => n.name).join(', ')
		},
		// a fresh fan-out point (2+ real siblings at THIS list) gives every
		// sibling its own new local anchor; a lone child just inherits
		// whatever branch context is already in effect from further up.
		branchFor(entry) {
			if (this.entries.length > 1) {
				return branchAnchor(entry)
			}
			return this.branchAnchorId ? {node: {id: this.branchAnchorId, name: ''}, isCtrl: this.branchIsCtrl} : null
		},
		isBranchHead(entry) {
			const b = this.branchFor(entry)
			return !!b && b.node.id === entry.node.id
		},
		// every node gets the pill label - strong (filled) at a real Ctrl
		// branch head, soft (dashed) at a Ctrl-less branch head, plain
		// (neutral) everywhere else, i.e. any node that's just continuing
		// a chain rather than itself being a branch's own focal point.
		badgeClass(entry) {
			if (this.isBranchHead(entry)) {
				return this.branchFor(entry).isCtrl
					? 'aquapi-chain-tree__anchor-badge--ctrl'
					: 'aquapi-chain-tree__anchor-badge--soft'
			}
			return 'aquapi-chain-tree__anchor-badge--plain'
		},
		// what to hand down to this entry's own children: a NEW branch
		// context if this entry is itself one of 2+ siblings, else
		// whatever's already in effect, unchanged.
		branchContext(entry) {
			if (this.entries.length > 1) {
				const b = branchAnchor(entry)
				return {id: b.node.id, isCtrl: b.isCtrl}
			}
			return {id: this.branchAnchorId, isCtrl: this.branchIsCtrl}
		},
	},
}
registerGlobalComponent('NodeSettingsTree', NodeSettingsTree)

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
				<template v-if="anchor.role === 'ALERTS'">
					<alert-cond-editor :node="anchor" class="mb-4"></alert-cond-editor>
					<node-settings-fields :node="anchor"></node-settings-fields>
					<escalation-editor :node="anchor"></escalation-editor>
				</template>
				<template v-else>
					<template v-if="anchor.role === 'HISTORY'">
						<node-settings-fields :node="anchor"></node-settings-fields>
						<node-receives-editor :node="anchor"></node-receives-editor>
					</template>
					<template v-else>
						<node-settings-tree v-if="inputs.length" :entries="inputs" :depth="1" flat></node-settings-tree>
						<div v-if="anchor.role === 'CTRL'" class="aquapi-chain-tree__anchor-badge aquapi-chain-tree__anchor-badge--ctrl">
							{{ anchor.name }}
						</div>
						<node-settings-fields :node="anchor"></node-settings-fields>
						<node-settings-tree v-if="outputs.length" :entries="outputs" :depth="1" flat></node-settings-tree>
					</template>
				</template>
			</v-card-text>
		</v-card>
	`,
	computed: {
		dashboardStore() {
			return useDashboardStore()
		},
		// cardTitle() picks chainAnchor()'s single-CTRL result for a plain,
		// unbranching chain (same as before), or the root itself for any
		// chain with a real fan-out anywhere - see chains.js.
		anchor: function() {
			return cardTitle(this.node, this.dashboardStore.nodes)
		},
		// ancestorsForward() walks root(s)-first toward the anchor (see
		// chains.js) - matches the reading direction used for `outputs`
		// below (closer-to-anchor = less nested). isPlainChain() only
		// guarantees no fan-OUT anywhere in this chain, not no fan-IN - two
		// sensors merging into one AvgAux upstream of a single Ctrl is
		// still "plain" (one purpose, titled by that Ctrl) but genuinely
		// has 2 real parents at the merge point, so this still needs
		// dedupeFanIn() same as outputs.
		inputs: function() {
			return dedupeFanIn(ancestorsForward(this.anchor, this.dashboardStore.nodes))
		},
		// Computed from this.anchor, not this.node (the root) as before:
		// for a plain chain, anchor is chainAnchor()'s downstream pick and
		// this is just "the rest of the chain past the headline" (same as
		// today). For a branching component, cardTitle() already forces
		// anchor === this.node (the root itself) - so this naturally
		// becomes the whole component's real descendant tree, replacing the
		// old "walk from root, then subtract anchor+ancestors as the spine"
		// workaround entirely: that workaround only ever existed to route
		// around exactly the branching case, which now picks the root as
		// its own anchor up front instead of re-centering on a downstream
		// CTRL, so there's no spine left to subtract.
		outputs: function() {
			return dedupeFanIn(descendants(this.anchor, this.dashboardStore.nodes))
		},
	},
	methods: {
		isHistOrAlert,
	},
}
registerGlobalComponent('NodeSettingsCard', NodeSettingsCard)

// vim: set noet ts=4 sw=4:
