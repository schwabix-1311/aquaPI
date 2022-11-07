/* This is a collection of Vue components that match the bus nodes
 *
 * We do not use a build step!
 *
 * Each type of bus node should have a matching type of Vue component,
 * however there will be a mechanism to fall back on anchestors, to allow
 * quick implementation (import?) of new nodes W/O a Vue component
 */


// IDEA: add UIkit.Drop to show details


// SVG edit e.g. in LibreOffice.Draw, then https://iconly.io/tools/svg-cleaner (6K -> 1.5k!)
const unit2icon = new Map([
    ['°C', 'thermo.svg'],
    ['°C.min', 'thermo_min.svg'],
    ['°C.max', 'thermo_max.svg'],
    ['°F', 'thermo.svg'],
    ['°F.min', 'thermo_min.svg'],
    ['°F.max', 'thermo_max.svg'],
    ['pH', 'gas.svg'],
    ['pH.min', 'gas_min.svg'],
    ['pH.max', 'gas_max.svg'],
    ['rH', 'faucet.svg'],
    ['rH.min', 'faucet.svg'],
    ['rH.max', 'faucet.svg'],
    ['%.min', 'min.'],
    ['%.max', 'max.svg'],
    ['.min', 'min.'],
    ['.max', 'max.svg'],
]);

const AnyNode = {
    delimiters: ['[[', ']]'],
    props: {
        id: String
    },
    async beforeMount () {
        this.$root.updateNode(this.id, addNew=true)
    },
    computed: {
        node() {
            if (this.id in this.$root.nodes)
                return this.$root.nodes[this.id]
            // may be undefined beforeMount
            return undefined
        },
    },
};

const DebugNode = {
    extends: AnyNode,
    template: `
          <div class="uk-card uk-card-small uk-card-default">
            <div class="uk-card-header">
              <h2 class="uk-card-title uk-margin-remove-bottom">
                [[ id ]] - raw:
              </h2>
            </div>
            <div class="uk-card-body uk-padding-remove">
              <div class="uk-grid-collapse" uk-grid>
                <div>
                  [[ $root.nodes[id] ]]
                </div>
              </div>
            </div>
          </div>
    `
};
Vue.component('DebugNode', DebugNode);

const BusNode = {
    extends: AnyNode,
    computed: {
        getLabel() {
            return this.node?.render_data['label']
        },
        getPrettyData() {
            try {
                return this.node?.render_data['pretty_data']
            }
            catch {
                return this.node?.data.toFixed(2)
            }
        },
        getAlert() {
            if ((this.node === undefined) || !('alert' in this.node.render_data))
                return ''
            return this.node.render_data['alert'][0]
        },
        getAlertClass() {
            if ((this.node === undefined) || !('alert' in this.node.render_data))
                return ''
            const severity_map = { 'act': 'uk-label-success'
                                 , 'wrn': 'uk-label-warning'
                                 , 'err': 'uk-label-danger'
                                 , 'std': 'uk-label-default'
                                 }
            let ret = "uk-card-badge uk-label "
            severity = this.node.render_data['alert'][1]
            try {
                ret += severity_map[severity]
            }
            catch {
                console.warn('Unknown alert severity: "' + severity + '" used by ' + this.id)
            }
            return ret
        }
    },
    template: `
          <div class="uk-card uk-card-small uk-card-default">
            <div class="uk-card-header">
              <h2 class="uk-card-title uk-margin-remove-bottom">
                <span v-if="node != undefined">[[ node.name ]]</span>
                <span v-else>[[ id ]] loading ...</span>
              </h2>
              <div :hidden="!getAlert">
                <div v-bind:class="getAlertClass">[[ getAlert ]]</div>
              </div
            </div>
            <div v-if="node != undefined" class="uk-card-body uk-padding-remove">
              <div class="uk-grid-collapse" uk-grid>
                <div class="uk-width-2-3">
                  [[ getLabel ]]
                </div
                <div class="uk-width-expand">
                  [[ getPrettyData ]]
                </div>
              </div>
            </div>
          </div>
    `
};
Vue.component('BusNode', BusNode);

const CtrlNode = {
    extends: BusNode,
    async beforeMount () {
        await this.$root.updateNode(this.id, addNew=true)

        // recurse all inputs? Advanced Ctrl have a chain and n:1
        this.in_id = this.node.inputs.sender[0]
        await this.$root.updateNode(this.in_id, addNew=true)
    },
    computed: {
        decoration() {
            return ''
        }
    },
    template: `
          <div class="uk-card uk-card-small uk-card-default">
            <div class="uk-card-header">
              <h1 class="uk-card-title uk-margin-remove-bottom">
                <span v-if="node != undefined">
                  Controller [[ node.name ]]
                </span>
                <span v-else>[[ id ]] loading ...</span>
              </h1>
              <div :hidden="!getAlert">
                <div v-bind:class="getAlertClass">[[ getAlert ]]</div>
              </div
            </div>

            <div v-if="node != undefined" class="uk-card-body uk-padding-remove">
              <div class="uk-grid-collapse" uk-grid>
                <div class="uk-width-2-3">
                  [[ getLabel ]]
                </div
                <div class="uk-width-expand">
                  [[ getPrettyData ]]
                </div>
              </div>
              <component is='BusNode' :id='in_id' ></component><br/>
            </div>
          </div>
    `
};
Vue.component('CtrlNode', CtrlNode);

const CtrlMinimum = {
    extends: CtrlNode,
    computed: {
        decoration() {
            ret = ''
            if (this.node !== undefined)
                icon = unit2icon.get(this.node.unit + '.min')
                if (icon !== undefined)
                    ret += `<img src="static/${icon}" style="width:24px;height:24px;">`
                //ret += '<span uk-icon="icon: arrow-up; ratio: 1"></span>'
            return ret
        }
    },
    template: `
          <div class="uk-card uk-card-small uk-card-default">
            <div class="uk-card-header">
              <h1 class="uk-card-title uk-margin-remove-bottom">
                <span v-if="node != undefined">
                  <span v-html="decoration"></span>[[ node.name ]]
                </span>
                <span v-else>[[ id ]] loading ...</span>
              </h1>
              <div :hidden="!getAlert">
                <div v-bind:class="getAlertClass">[[ getAlert ]]</div>
              </div
            </div>

            <div v-if="node != undefined" class="uk-card-body uk-padding-remove">
              <div class="uk-grid-collapse" uk-grid>
                <div class="uk-width-2-3">
                  <img style="width:36px">Status
                </div
                <div class="uk-width-expand">
                  [[ node.data ? 'Ein' : 'Aus' ]]
                </div>
              </div>
              <component is='BusNode' :id='in_id' ></component><br/>
            </div>
          </div>
    `
};
Vue.component('CtrlMinimum', CtrlMinimum);

const CtrlMaximum = {
    extends: CtrlNode,
    computed: {
        decoration() {
            ret = ''
            if (this.node !== undefined)
                icon = unit2icon.get(this.node.unit + '.max')
                if (icon !== undefined)
                    ret += `<img src="static/${icon}" style="width:24px;height:24px;">`
                //ret += '<span uk-icon="icon: arrow-down; ratio: 1"></span>'
            return ret
        }
    },
    template: `
          <div class="uk-card uk-card-small uk-card-default">
            <div class="uk-card-header">
              <h1 class="uk-card-title uk-margin-remove-bottom">
                <span v-if="node != undefined">
                  <span v-html="decoration"></span>[[ node.name ]]
                </span>
                <span v-else>[[ id ]] loading ...</span>
              </h1>
              <div :hidden="!getAlert">
                <div v-bind:class="getAlertClass">[[ getAlert ]]</div>
              </div
            </div>

            <div v-if="node != undefined" class="uk-card-body uk-padding-remove">
              <div class="uk-grid-collapse" uk-grid>
                <div class="uk-width-2-3">
                  <img style="width:36px">Status
                </div
                <div class="uk-width-expand">
                  [[ node.data ? 'Ein' : 'Aus' ]]
                </div>
              </div>
              <component is='BusNode' :id='in_id' ></component><br/>
            </div>
          </div>
    `
};
Vue.component('CtrlMaximum', CtrlMaximum);

const CtrlLight = {
    extends: CtrlNode,
    computed: {
        decoration() {
            ret = ''
            if (this.node !== undefined)
                ret = '<img src="static/light.svg" style="width:24px;height:24px;">'
            return ret
        }
    },
    template: `
          <div class="uk-card uk-card-small uk-card-default">
            <div class="uk-card-header">
              <h1 class="uk-card-title uk-margin-remove-bottom">
                <span v-if="node != undefined">
                  <span v-html="decoration"></span>[[ node.name ]]
                </span>
                <span v-else>[[ id ]] loading ...</span>
              </h1>
              <div :hidden="!getAlert">
                <div v-bind:class="getAlertClass">[[ getAlert ]]</div>
              </div
            </div>

            <div v-if="node != undefined" class="uk-card-body uk-padding-remove">
              <div class="uk-grid-collapse" uk-grid>
                <div class="uk-width-2-3">
                  <img style="width:36px">Status
                </div
                <div class="uk-width-expand">
                  [[ node.data==100 ? 'Ein' : node.data == 0 ? 'Aus' : node.data.toFixed(2).toString() + node.unit ]]
                </div>
              </div>
              <component is='BusNode' :id='in_id' ></component><br/>
            </div>
          </div>
    `
};
Vue.component('CtrlLight', CtrlLight);
