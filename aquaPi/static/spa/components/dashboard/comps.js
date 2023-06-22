// TODO: more details on dashboard widget? Design/Layout? Colors? Icons? Edit settings?
// TODO: adapt charts to new history API, when implemented
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

const LightCtrl = {
	extends: ControllerNode,
}
Vue.component('LightCtrl', LightCtrl)


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
			<v-card-title
				v-if="addNodeTitle"
			>
				{{ node.name }}
			</v-card-title>
			<aquapi-node-description
				:item="node"
			>
			</aquapi-node-description>
			
			<div
				v-if="this.dataPrepared == false"
				class="pa-10 text-center"
			>
				<aquapi-loading-indicator></aquapi-loading-indicator>
			</div>
			
			<div 
				v-else
				class="pa-2"
			>
				<div 
					class="d-flex justify-end px-0 py-2"
				>
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
								@click="setPeriod(item.value)"
							>
								<v-list-item-title>
									{{ item.label }}
								</v-list-item-title>
							</v-list-item>
						</v-list>
					</v-menu>
				</div>
				<div>
					<canvas :id="'chart_' + id"></canvas>
				</div>
			</div>
		</div>
	`,

	data() {
		return {
			chart: null,
			dataPrepared: false,
			isLoading: false,
			currentPeriod: (60 * 60 * 1000),
			cd: {
				type: "scatter",
				data: {
					labels: [],
					datasets: [],
				},
				options: {
					//locale: "de-DE",
					responsive: true,
					//aspectRatio: 1,
					maintainAspectRatio: true,
					showLine: true,
					borderWidth: 1,
					lineTension: 0,
					stepped: true, //false,
					pointRadius: 0,
					plugins: {
						legend: {display: true, labels: {boxWidth: 3}, position: "top"},
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
								//unit: "minutes"
								// unit: "hours",
								displayFormats: {seconds: "H:mm:ss", minutes: "H:mm", hours: "H:mm"},
								tooltipFormat: "TT"
							},
						},
						y: {display: 'auto', axis: 'y', ticks: {beginAtZero: true}},
						yAnalog: {display: 'auto', axis: 'y', position: 'right'},
					}
				}
			},
		}
	},

	computed: {
		periods() {
			const vm = this
			return [0.25, 1, 4, 8, 24].map((h) => {
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
					config[this.node.id] = {period: val}
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
						if (config[this.node.id]?.period) {
							this.currentPeriod = config[this.node.id].period
						}
					}
				} catch(e) {}

				return this.currentPeriod
			}
		}
	},
	methods: {
		prepareChartData() {
			const store = this.$store.getters['dashboard/history'](this.node.id)

			if (store != null) {
				const now = Date.now();
				let dsIdx = 0;
				for (let series in store) {
					if (dsIdx >= this.cd.data.datasets.length) {
						const node = this.$store.getters['dashboard/node'](series)
						this.cd.data.datasets.push({
							label: node.name,
							data: [],
						});

						if (node.data_range === 'ANALOG' && node.unit != '%') {
							this.cd.data.datasets[dsIdx].stepped = false
							this.cd.data.datasets[dsIdx].yAxisID = 'yAnalog'
						}
					}

					this.cd.data.datasets[dsIdx].data = []
					for (let val of store[series]) {
						this.cd.data.datasets[dsIdx].data.push({x: val[0] * 1000, y: val[1]})
					}
					// append current value
					this.cd.data.datasets[dsIdx].data.push({x: now, y: this.$store.getters['dashboard/node'](series).data});
					dsIdx++;
				}
				this.cd.options.scales.x.min = now - this.currentPeriod
				this.cd.options.scales.x.max = now
			}

			this.dataPrepared = true
		},

		async loadHistory() {
			this.isLoading = true
			const result = await this.$store.dispatch('dashboard/loadNodeHistory', this.node)
			if (result) {
				this.prepareChartData()
			}
			this.isLoading = false
		},
		async setPeriod(val) {
			if (val !== this.currentPeriod) {
				this.period = val
				if (this.chart) {
					await this.loadHistory()
					this.chart.update()
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
		}
	},
	async created() {
		this.chart = null
		this.currentPeriod = this.period
		await this.loadHistory()

		if (this.chart == null) {
			const el = document.getElementById('chart_' + this.id)
			if (el != null) {
				this.chart = new Chart(el, this.cd)
			}
		}

		// TODO: maybe listen to SSE_NODE_UPDATE for this node.inputs, not only for this node ?
		EventBus.$on(AQUAPI_EVENTS.SSE_NODE_UPDATE, async (payload) => {
			if (payload.id === this.node.id) {
				await this.loadHistory()
				if (this.chart !== null) {
					this.chart.update()
				}
			}
		})
	},
	destroyed() {
		EventBus.$off(AQUAPI_EVENTS.SSE_NODE_UPDATE)

		if (this.chart != null) {
			this.chart.destroy()
		}
		this.chart = null
	},
}
Vue.component('History', History)


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
