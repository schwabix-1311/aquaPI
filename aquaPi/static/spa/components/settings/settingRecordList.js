// Generic widget for a Setting of type='record-list': a value that is a
// list of records, each described by the entry's nested `attrs.recordSchema`
// (itself a list of Setting.to_dict() dicts). Renders one add/removable
// row per record and one inner Setting* widget per sub-field, recursing
// through settingWidgetType(). Emits @update with the whole new array.
//
// Used both by NodeSettingsFields (/parameters, immediate PUT) and by
// WiringNodeDialog (/wiring, staged into the draft) - the first user is
// Alert.conditions. Pure row helpers live in ./recordListRows.js.

import {registerGlobalComponent} from '../app/registry.js'
import {useDashboardStore} from '../../store/modules/dashboard.js'
import {useWiringStore} from '../../store/modules/wiring.js'
import {isNumericSource, isUsableSource} from '../wiring/wiringConnect.js'
import {settingWidgetType} from './comps.js'
import {subFieldsOf, emptyRow, rowsFromValue, stripRows, nodeFilterFor} from './recordListRows.js'

const SettingRecordList = {
	props: {
		item: {type: Object, required: true},
		disabled: {type: Boolean, default: false},
		ownerNodeId: {type: String, default: null},
	},
	template: `
		<div class="setting-record-list">
			<div class="text-caption grey--text mb-1">{{ item.label }}</div>
			<div v-if="!localRows.length" class="text-caption grey--text mb-2">
				{{ $t('misc.recordList.empty') }}
			</div>
			<div v-for="(row, ri) in localRows" :key="row._key"
				class="d-flex align-center mb-2" style="gap: 8px; flex-wrap: wrap;">
				<component
					v-for="sf in subFields" :key="sf.key"
					:is="widgetType(subItemFor(row, sf))"
					:item="subItemFor(row, sf)"
					:disabled="disabled"
					:style="{flex: isSelect(sf) ? '1 1 150px' : '0 1 110px', minWidth: 0}"
					@update="onCell(ri, sf.key, $event)"
				></component>
				<v-btn icon variant="text" size="small" color="grey-darken-1"
					class="flex-shrink-0" :disabled="disabled"
					:title="$t('misc.recordList.remove')" @click="removeRow(ri)">
					<v-icon size="small">mdi-delete</v-icon>
				</v-btn>
			</div>
			<v-btn variant="text" size="small" :disabled="disabled" @click="addRow">
				<v-icon start size="small">mdi-plus</v-icon>{{ $t('misc.recordList.add') }}
			</v-btn>
		</div>
	`,
	data() {
		return {
			localRows: rowsFromValue(this.item.value, subFieldsOf(this.item)),
		}
	},
	computed: {
		dashboardStore() { return useDashboardStore() },
		wiringStore() { return useWiringStore() },
		subFields() { return subFieldsOf(this.item) },
	},
	watch: {
		'item.value': function(val) {
			// re-seed only when the incoming value genuinely differs from
			// what we'd emit, so a server echo of our own edit doesn't
			// clobber in-progress typing
			if (JSON.stringify(stripRows(this.localRows, this.subFields))
				!== JSON.stringify(val || [])) {
				this.localRows = rowsFromValue(val, this.subFields)
			}
		},
	},
	methods: {
		widgetType(subItem) {
			return settingWidgetType(subItem)
		},
		isSelect(sf) {
			return (sf.attrs || {}).type === 'select'
		},
		nodeOptions(filter) {
			const pred = filter === 'numeric' ? isNumericSource
				: filter === 'usable' ? isUsableSource
					: () => true
			return Object.values(this.dashboardStore.nodes)
				.filter(n => n.id !== this.ownerNodeId && pred(n, this.wiringStore.nodeTypes))
				.map(n => ({title: n.name + ' (' + n.type + ')', value: n.id}))
		},
		subItemFor(row, sf) {
			const attrs = Object.assign({}, sf.attrs)
			const nf = nodeFilterFor(sf, row)
			if (nf) {
				attrs.options = this.nodeOptions(nf)
			} else if (attrs.optionLabelPrefix && Array.isArray(attrs.options)) {
				attrs.options = attrs.options.map(v => ({
					title: this.$t(attrs.optionLabelPrefix + v), value: v,
				}))
			}
			return {
				key: sf.key,
				label: this.$t('pages.settings.fields.' + sf.label),
				value: row[sf.key],
				attrs,
				editable: true,
			}
		},
		emitUpdate() {
			this.$emit('update', stripRows(this.localRows, this.subFields))
		},
		onCell(ri, key, val) {
			this.localRows[ri][key] = val
			this.emitUpdate()
		},
		addRow() {
			this.localRows.push(emptyRow(this.subFields))
			this.emitUpdate()
		},
		removeRow(ri) {
			this.localRows.splice(ri, 1)
			this.emitUpdate()
		},
	},
}
registerGlobalComponent('SettingRecordList', SettingRecordList)

// vim: set noet ts=4 sw=4:
