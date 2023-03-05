
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
    created: async function () {
        this.in_ids = []

        console.log('[AnyNode] CREATED | this:', this)
        // if (this.node.inputs?.sender != null) {
        //     this.in_ids = this.node.inputs.sender
        //     if (this.in_ids == '*')
        //         this.in_ids = []
        //     console.debug(`... INs of ${this.id}:  ${this.in_ids}`)
        //     for (let in_id of this.in_ids)
        //         await this.$root.updateNode(in_id, true)
        // }
    },
    computed: {
		// node() {
		// 	return this.nodes[this.item.id]
		// },
		nodes() {
			return this.$store.getters['dashboard/nodes']
		},
        label() {
            return this.decoration == '' ? 'Status' :  '<img style="width:24px">Status'
        },
        value() {
            return this.node?.data.toFixed(2).toString() + this.node?.unit
        },
    },
}
Vue.component('AnyNode', AnyNode)

const DebugNode = {
    extends: AnyNode,
    template: `
          <div class="uk-card uk-card-small uk-card-default" style="border: 1px solid red;">
            <div class="uk-card-header">
              <h2 class="uk-card-title uk-margin-remove-bottom">
                {{ id }} - raw:
              </h2>
            </div>
            <div class="uk-card-body uk-padding-remove">
              <div class="uk-grid-collapse" uk-grid>
                <div>
                  {{ node }}
                </div>
              </div>
            </div>
          </div>
    `
}
Vue.component('DebugNode', DebugNode)


const BusNode = {
    extends: AnyNode,
    template: `
          <div class="uk-card uk-card-small uk-card-default uk-card-body" style="border: 1px solid blue;">
            (BusNode)
            <h2 class="uk-card-title uk-margin-remove-bottom">
              <span v-if="node != undefined">
                <span v-html="decoration"></span>{{ node.name }}
              </span>
              <span v-else>{{ id }} loading ...</span>
            </h2>
            <div v-html="getAlert" v-bind:class="getAlertClass" :hidden="!getAlert"></div>
            <div v-if="node != undefined" class="uk-padding-remove">
              <div class="uk-grid-collapse" uk-grid>
                <div class="uk-width-2-3" v-html="label"></div>
                <div class="uk-width-expand" v-html="value"></div>
              </div>
            </div>
          </div>
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


const LightCtrl = {
    extends: ControllerNode,
}
Vue.component('LightCtrl', LightCtrl)

const SunCtrl = {
    extends: ControllerNode,
}
Vue.component('SunCtrl', SunCtrl)


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
    // template: `
    //     <div style="border: 1px solid orange">
    //         (ScheduleInput)
    //     </div>
    // `
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
