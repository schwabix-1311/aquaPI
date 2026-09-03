// TODO: more details on dashboard widget? Design/Layout? Colors? Icons? Edit settings?
// TODO: add 'zoom' / modal mode for charts
// TODO: change masonry direction, if possible; maybe use other masonry plugin

import {AQUAPI_EVENTS, EventBus} from '../app/EventBus.js';
import {registerGlobalComponent} from '../app/registry.js';
import {useUiStore} from '../../store/modules/ui.js';
import {useDashboardStore} from '../../store/modules/dashboard.js';
import {useSettingsStore} from '../../store/modules/settings.js';
import {formatDuration} from '../settings/comps.js';

const AnyNode = {
	props: {
		id: String,
		node: {
			type: Object
		},
		addNodeTitle: {
			type: Boolean,
			default: true
		},
		level: {
			type: Number,
			default: 1,
			required: true
		}
	},
	template: `
		<div style="border:1px dashed blue;">
			(AnyNode)<br>
			id: {{ id }}<br>
			node: {{ node }}
		</div>
	`,

	data() {
		return {}
	},

	computed: {
		dashboardStore() {
			return useDashboardStore()
		},
		descript() {
			return ''  // just a sample
		},
		label() {
			let node = this.node
			switch (node.data_range) {
				case 'ANALOG':
				case 'BINARY':
				case 'PERCENT':
				case 'CRONSPEC':
				case 'STRING':
					return this.$t('misc.dataRange.' + node.data_range.toLowerCase() + '.label')
				default:
					return this.$t('misc.dataRange.default.label')
			}

			return node.data_range
		},
		value() {
			let node = this.node
			switch (node.data_range) {
				case 'ANALOG':
				case 'PERCENT':
					return node.data.toFixed(2).toString() + (node.unit ? ' ' + node.unit : '')
				case 'BINARY':
					// return '<i aria-hidden="true" class="v-icon notranslate v-icon--left mdi mdi-chart-line theme--light blue-grey--text text--lighten-4"></i>'
					return (node.data > 0
							? this.$t('misc.dataRange.' + node.data_range.toLowerCase() + '.value.on')
							: this.$t('misc.dataRange.' + node.data_range.toLowerCase() + '.value.off')
					)
				default:
					return node.data
			}

			return node.data
		},
		receivesNodes() {
			const node = this.node
			let nodes = []

			node.receives.forEach(id => {
				if (id !== '*') {
					nodes.push(this.dashboardStore.node(id))
				}
			})

			return nodes
		},
	},
	methods: {
		humanPeriod(val) {
			let value = (val / 60 / 1000)
			let duration = (value == 1) ? this.$t('misc.duration.min')
										: this.$t('misc.duration.mins')
			if (value >= 60) {
				value /= 60
				duration = (value == 1) ? this.$t('misc.duration.hour')
										: this.$t('misc.duration.hours')
				if (value >= 24) {
					value /= 24
					duration = (value == 1) ? this.$t('misc.duration.day')
											: this.$t('misc.duration.days')
					if (value >= 365) {
						value /= 365
						duration = (value == 1) ? this.$t('misc.duration.year')
												: this.$t('misc.duration.years')
					} else if (value >= 182) {
						return this.$t('misc.duration.halfYear')
					} else if (value >= 30) {
						value /= 30
						duration = (value == 1) ? this.$t('misc.duration.month')
												: this.$t('misc.duration.months')
					}
				}
			}
			return `${value} ${duration}`
		},
	},
}
registerGlobalComponent('AnyNode', AnyNode)  //??

const DebugNode = {
	extends: AnyNode,
	template: `
		<div style="border: 1px solid red;">
			<h2>
				{{ id }} - raw:
			</h2>
			<div class="pa-2">
				{{ node }}
			</div>
		</div>
	`
}
registerGlobalComponent('DebugNode', DebugNode)


const BusNode = {
	extends: AnyNode,
	template: `
		<div>
			<v-card-title
				v-if="addNodeTitle"
			>
				{{ node.name }}
			</v-card-title>
			<template
				v-if="true"
			>
				<aquapi-node-description
					:item="node"
				>
				</aquapi-node-description>
				<v-card-text
					class="text--secondary"
				>
					<aquapi-node-data
						:item="node"
					>
						<template v-slot:label>
							<span>{{ label }}</span>
						</template>
						<template v-slot:value>
							<span>{{ value }}</span>
						</template>
					</aquapi-node-data>
				</v-card-text>
			</template>
			
			<template
				v-if="receivesNodes.length > 0"
			>
				<v-expansion-panels
					v-if="level == 1"
					multiple
					v-model="openPanels"
					tile
				>
					<v-expansion-panel>
						<v-expansion-panel-title
							class="py-0 px-4 text-caption"
						>
							{{ $t('dashboard.widget.inputs.label') }}
						</v-expansion-panel-title>
						<v-expansion-panel-text>
							<v-card
								v-for="(item, index) in receivesNodes"
								:key="item.identifier"
								variant="outlined"
								tile
								class="ma-3 mt-0"
							>
								<component
									v-if="item"
									:is="item.type"
									:id="item.identifier"
									:node="item"
									:level="(level + 1)"
								></component>
								<v-card-text v-else class="red--text">
									{{ $t('dashboard.widget.elementNotFound') }}
								</v-card-text>
							</v-card>
						</v-expansion-panel-text>
					</v-expansion-panel>
				</v-expansion-panels>
				
				<div v-else class="mt-2">
					<v-card
						v-for="(item, index) in receivesNodes"
						:key="item.identifier"
						variant="outlined"
						tile
						class="ma-3 mt-0"
					>
						<component
							v-if="item"
							:is="item.type"
							:id="item.identifier"
							:node="item"
							:level="(level + 1)"
						></component>
						<v-card-text v-else class="red--text">
							{{ $t('dashboard.widget.elementNotFound') }}
						</v-card-text>
					</v-card>
				</div>
			</template>
		</div>
	`,

	data() {
		return {
			openPanels: [],
		}
	},
	computed: {},
}
//Vue.component('BusNode', BusNode)  //??

//TODO: do we need Vue.components that are purely abstract? Would it save anything?
//TODO: do we need derived nodes W/O any functional change? 


const ControllerNode = {
	extends: BusNode,
	computed: {
		// only append rcv_unit when the setpoint is a numeric value - for
		// BINARY/PERCENT controllers the setpoint is rendered as on/off
		// text instead (see misc.dataRange.binary/percent), where a unit
		// suffix wouldn't make sense.
		setpointUnitSuffix() {
			const node = this.node
			if (!node || !node.rcv_unit) return ''
			if (typeof node.setpoint !== 'number') return ''
			return ' ' + node.rcv_unit.trim()
		}
	},
}
//Vue.component('ControllerNode', ControllerNode)  //??


const MinimumCtrl = {
	extends: ControllerNode,
	computed: {
		descript() {
			return this.$t('dashboard.widget.setpoint.minimum') + this.node.setpoint.toString() + this.setpointUnitSuffix
		},
	},
}
registerGlobalComponent('MinimumCtrl', MinimumCtrl)


const MaximumCtrl = {
	extends: ControllerNode,
	computed: {
		descript() {
			return this.$t('dashboard.widget.setpoint.maximum') + this.node.setpoint.toString() + this.setpointUnitSuffix
		},
	},
}
registerGlobalComponent('MaximumCtrl', MaximumCtrl)


const PidCtrl = {
	extends: ControllerNode,
	computed: {
		descript() {
			return this.$t('dashboard.widget.setpoint.equals') + this.node.setpoint.toString() + this.setpointUnitSuffix
		},
	},
}
registerGlobalComponent('PidCtrl', PidCtrl)


const SunCtrl = {
	extends: ControllerNode,
	computed: {
		descript() {
			const cloudiness = Math.max(0, Math.min(7, this.node.cloudiness || 0))
			return this.$t('pages.settings.fields.ascendDescend') + ': '
				+ this.humanPeriod(this.node.xscend * 60 * 60 * 1000)
				+ ', ' + this.$t('dashboard.widget.sunCtrl.cloudiness.c' + cloudiness)
		},
		value() {
			let node = this.node
			switch (node.data) {
			case 100:
				return this.$t('misc.dataRange.' + node.data_range.toLowerCase() + '.value.on')
			case 0:
				return this.$t('misc.dataRange.' + node.data_range.toLowerCase() + '.value.off')
			default:
				return node.data.toFixed(2).toString() + (node.unit ? ' ' + node.unit : '')
			}
		}
	}
}
registerGlobalComponent('SunCtrl', SunCtrl);


const FadeCtrl = {
	extends: ControllerNode,
	computed: {
		descript() {
			return this.$t('pages.settings.fields.fadeIn') + ': ' + this.humanPeriod(this.node.fade_time)
				+ ', ' + this.$t('pages.settings.fields.fadeOut') + ': ' + this.humanPeriod(this.node.fade_out)
		},
		value() {
			let node = this.node
			switch (node.data) {
			case 100:
				return this.$t('misc.dataRange.' + node.data_range.toLowerCase() + '.value.on')
			case 0:
				return this.$t('misc.dataRange.' + node.data_range.toLowerCase() + '.value.off')
			default:
				return node.data.toFixed(2).toString() + (node.unit ? ' ' + node.unit : '')
			}
		}
	}
}
registerGlobalComponent('FadeCtrl', FadeCtrl)


const SwitchInput = {
	extends: BusNode,
}
registerGlobalComponent('SwitchInput', SwitchInput)

const AnalogInput = {
	extends: BusNode,
}
registerGlobalComponent('AnalogInput', AnalogInput)

const TextInput = {
	extends: BusNode,
}
registerGlobalComponent('TextInput', TextInput)


const UiSwitchInput = {
	extends: AnyNode,
	template: `
		<div>
			<v-card-title v-if="addNodeTitle">{{ node.name }}</v-card-title>
			<v-card-text class="text--secondary">
				<setting-switch :item="settingItem" @update="onUpdate"></setting-switch>
			</v-card-text>
		</div>
	`,
	computed: {
		settingsStore() {
			return useSettingsStore()
		},
		settingItem() {
			return {value: this.node.data, label: this.node.name}
		},
	},
	methods: {
		onUpdate(val) {
			this.settingsStore.updateNodeSetting({nodeId: this.node.id, key: 'value', value: val})
		},
	},
}
registerGlobalComponent('UiSwitchInput', UiSwitchInput)

const UiAnalogInput = {
	extends: AnyNode,
	template: `
		<div>
			<v-card-title v-if="addNodeTitle">{{ node.name }}</v-card-title>
			<v-card-text class="text--secondary">
				<setting-slider :item="settingItem" @update="onUpdate"></setting-slider>
			</v-card-text>
		</div>
	`,
	computed: {
		settingsStore() {
			return useSettingsStore()
		},
		settingItem() {
			return {
				value: this.node.data,
				label: this.node.name,
				attrs: {min: this.node.min, max: this.node.max, step: this.node.step},
			}
		},
	},
	methods: {
		onUpdate(val) {
			this.settingsStore.updateNodeSetting({nodeId: this.node.id, key: 'value', value: val})
		},
	},
}
registerGlobalComponent('UiAnalogInput', UiAnalogInput)


const ScheduleInput = {
	extends: BusNode,
	computed: {
		descript() {
			const node = this.node
			const weekdays = node.weekdays

			let prefix = ''
			if (weekdays && weekdays.length && weekdays.length < 7) {
				prefix = this.weekdayList(weekdays) + ' '
			}

			if (node.duration >= node.frequency) {
				return prefix + this.$t('dashboard.widget.schedule.always')
			}
			if (node.frequency === 86400) {
				return prefix + this.$t('dashboard.widget.schedule.daily', {
					start: node.anchor,
					end: this.addSeconds(node.anchor, node.duration),
				})
			}
			return prefix + this.$t('dashboard.widget.schedule.repeat', {
				freq: formatDuration(node.frequency, this.$t),
				dur: formatDuration(node.duration, this.$t),
				anchor: node.anchor,
			})
		},
	},
	methods: {
		weekdayList(weekdays) {
			return weekdays.slice().sort((a, b) => a - b)
				.map(d => this.$t('misc.weekday.' + d)).join(', ')
		},
		// anchor + a duration in seconds, wrapped to a 24h clock face -
		// only meaningful for the frequency=1-day "daily window" phrase,
		// where the window is always fully contained within one day
		addSeconds(anchor, seconds) {
			const [h, m] = anchor.split(':').map(Number)
			const total = ((h * 60 + m) * 60 + seconds) % 86400
			const endH = Math.floor(total / 3600)
			const endM = Math.floor((total / 60) % 60)
			return String(endH).padStart(2, '0') + ':' + String(endM).padStart(2, '0')
		},
	},
}
registerGlobalComponent('ScheduleInput', ScheduleInput)


const SwitchDevice = {
	extends: BusNode,
}
registerGlobalComponent('SwitchDevice', SwitchDevice)

const AnalogDevice = {
	extends: BusNode,
}
registerGlobalComponent('AnalogDevice', AnalogDevice)
registerGlobalComponent('SlowPwmDevice', AnalogDevice)

const AuxNode = {
	extends: BusNode,
	computed: {
		label() {
			return this.$t('misc.dataRange.aux.label')
		},
	},
}

const AvgAux = {
	extends: AuxNode,
	computed: {
		// unfair_avg has three distinct behaviors (aux_nodes.py) - 0 is the
		// default equal-weight average across all senders and needs no
		// subtitle; 1 is effectively no averaging at all (instant passthrough
		// of the latest value); >1 is a real moving average over that many
		// samples.
		descript() {
			const n = this.node.unfair_avg
			if (!n) {
				return ''
			}
			if (n === 1) {
				return this.$t('dashboard.widget.avgAux.unweighted')
			}
			return this.$t('dashboard.widget.avgAux.movingAvg', {n: n})
		},
	},
}
registerGlobalComponent('AvgAux', AvgAux);

const MinAux = {
	extends: AuxNode,
}
registerGlobalComponent('MinAux', MinAux)

const MaxAux = {
	extends: AuxNode,
}
registerGlobalComponent('MaxAux', MaxAux)

// no aggregation/math - just a flat, read-only name/value row per
// received node (not each source's own full widget, which would
// nest recursively for anything with receives of its own, and would
// duplicate live *interactive* controls inside what's meant to be a
// passive display)
const UiDisplay = {
	extends: AuxNode,
	template: `
		<div>
			<v-card-title v-if="addNodeTitle">{{ node.name }}</v-card-title>
			<v-card-text v-if="receivesNodes.length" class="text--secondary">
				<v-row
					v-for="item in receivesNodes"
					:key="item.identifier"
					no-gutters
					class="py-1"
				>
					<v-col cols="6" class="text-truncate">{{ item.name }}</v-col>
					<v-col cols="6">{{ formatValue(item) }}</v-col>
				</v-row>
			</v-card-text>
		</div>
	`,
	methods: {
		formatValue(item) {
			// prefer what this node itself actually received (node.values,
			// keyed by sender id) over the source's own re-fetched state -
			// a sender's .data doesn't necessarily reflect every message it
			// posts (e.g. SlowPwmDevice._pulse() posts transient on/off
			// states without updating its own .data), so falling back to
			// item.data would silently miss those. Only truly falls back
			// to item.data before any message has arrived from that sender.
			const values = this.node.values || {}
			const val = (item.id in values) ? values[item.id] : item.data

			switch (item.data_range) {
				case 'ANALOG':
				case 'PERCENT':
					return val.toFixed(2).toString() + (item.unit ? ' ' + item.unit : '')
				case 'BINARY':
					return (val > 0
						? this.$t('misc.dataRange.' + item.data_range.toLowerCase() + '.value.on')
						: this.$t('misc.dataRange.' + item.data_range.toLowerCase() + '.value.off')
					)
				default:
					return val
			}
		},
	},
}

registerGlobalComponent('UiDisplay', UiDisplay)

const ScaleAux = {
	extends: AuxNode,
	computed: {
		descript() {
			const node = this.node
			let text = this.$t('dashboard.widget.scaleAux.formula', {
				factor: node.factor.toFixed(2),
				offset: node.offset.toFixed(2),
			})
			const limit = node.limit
			// (0, 100) is ScaleAux's constructor default - only call it out
			// when the node actually narrows/shifts that range
			if (limit && (limit[0] !== 0.0 || limit[1] !== 100.0)) {
				text += ' [' + limit[0] + '-' + limit[1] + ']'
			}
			return text
		},
	},
}
registerGlobalComponent('ScaleAux', ScaleAux)


const History = {
	extends: AnyNode,

	template: `
		<div>
			<aquapi-node-description
				:item="node"
			>
			</aquapi-node-description>

			<history-chart
				:id="id"
				:node="node"
				:level="level"
				:renderType="'widget'"
			></history-chart>
			
			<v-dialog
				:model-value="uiStore.isActiveDialog(modalDialogName)"
				@update:model-value="(val) => { if (!val) closeModal() }"
				persistent
				width="80vw"
			>
				<v-card>
					<v-card-title class="text-h6 d-flex align-center justify-space-between">
						<span>{{ node.name }}</span>
						<v-btn
							icon
							variant="text"
							color="grey-darken-1"
							@click="closeModal"
						>
							<v-icon>mdi-close</v-icon>
						</v-btn>
					</v-card-title>
					<v-divider></v-divider>

					<v-card-text>
						<history-chart
							:id="id"
							:node="node"
							:level="level"
							:renderType="'modal'"
						></history-chart>
					</v-card-text>
				</v-card>
			</v-dialog>
			
		</div>
	`,

	data() {
		return {
			chart: null,
			chartContainerWidth: null,
		}
	},

	computed: {
		uiStore() {
			return useUiStore()
		},
		modalDialogName() {
			return `chart_modal_${this.id}`
		}
	},
	methods: {
		closeModal() {
			this.uiStore.hideDialog(this.modalDialogName)
		}
	}
}
registerGlobalComponent('History', History)


const HistoryChart = {
	extends: AnyNode,

	props: {
		renderType: {
			type: String,
			default: 'widget',
			required: false
		}
	},

	template: `
		<div>
			<div
				class="v-card__text"
			>
				<div :id="wrapperId">
				</div>

				<div
					 v-if="dataPrepared == false"
					 class="pa-10 text-center"
				 >
					<aquapi-loading-indicator></aquapi-loading-indicator>
				</div>

				<div 
					v-else

				>
					<teleport :to="'#widget-title-actions-' + node.id" :disabled="renderType === 'modal'">
						<div class="d-flex justify-end align-center px-0 py-2">
							<v-menu
								offset-y
								open-on-hover
							>
								<template v-slot:activator="{ props }">
									<v-btn
										v-bind="props"
										variant="tonal"
										color="grey-darken-1"
										size="small"
										class="text-none"
										append-icon="mdi-menu-down"
										:loading="isLoading"
									>
										{{ $t('dashboard.widget.history.period.label').replace('%s', humanPeriod(period)) }}
									</v-btn>
								</template>
								<v-list
									dense
									density="compact"
									class="py-0"
								>
									<v-list-item
										v-for="(item, index) in periods"
										:key="index"
										density="compact"
										min-height="28"
										:disabled="node.memory_only && item.value > node.capacity * 60 * 60 * 1000"
										@click="setPeriod(item.value, chart)"
									>
										<v-list-item-title class="text-caption">
											{{ item.label }}
										</v-list-item-title>
									</v-list-item>

									<v-divider></v-divider>

									<v-list-item
										density="compact"
										min-height="28"
										@click.stop
									>
										<v-checkbox
											v-model="forceDailySampling"
											:disabled="forceDailySamplingDisabled"
											density="compact"
											hide-details
											class="ma-0"
											:label="$t('dashboard.widget.history.forceDailySampling.label')"
											@click.stop
											@update:modelValue="onForceDailySamplingChange(chart)"
										></v-checkbox>
									</v-list-item>
								</v-list>
							</v-menu>

							<v-btn
								v-if="renderType != 'modal'"
								variant="tonal"
								color="grey-darken-1"
								size="small"
								class="ms-2 px-2"
								min-width="0"
								@click="openModal"
							>
								<v-icon>mdi-arrow-expand-all</v-icon>
							</v-btn>
						</div>
					</teleport>

					<div class="chart-container" style="position: relative; width:100%;">
						<canvas :id="canvasId"></canvas>
					</div>
				</div>
			</div>
		</div>
	`,

	data() {
		return {
			numDataItems : 0,
			chart: null,
			chartContainerWidth: null,

			dataPrepared: false,
			isLoading: false,
			currentPeriod: (60 * 60 * 1000),
			currentForceDailySampling: false,
			// NOTE: markRaw() prevents Vue from wrapping this in a reactive Proxy - Chart.js
			// performs its own internal option resolution (also Proxy-based) on this object,
			// and nesting it inside a Vue reactive Proxy causes infinite recursion on update().
			cd: window.Vue.markRaw({
				type: "scatter",
				data: {
					// labels: [],
					datasets: [],
				},
				options: {
					spanGaps: true,
					//locale: "de-DE",
					responsive: true,
					//aspectRatio: 1,
					maintainAspectRatio: true,
					showLine: true,
					borderWidth: 1,
					lineTension: 0,
					stepped: false,
					pointRadius: 0,
					plugins: {
						legend: {display: true, labels: {boxWidth: 5}, position: "bottom"},
						tooltip: {position: 'nearest', xAlign: 'center', yAlign: 'bottom', caretPadding: 24},
					},	//top"},
					animation: {duration: 1500, easing: "easeInOutBack"},
					interaction: {mode: "x", axis: "x", intersect: false},
					scales: {
						x: {
							type: "time",
							min: Date.now() - this.currentPeriod,
							max: Date.now(),
							time: {
								//unit: "hour",
								// from https://github.com/moment/luxon/blob/master/docs/formatting.md 
								displayFormats: {second: "mm:ss", minute: "t", hour: "t", day: "D"},
								tooltipFormat: "tt",
							},
							grid: {
								color: useUiStore().darkMode ? 'rgba(220, 220, 220, 0.08)' : 'rgba(0, 0, 0, 0.05)'
							}
						},
						y: {
							display: 'auto',
							axis: 'y',
							position: 'left',
							min: 0,
							max: 100,
							ticks: {
								beginAtZero: true
							},
							grid: {
								color: useUiStore().darkMode ? 'rgba(220, 220, 220, 0.12)' : 'rgba(0, 0, 0, 0.12)'
							}
						},
						yAnalog: {
							display: 'auto',
							axis: 'y',
							position: 'right',
 						grid: {
								color: useUiStore().darkMode ? 'rgba(220, 220, 220, 0.08)' : 'rgba(0, 0, 0, 0.05)'
							}
						},
					}
				}
			}),
		}
	},

	computed: {
		dashboardStore() {
			return useDashboardStore()
		},
		uiStore() {
			return useUiStore()
		},
		wrapperId() {
			return `chart_wrapper_${this.id}_${this.renderType}`
		},
		canvasId() {
			return `chart_canvas_${this.id}_${this.renderType}`
		},
		modalId() {
			return `chart_modal_${this.id}_${this.renderType}`
		},
		modalDialogName() {
			return `chart_modal_${this.id}`
		},
		storageId() {
			return `${this.id}_${this.renderType}`
		},
		chartWidth: {
			set(val) {
				this.chartContainerWidth = val
			},
			get() {
				return this.chartContainerWidth
			}
		},
		periods() {
			const vm = this
			return [0.25, 1, 4, 8, 12, 24, 48, 168, 720, 4380, 8760].map((h) => {
				const value = (h * 60 * 60 * 1000)
				return { value: value, label: vm.humanPeriod(value) }
			})
		},

		period: {
			set(val) {
				try {
					const storage = window.localStorage
					let config = storage.getItem('aquapi.history');
					if (config) {
						config = JSON.parse(config)
					} else {
						config = {}
					}
					config[this.storageId] = {...config[this.storageId], period: val}
					storage.setItem('aquapi.history', JSON.stringify(config))
				} catch(e) {}

				this.currentPeriod = val
			},
			get() {
				try {
					const storage = window.localStorage
					let config = storage.getItem('aquapi.history')
					if (config) {
						config = JSON.parse(config)
						if (config[this.storageId]?.period) {
							this.currentPeriod = config[this.storageId].period
						}
					}
				} catch(e) {}

				return this.currentPeriod
			}
		},
		forceDailySampling: {
			set(val) {
				try {
					const storage = window.localStorage
					let config = storage.getItem('aquapi.history');
					if (config) {
						config = JSON.parse(config)
					} else {
						config = {}
					}
					config[this.storageId] = {...config[this.storageId], forceDailySampling: val}
					storage.setItem('aquapi.history', JSON.stringify(config))
				} catch(e) {}

				this.currentForceDailySampling = val
			},
			get() {
				try {
					const storage = window.localStorage
					let config = storage.getItem('aquapi.history')
					if (config) {
						config = JSON.parse(config)
						if (config[this.storageId]?.forceDailySampling !== undefined) {
							this.currentForceDailySampling = config[this.storageId].forceDailySampling
						}
					}
				} catch(e) {}

				return this.currentForceDailySampling
			}
		},
		forceDailySamplingDisabled() {
			return this.period < 24 * 60 * 60 * 1000
		},
		chartStep() {
			// NOTE: period is millisecs, result must be secs
			let periodSec = this.period / 1000

			if (this.forceDailySampling && periodSec >= 24 * 60 * 60) {
				return 24 * 60 * 60
			}

			if (!this.chartWidth) {
				return (periodSec <= 3600) ? 1 : 60
			}

			// target ~1 sample per available chart pixel
			let rawStep = periodSec / this.chartWidth
			if (rawStep <= 1) {
				// DB's native resolution; also smooths rare faster-than-1s bursts
				return 1
			}

			// round up to the next "nice" bucket so QuestDB's ALIGN TO
			// CALENDAR grid produces stable, calendar-aligned boundaries
			let niceSteps = [1, 5, 10, 15, 30, 60, 300, 900, 1800, 3600, 7200, 21600, 43200, 86400]
			let nice = niceSteps.find((s) => s >= rawStep)
			return nice ?? Math.ceil(rawStep / 86400) * 86400
		}
	},
	methods: {
		prepareChartData(payload) {
			const now = Date.now();
			const data = payload

			if (data) {
				const historySeries = data[0]
				delete(data[0])

				let values = {}

				for (let dsIdx in historySeries) {
					values[dsIdx] = {}

					const node = this.dashboardStore.node(historySeries[dsIdx])

					if (this.cd.data.datasets[dsIdx] === undefined) {
						this.cd.data.datasets[dsIdx] = {
							label: node.name + ' [' + node.unit + ']', // ' %',
							data: [],
						}

						if (node.data_range === 'ANALOG' && node.unit != '%') {
							this.cd.data.datasets[dsIdx].stepped = false
							this.cd.data.datasets[dsIdx].yAxisID = 'yAnalog'
						}
						if (node.data_range === 'BINARY') {
							this.cd.data.datasets[dsIdx].stepped = true
							this.cd.data.datasets[dsIdx].label = '⏻ ' + node.name
						}
					}
					dsIdx++;
				}

				for (let dsIdx in historySeries) {
					let val = null
					for (const ts in data) {
						if (data[ts][dsIdx] !== null) {
							val = data[ts][dsIdx]
							values[dsIdx][ts] = {x: ts * 1000, y: val}
//							console.log('  data ' + dsIdx + ': ' + ts + '/' + val)
						}
					}
					if (val !== null) {
						values[dsIdx][now] = {x: now, y: val}
//						console.log('  append ' + dsIdx + ': ' + now + '/' + val +  ' ? ' + this.$store.getters['dashboard/node'](node.id).data)
					}

					this.cd.data.datasets[dsIdx].data = Object.values(values[dsIdx])
				}

				this.cd.options.scales.x.min = now - this.currentPeriod
				this.cd.options.scales.x.max = now
			}

			this.numDataItems = this.cd?.data?.datasets[0]?.data?.length || 0
			this.dataPrepared = true
		},

		async loadHistory() {
			if (this.renderType === 'modal' && !this.uiStore.isActiveDialog(this.modalDialogName)) {
				return
			}

			this.isLoading = true

			let tsNow = Math.floor(Date.now() / 1000)
			let start = tsNow - this.currentPeriod / 1000

			const result = await this.dashboardStore.fetchNodeHistory({
				nodeId: this.node.id,
				start: start,
				step: this.chartStep
			})

			if (result) {
				this.prepareChartData(result)
			}
			this.isLoading = false
		},
		async setPeriod(val, chart) {
			if (val !== this.currentPeriod) {
				this.period = val
				if (chart) {
					await this.loadHistory()
					chart.update()
				}
			}
		},
		async onForceDailySamplingChange(chart) {
			// v-model already persisted the new value via the
			// forceDailySampling computed setter - just reload at the
			// new step
			if (chart) {
				await this.loadHistory()
				chart.update()
			}
		},
		async openModal() {
			// NOTE: the 2nd ("hideOthers") arg is intentionally dropped here -
			// Vuex's dispatch(type, payload, options) never forwarded a 3rd
			// positional argument to the action anyway, so `true` was always
			// silently ignored and showDialog() always used its hideOthers=true
			// default; this preserves that exact prior behavior.
			await this.uiStore.showDialog(this.modalDialogName)
			await this.loadHistory()
		},
		closeModal() {
			this.uiStore.hideDialog(this.modalDialogName)
			if (this.chart != null) {
				this.chart.destroy()
				this.chart = null
			}
		}
	},
	async created() {
		this._sseHandler = async (payload) => {
			if (payload.id === this.node.id) {
				await this.loadHistory()
				if (this.chart !== null) {
					this.chart.update()
				}
			}
		}
		EventBus.$on(AQUAPI_EVENTS.SSE_NODE_UPDATE, this._sseHandler)
	},

	async mounted() {
		this.chart = null
		this.currentPeriod = this.period

		let elContainer = document.getElementById(this.wrapperId)
		if (elContainer) {
			this.chartContainerWidth = elContainer.offsetWidth

			// re-fetch at the new pixel-driven step (see chartStep) once
			// resizing settles, so an already-loaded chart's resolution
			// adapts instead of staying pinned to its width at mount time
			this._resizeObserver = new ResizeObserver((entries) => {
				const width = Math.round(entries[0].contentRect.width)
				if (width && width !== this.chartContainerWidth) {
					this.chartContainerWidth = width

					// Chart.js doesn't always pick up its container growing
					// on its own here (canvas stays at its old size) -
					// resize() forces it to re-measure and redraw immediately
					if (this.chart != null) {
						this.chart.resize()
					}

					clearTimeout(this._resizeDebounce)
					this._resizeDebounce = setTimeout(async () => {
						await this.loadHistory()
						if (this.chart != null) {
							this.chart.update()
						}
					}, 300)
				}
			})
			this._resizeObserver.observe(elContainer)
		}

		await this.loadHistory()

		if (this.chart == null) {
			let el = document.getElementById(this.canvasId)
			if (el != null) {
				// NOTE: markRaw() - see the comment on `cd` in data() above.
				this.chart = window.Vue.markRaw(new Chart(el, this.cd))
			}
		}
	},

	unmounted() {
		EventBus.$off(AQUAPI_EVENTS.SSE_NODE_UPDATE, this._sseHandler)

		if (this._resizeObserver) {
			this._resizeObserver.disconnect()
			this._resizeObserver = null
		}
		clearTimeout(this._resizeDebounce)

		if (this.chart != null) {
			this.chart.destroy()
		}
		this.chart = null
		this.chartContainerWidth = null
	}
}
registerGlobalComponent('HistoryChart', HistoryChart)


const AlertNode = {
	extends: AnyNode,
	template: `
		<div>
			<v-card-title
				v-if="addNodeTitle"
			>
				{{ node.name }}
			</v-card-title>
			<aquapi-node-description
				:item="node"
			>
			</aquapi-node-description>
			<v-card-text
				class="text--secondary"
			>
				<div
					v-for="(entry, index) in node.data"
					:key="index"
					style="white-space: pre-line"
					class="mb-1"
				>
					{{ entryBody(entry) }}
				</div>
				<div v-if="!node.data || !node.data.length">
					{{ $t('misc.noActiveAlerts') }}
				</div>
			</v-card-text>
		</div>
	`,

	computed: {
		descript() {
			return (this.node.conditions || []).map((cond) => this.conditionText(cond)).join(', ')
		}
	},

	methods: {
		// each entry's 1st line is only meant as an email subject
		// (see Alert.listen() in alert_nodes.py) - not shown here
		entryBody(entry) {
			return entry.split('\n').slice(1).join('\n')
		},
		conditionText(cond) {
			const watched = this.dashboardStore.node(cond.node_id)
			const name = watched ? watched.name : cond.node_id
			const unit = (watched && watched.unit) ? ' ' + watched.unit.trim() : ''
			let text = `${name} ${this.$t('misc.alertConds.' + cond.class)} ${cond.limit}${unit}`
			// duration is in minutes (see AlertCond in alert_nodes.py), humanPeriod wants ms
			if (cond.duration) {
				text += ' (' + this.humanPeriod(cond.duration * 60 * 1000) + ')'
			}
			return text
		}
	}
}
registerGlobalComponent('Alert', AlertNode)


const AquapiNodeDescription = {
	props: {
		item: {
			type: Object,
			required: true
		},
	},
	template: `
		<v-card-subtitle
			v-if="descript"
			class="pt-0"
		>
			{{ descript }}
		</v-card-subtitle>
	`,

	computed: {
		descript() {
			return this.$parent?.descript ?? ''
		}
	}
}
registerGlobalComponent('AquapiNodeDescription', AquapiNodeDescription)


const AquapiNodeData = {
	props: {
		item: {
			type: Object,
			required: true
		},
	},
	template: `
		<v-row no-gutters>
			<v-col cols="6">
				<slot name="label">
					{{ $t('misc.genericLabel') }}
				</slot>
			</v-col>
			<v-col cols="6">
				<slot name="value">
					{{ $t('misc.genericValue') }}
				</slot>
			</v-col>
		</v-row>
	`,

	computed: {}
}
registerGlobalComponent('AquapiNodeData', AquapiNodeData)

// vim: set noet sts ts=4 sw=4:
