// TODO: more details on dashboard widget? Design/Layout? Colors? Icons? Edit settings?
// TODO: add 'zoom' / modal mode for charts
// TODO: change masonry direction, if possible; maybe use other masonry plugin

import {AQUAPI_EVENTS, EventBus} from '../app/EventBus.js';

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
		descript() {
			return ''  // just a sample
		},
		label() {
			let node = this.node
			switch (node.data_range) {
				case 'ANALOG':
				case 'BINARY':
				case 'PERCENT':
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
					return node.data.toFixed(2).toString() + (node.unit ? ' ' + node.unit : '')
				case 'BINARY':
					// return '<i aria-hidden="true" class="v-icon notranslate v-icon--left mdi mdi-chart-line theme--light blue-grey--text text--lighten-4"></i>'
					return (node.data > 0
							? this.$t('misc.dataRange.' + node.data_range.toLowerCase() + '.value.on')
							: this.$t('misc.dataRange.' + node.data_range.toLowerCase() + '.value.off')
					)
				case 'PERCENT':
					return node.data.toFixed(2).toString() + (node.unit ? ' ' + node.unit : '')
				default:
					return node.data
			}

			return node.data
		},
		inputNodes() {
			const node = this.node
			let nodes = []

			if (node.inputs?.sender) {
				node.inputs.sender.forEach(id => {
					nodes.push(this.$store.getters['dashboard/node'](id))
				})
			}

			return nodes
		},
	},
}
Vue.component('AnyNode', AnyNode)

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
Vue.component('DebugNode', DebugNode)


const BusNode = {
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
			
			<template
				v-if="inputNodes.length > 0"
			>
				<template
					v-if="level == 1"
				>
					<v-expansion-panels
						tile
					>
						<v-expansion-panel>
							<v-expansion-panel-header
								class="py-0 px-4"
							>
								{{ $t('dashboard.widget.inputs.label') }}
							</v-expansion-panel-header>
							<v-expansion-panel-content>
								<v-card
									v-for="(item, index) in inputNodes"
									:key="item.identifier"
									outlined
									tile
									class="ma-3 mt-0"
								>
									<component
										:is="item.type"
										:id="item.identifier"
										:node="item"
										:level="(level + 1)"
									></component>
								</v-card>
							</v-expansion-panel-content>
						</v-expansion-panel>
					</v-expansion-panels>
				</template>
				<template
					v-else
				>
					<v-card
						v-for="(item, index) in inputNodes"
						:key="item.identifier"
						outlined
						tile
						class="ma-3 mt-0"
					>
						<component
							:is="item.type"
							:id="item.identifier"
							:node="item"
							:level="(level + 1)"
						></component>
					</v-card>
				</template>
			</template>
		</div>
	`,

	computed: {},
}
Vue.component('BusNode', BusNode)


const ControllerNode = {
	extends: BusNode,
}
Vue.component('ControllerNode', ControllerNode)


const MinimumCtrl = {
	extends: ControllerNode,
	computed: {
		descript() {
			return 'Sollwert: >= ' + this.node.threshold.toString() // just a sample
		},
	},
}
Vue.component('MinimumCtrl', MinimumCtrl)


const MaximumCtrl = {
	extends: ControllerNode,
	computed: {
		descript() {
			return 'Sollwert: <= ' + this.node.threshold.toString() // just a sample
		},
	},
}
Vue.component('MaximumCtrl', MaximumCtrl)


const SunCtrl = {
	extends: ControllerNode,
	computed: {
		descript() {
			return this.node.xscend.toString() + ' h_/ '
				 + this.node.highnoon.toString() + ' h \\_'
				 + this.node.xscend.toString() + ' h'
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
Vue.component('SunCtrl', SunCtrl);
Vue.component('FadeCtrl', SunCtrl) // temporary alias


const SwitchInput = {
	extends: BusNode,
}
Vue.component('SwitchInput', SwitchInput)

const AnalogInput = {
	extends: BusNode,
}
Vue.component('AnalogInput', AnalogInput)

const ScheduleInput = {
	extends: BusNode,
	computed: {
		label() {
			let node = this.node
			return this.$t('misc.dataRange.cronspec.label')
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
Vue.component('ScheduleInput', ScheduleInput)


const SwitchDevice = {
	extends: BusNode,
}
Vue.component('SwitchDevice', SwitchDevice)

const AnalogDevice = {
	extends: BusNode,
}
Vue.component('AnalogDevice', AnalogDevice)

const AuxNode = {
	extends: BusNode,
}
Vue.component('AuxNode', AuxNode)

const AvgAux = {
	extends: AuxNode,
}
Vue.component('AvgAux', AvgAux);

const MinAux = {
	extends: AuxNode,
}
Vue.component('MinAux', MinAux)

const MaxAux = {
	extends: AuxNode,
}
Vue.component('MaxAux', MaxAux)

const ScaleAux = {
	extends: AuxNode,
}
Vue.component('ScaleAux', ScaleAux)


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
				v-model="$store.getters['ui/isActiveDialog'](modalDialogName)"
				persistent
				width="80vw"
			>
				<v-card>
					<v-card-title class="text-h6">
						{{ node.name }}
						<v-spacer></v-spacer>
						<v-btn
							icon
							@click="closeModal"
						>
							<v-icon color="grey">mdi-close</v-icon>
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
		modalDialogName() {
			return `chart_modal_${this.id}`
		}
	},
	methods: {
		closeModal() {
			this.$store.dispatch('ui/hideDialog', this.modalDialogName)
		}
	}
}
Vue.component('History', History)


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
					<div class="d-flex justify-end px-0 py-2">
						<v-menu
							offset-y
							open-on-hover
						>
							<template v-slot:activator="{ on, attrs }">
								<v-btn
									v-bind="attrs"
									v-on="on"
									depressed
									small
									class="text-none"
									:loading="isLoading"
								>
									{{ humanPeriod() }}
								</v-btn>
							</template>
							<v-list
								dense
								class="py-0"
							>
								<v-list-item
									v-for="(item, index) in periods"
									:key="index"
									@click="setPeriod(item.value, chart)"
								>
									<v-list-item-title>
										{{ item.label }}
									</v-list-item-title>
								</v-list-item>
							</v-list>
						</v-menu>

						<v-btn
							v-if="renderType != 'modal'"
							depressed
							small
							class="text-none ms-2 px-0 v-btn--icon"
							width="28"
							max-width="28"
							min-width="28"
							@click="openModal"
						>
							<v-icon class="text-button">mdi-arrow-expand-all</v-icon>
						</v-btn>
					</div>

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
			cd: {
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
								color: this.$store.state.ui.darkMode ? 'rgba(220, 220, 220, 0.08)' : 'rgba(0, 0, 0, 0.05)'
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
								color: this.$store.state.ui.darkMode ? 'rgba(220, 220, 220, 0.12)' : 'rgba(0, 0, 0, 0.12)'
							}
						},
						yAnalog: {
							display: 'auto',
							axis: 'y',
							position: 'right',
							grid: {
								color: this.$store.state.ui.darkMode ? 'rgba(220, 220, 220, 0.08)' : 'rgba(0, 0, 0, 0.05)'
							}
						},
					}
				}
			},
		}
	},

	computed: {
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
			return [0.25, 1, 4, 8, 12, 24].map((h) => {
				const value = (h * 60 * 60 * 1000)
				return { value: value, label: vm.humanPeriod(false, value) }
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
					config[this.storageId] = {period: val}
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
		chartStep() {
			if (!this.chartWidth) {
				return 5
			}

			// NOTE: period is millisecs, result must be secs
			// NOTE: for now, we round up to 15 seconds
			let minStep = 60  //?15
			// TODO: (?) calculate factor based on period, chartWidth, ...
			let factor = this.period / 1000 / 3600
			let val = this.period / 1000 / this.chartWidth * factor
			let rounded = Math.ceil(val / minStep) * minStep

			//return rounded
			return (factor <= 1) ? 1 : rounded
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

					const node = this.$store.getters['dashboard/node'](historySeries[dsIdx])

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
//	 						console.log('  data ' + dsIdx + ': ' + ts + '/' + val)
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
			if (this.renderType === 'modal' && !this.$store.getters['ui/isActiveDialog'](this.modalDialogName)) {
				return
			}

			this.isLoading = true

			let tsNow = Math.floor(Date.now() / 1000)
			let start = tsNow - this.currentPeriod / 1000

			const result = await this.$store.dispatch('dashboard/fetchNodeHistory', {
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
		humanPeriod(addLabel = true, val = null) {
			const label = this.$t('dashboard.widget.history.period.label')
			let value = (val !== null ? (val / 60 / 1000) : (this.period / 60 / 1000))
			let unit = 'h'
			if (value < 60) {
				unit = 'min'
				return (addLabel ? label.replace('%s', `${value} ${unit}`) : `${value} ${unit}`)
			}
			value /= 60
			return (addLabel ? label.replace('%s', `${value} ${unit}`) : `${value} ${unit}`)
		},
		async openModal() {
			await this.$store.dispatch('ui/showDialog', this.modalDialogName, true)
			await this.loadHistory()
		},
		closeModal() {
			this.$store.dispatch('ui/hideDialog', this.modalDialogName)
			if (this.chart != null) {
				this.chart.destroy()
				this.chart = null
			}
		}
	},
	async created() {
		EventBus.$on(AQUAPI_EVENTS.SSE_NODE_UPDATE, async (payload) => {
			if (payload.id === this.node.id) {
				await this.loadHistory()
				if (this.chart !== null) {
					this.chart.update()
				}
			}
		})
	},

	async mounted() {
		this.chart = null
		this.currentPeriod = this.period

		let elContainer = await document.getElementById(this.wrapperId)
		if (elContainer) {
			this.chartContainerWidth = elContainer.offsetWidth
		}

		await this.loadHistory()

		if (this.chart == null) {
			let el = document.getElementById(this.canvasId)
			if (el != null) {
				this.chart = new Chart(el, this.cd)
			}
		}
	},

	destroyed() {
		EventBus.$off(AQUAPI_EVENTS.SSE_NODE_UPDATE)

		if (this.chart != null) {
			this.chart.destroy()
		}
		this.chart = null
		this.chartContainerWidth = null
	}
}
Vue.component('HistoryChart', HistoryChart)

const AquapiNodeDescription = {
	props: {
		item: {
			type: Object,
			required: true
		}
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
Vue.component('AquapiNodeDescription', AquapiNodeDescription)


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
					Label
				</slot>
			</v-col>
			<v-col cols="6">
				<slot name="value">
					Value
				</slot>
			</v-col>
		</v-row>
	`,

	computed: {}
}
Vue.component('AquapiNodeData', AquapiNodeData)

// vim: set noet ts=4 sw=4:
