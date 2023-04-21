// TODO: complete labels for different node types / data_range
// TODO: complete values for different node types / data_range
// TODO: implement charts from uikit instance
// TODO: 'alert' badges?
// TODO: ... more details on dashboard widget? Design/Layout? Colors? Icons? Edit settings?

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

const CalibrationAux = {
	extends: AuxNode,
}
Vue.component('CalibrationAux', CalibrationAux)


const History = {
	extends: AnyNode,
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
