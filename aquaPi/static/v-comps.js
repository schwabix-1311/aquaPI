/* This is a collection of Vue components that match the bus nodes
 *
 * We do not use a build step!
 *
 * Each type of bus node should have a matching type of Vue component,
 * however there will be a mechanism to fall back on anchestors, to allow
 * quick implementation (import?) of new nodes W/O a Vue component
 */


// IDEA: add UIkit.Drop to show details, add uk-card-hover for future switch panel, uk-media-bottom +uk-cover-container? for charts


// SVG edit e.g. in LibreOffice.Draw, then https://iconly.io/tools/svg-cleaner (6K -> 1.5k!)
const unit2icon = {
    '°C': 'thermo.svg',
    '°C.min': 'thermo_min.svg',
    '°C.max': 'thermo_max.svg',
    '°F': 'thermo.svg',
    '°F.min': 'thermo_min.svg',
    '°F.max': 'thermo_max.svg',
    'pH': 'gas.svg',
    'pH.min': 'gas_min.svg',
    'pH.max': 'gas_max.svg',
    'rH': 'faucet.svg',
    'rH.min': 'faucet.svg',
    'rH.max': 'faucet.svg',
    '%.min': 'min.',
    '%.max': 'max.svg',
    '.min': 'min.',
    '.max': 'max.svg'
};

const severity_map = {
    'act': 'uk-label-success',
    'wrn': 'uk-label-warning',
    'err': 'uk-label-danger',
    'std': 'uk-label-default'
};


const AnyNode = {
    delimiters: ['[[', ']]'],
    props: {
        id: String
    },
    created: async function () {
        this.in_ids = []
        // console.debug(`AnyNode: create ${this.id} ...`)
        await this.$root.updateNode(this.id, true)
        // console.debug(`... Any create ${this.id} done`)
        if (this.node.inputs?.sender != null) {
            this.in_ids = this.node.inputs.sender
            if (this.in_ids == '*')
                this.in_ids = []
            // console.debug(`... INs of ${this.id}:  ${this.in_ids}`)
            for (let in_id of this.in_ids)
                await this.$root.updateNode(in_id, true)
        }
    },
    computed: {
        node() {
            // console.debug(`get node(${this.id})`)
            if (this.id in this.$root.nodes) {
            // console.debug(`  .. got node(${this.id})`)
                return this.$root.nodes[this.id]
            }
            //  console.debug(`  .. NO node(${this.id})`)
            return undefined
        },
        label() {
            if (this.decoration === '')
                return 'Status'
            else
                return '<img style="width:24px">Status'
        },
        value() {
            return this.node?.data.toFixed(2).toString() + this.node?.unit
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
    template: `
          <div class="uk-card uk-card-small uk-card-default uk-card-body">
            <h2 class="uk-card-title uk-margin-remove-bottom">
              <span v-if="node != undefined">
                <span v-html="decoration"></span>[[ node.name ]]
              </span>
              <span v-else>[[ id ]] loading ...</span>
            </h2>
            <div v-html="getAlert" v-bind:class="getAlertClass" :hidden="!getAlert"></div>
            <div v-if="node != undefined" class="uk-padding-remove">
              <div class="uk-grid-collapse" uk-grid>
                <div class="uk-width-2-3" v-html="label"></div>
                <div class="uk-width-expand" v-html="value"></div>
              </div>
            </div>
          </div>
    `
};
Vue.component('BusNode', BusNode);


const ControllerNode = {
    extends: BusNode,
    computed: {
        value() {
            return this.node?.data ? 'Ein' : 'Aus'
        },
    },
    template: `
          <div class="uk-card uk-card-small uk-card-default uk-card-body">
            <h2 class="uk-card-title uk-margin-remove-bottom">
              <span v-if="node != undefined">
                <span v-html="decoration"></span>[[ node.name ]]
              </span>
              <span v-else>[[ id ]] loading ...</span>
            </h2>
            <div :hidden="!getAlert">
              <div v-bind:class="getAlertClass">[[ getAlert ]]</div>
            </div>
            <div v-if="node != undefined" class="uk-padding-remove">
              <div class="uk-grid-collapse" uk-grid>
                <div class="uk-width-2-3" v-html="label"></div>
                <div class="uk-width-expand" v-html="value"></div>
              </div>
              <div v-if="in_ids[0] in $root.nodes">
                <component :is="$root.nodes[in_ids[0]].cls" :id="in_ids[0]" ></component>
              </div>
            </div>
          </div>
    `
};

const MinimumCtrl = {
    extends: ControllerNode,
    computed: {
        decoration() {
            let ret = ''
            if ((this.node !== undefined) && ('unit' in this.node))
                if (this.node.unit + '.min' in unit2icon) {
                    let icon = unit2icon[this.node.unit + '.min']
                    ret += `<img src="static/${icon}" style="width:24px;height:24px;">`
                }
            return ret
        },
    },
};
Vue.component('MinimumCtrl', MinimumCtrl);

const MaximumCtrl = {
    extends: ControllerNode,
    computed: {
        decoration() {
            let ret = ''
            if ((this.node !== undefined) && ('unit' in this.node))
                if (this.node.unit + '.max' in unit2icon) {
                    let icon = unit2icon[this.node.unit + '.max']
                    ret += `<img src="static/${icon}" style="width:24px;height:24px;">`
                }
            return ret
        },
    },
};
Vue.component('MaximumCtrl', MaximumCtrl);

const LightCtrl = {
    extends: ControllerNode,
    computed: {
        decoration() {
            let ret = ''
            if (this.node !== undefined)
                ret = '<img src="static/light.svg" style="width:24px;height:24px;">'
            return ret
        },
        value() {
            return this.node?.data == 100 ? 'Ein'
                : this.node?.data == 0 ? 'Aus'
                    : this.node?.data.toFixed(2).toString() + this.node?.unit
        },
    },
};
Vue.component('LightCtrl', LightCtrl);


const SwitchInput = {
    extends: BusNode,
    computed: {
        label() {
            if (this.decoration === '')
                return 'Zustand'
            else
                return '<img style="width:24px">Zustand'
        },
        value() {
            return this.node?.data ? 'Ein' : 'Aus'
        },
    },
};
Vue.component('SwitchInput', SwitchInput);

const AnalogInput = {
    extends: BusNode,
    computed: {
        label() {
            if (this.decoration === '')
                return 'Messwert'
            else
                return '<img style="width:24px">Messwert'
        },
        value() {
            return this.node?.data.toFixed(2).toString() + this.node?.unit
        },
    },
};
Vue.component('AnalogInput', AnalogInput);

const ScheduleInput = {
    extends: BusNode,
    computed: {
        label() {
            if (this.decoration === '')
                return 'Schaltzustand'
            else
                return '<img style="width:24px">Schaltzustand'
        },
        value() {
            return this.node?.data ? 'Ein' : 'Aus'
        },
    },
};
Vue.component('ScheduleInput', ScheduleInput);


const SwitchDevice = {
    extends: BusNode,
    computed: {
        label() {
            if (this.decoration === '')
                return 'Schalter'
            else
                return '<img style="width:24px">Schalter'
        },
        value() {
            return this.node?.data ? 'Ein' : 'Aus'
        },
    },
};
Vue.component('SwitchDevice', SwitchDevice);

const AnalogDevice = {
    extends: BusNode,
    computed: {
        label() {
            if (this.decoration === '')
                return 'Ausgang'
            else
                return '<img style="width:24px">Ausgang'
        },
        value() {
            return this.node?.data.toFixed(2).toString() + this.node?.unit
        },
    },
};
Vue.component('AnalogDevice', AnalogDevice);


const AuxNode = {
    extends: BusNode,
    template: `
          <div class="uk-card uk-card-small uk-card-default uk-card-body">
            <h2 class="uk-card-title uk-margin-remove-bottom">
              <span v-if="node != undefined">
                <span v-html="decoration"></span>[[ node.name ]]
              </span>
              <span v-else>[[ id ]] loading ...</span>
            </h2>
            <div :hidden="!getAlert">
              <div v-bind:class="getAlertClass">[[ getAlert ]]</div>
            </div>
            <div v-if="node != undefined" class="uk-padding-remove">
              <div class="uk-grid-collapse" uk-grid>
                <div class="uk-width-2-3" v-html="label"></div>
                <div class="uk-width-expand" v-html="value"></div>
              </div>
              <div v-for="in_id in in_ids" >
                <div v-if="in_id in $root.nodes">
                  <component :is="$root.nodes[in_id].cls" :id="in_id" ></component>
                </div>
              </div>
            </div>
          </div>
    `
};

const AvgAux = {
    extends: AuxNode,
    computed: {
        label() {
            if (this.decoration === '')
                return 'ø'
            else
                return '<img style="width:24px">ø'
        },
    },
};
Vue.component('AvgAux', AvgAux);

const MaxAux = {
    extends: AuxNode,
    computed: {
        label() {
            if (this.decoration === '')
                return 'Max'
            else
                return '<img style="width:24px">Max'
        },
    },
};
Vue.component('MaxAux', MaxAux);


const History = {
    extends: AnyNode,
    created: function() {
      this.chart = null;
      this.cd = {
        type: "scatter", //"line",
        data: {
          labels: [],
          datasets: [],
        },
        options: {
          responsive: true,
          //aspectRatio: 1,
          maintainAspectRatio: true, 
          showLine: true,
          borderWidth: 1,
          lineTension: 0,
          stepped: true, //false,
          pointRadius: 0,
          legend: { labels: { boxWidth: 2, }, position: "top", },
          animation: { duration: 1500, easing: "easeInOutQuart", },
          scales: {
//            x: {type: 'time', time: {unit: 'second'} },
//            y: [ {ticks: {beginAtZero: true, padding: 25}} ],
          }
        }
      };
    },
    destroyed: function() {
      if (this.chart != null)
        this.chart.destroy();
      this.chart = null;
    },
    beforeUpdate: function() {
      if (this.chart == null) {
        const el = document.querySelector("canvas");
        if (el != null) {

          this.chart = new Chart(el, this.chartData);
        }
      } else {
        this.chartData;
        this.chart.update();
      }
    },
    computed: {
      chartData() {
        let store = this.$root.nodes[this.id]?.store;
        if (store != null) {
          ds_index = 0;
          for (let series in store) {
            if (ds_index >= this.cd.data.datasets.length) {
              this.cd.data.datasets.push( {
                label: this.$root.nodes[series].name,
                data:  [],
                backgroundColor: "rgba(224, 248, 255, 0.4)",  // -> table
                borderColor: "#5cddff",
                pointBackgroundColor: "#5cddff",
              });
              if (this.$root.nodes[series].unit == '')  //TODO replace with node.OUT_TYPE!=ANALOG
                this.cd.data.datasets[ds_index].stepped = true;
            }

            const now = new Date().getTime() / 1000;

        //FIXME: indices shift

            this.cd.data.datasets[ds_index].data = []
            for (let val of store[series]) {
              this.cd.data.datasets[ds_index].data.push({ x: val[0], y: val[1]});
              if (ds_index == 0) {
                let d = (now - val[0]).toFixed(0);
                if (d < 60) {
                  this.cd.data.labels.push(`-${d}s`);
                } else if (d < 60*60) {
                  d = (d / 60).toFixed(1);
                  this.cd.data.labels.push(`-${d}m`);
                } else if (d < 60*60*24) {
                  d = (d / (60*60)).toFixed(1);
                  this.cd.data.labels.push(`-${d}m`);
                } else {
                  d = (d / (60*60*24)).toFixed(2);
                  this.cd.data.labels.push(`-${d}d`);
                }
              }
            }
            ds_index += 1
          }
          //this.refreshed = new Date().toLocaleString()
        }
console.warn("Update")
console.debug(this.cd);        
        return this.cd;
      },
    },
    template: `
          <div class="uk-card uk-card-small uk-card-default">
            <div class="uk-card-header">
              <h2 class="uk-card-title uk-margin-remove-bottom">
              <span v-if="node != null">[[ node.name ]]</span>
              <span v-else>[[ id ]] loading ...</span>
              </h2>
            </div>
            <div v-if="node != null" class="uk-padding-remove">
              <div class="uk-grid-collapse" uk-grid>
                <canvas></canvas>
              </div>
            </div>
          </div>
    `
};
Vue.component('History', History);
