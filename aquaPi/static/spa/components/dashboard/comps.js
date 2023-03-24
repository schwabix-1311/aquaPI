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

	created: async function () {
		// this.in_ids = []
		//
		// console.log('[AnyNode] CREATED | this:', this)
		// // if (this.node.inputs?.sender != null) {
		// //     this.in_ids = this.node.inputs.sender
		// //     if (this.in_ids == '*')
		// //         this.in_ids = []
		// //     console.debug(`... INs of ${this.id}:  ${this.in_ids}`)
		// //     for (let in_id of this.in_ids)
		// //         await this.$root.updateNode(in_id, true)
		// // }
	},
	computed: {
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
		}
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
        <v-card-text>
            <div v-if="(999 == 111)">
                <strong>node:</strong> {{ node }}
            </div>

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

<!--      <div class="uk-card uk-card-small uk-card-default uk-card-body" style="border: 1px solid blue;">-->
<!--        <h2 class="uk-card-title uk-margin-remove-bottom">-->
<!--          <span v-if="node != undefined">-->
<!--            <span v-html="decoration"></span>{{ node.name }}-->
<!--          </span>-->
<!--          <span v-else>{{ id }} loading ...</span>-->
<!--        </h2>-->
<!--        <div v-html="getAlert" v-bind:class="getAlertClass" :hidden="!getAlert"></div>-->
<!--        <div v-if="node != undefined" class="uk-padding-remove">-->
<!--          <div class="uk-grid-collapse" uk-grid>-->
<!--            <div class="uk-width-2-3" v-html="label"></div>-->
<!--            <div class="uk-width-expand" v-html="value"></div>-->
<!--          </div>-->
<!--        </div>-->
<!--      </div>-->
    `,

	computed: {
		decoration() {
			return ''
		},
		getAlert() {
			if ((this.node == null) || !('alert' in this.node))
				return ''
			return this.node.alert[0]
		},
		getAlertClass() {
			if ((this.node == null) || !('alert' in this.node))
				return ''
			let ret = 'uk-card-badge uk-label '
			let severity = this.node.alert[1]
			if (severity in severity_map)
				ret += severity_map[severity]
			else
				console.warn('Unknown alert severity: "' + severity + '" used by ' + this.id)
			return ret
		},
	},
}
Vue.component('BusNode', BusNode)


const ControllerNode = {
	extends: BusNode,
}
Vue.component('ControllerNode', ControllerNode)


const MinimumCtrl = {
	extends: ControllerNode,
}
Vue.component('MinimumCtrl', MinimumCtrl)


const MaximumCtrl = {
	extends: ControllerNode,
}
Vue.component('MaximumCtrl', MaximumCtrl)


const SunCtrl = {
	extends: ControllerNode,
	computed: {
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


const AquapiNodeData = {
	props: {
		item: {
			type: Object,
			required: true
		},
	},
	template: `
        <v-row no-gutters>
            <div v-if="(999 == 111)">
                {{ item }}
            </div>
            <v-col cols="3"">
                <slot name="label">
                    Label
                </slot>
            </v-col>
            
            <v-col cols="9">
                <slot name="value">
                    Value
                </slot>
            </v-col>
        </v-row>
    `,

	computed: {}
}
Vue.component('AquapiNodeData', AquapiNodeData)
