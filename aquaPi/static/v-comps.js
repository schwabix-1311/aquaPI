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
	' pH': 'gas.svg',
	' pH.min': 'gas_min.svg',
	' pH.max': 'gas_max.svg',
	'rH': 'faucet.svg',
	'rH.min': 'faucet.svg',
	'rH.max': 'faucet.svg',
	' rH': 'faucet.svg',
	' rH.min': 'faucet.svg',
	' rH.max': 'faucet.svg',
	'%.min': 'min.',
	'%.max': 'max.svg',
	' %.min': 'min.',
	' %.max': 'max.svg',
	'.min': 'min.',
	'.max': 'max.svg'
};

const severity_map = {
	'act': 'uk-label-success',
	'wrn': 'uk-label-warning',
	'err': 'uk-label-danger',
	'std': 'uk-label-default'
};

const RangeAnalog = 1;
const RangeBinary = 2;
const RangePercent = 3;
const RangePerc_3 = 4;

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

		// console.log(this.node.inputs.sender)
		if (this.node.inputs?.sender != null) {
			this.in_ids = this.node.inputs.sender
			if (this.in_ids == '*')
				this.in_ids = []
			console.debug(`... INs of ${this.id}:  ${this.in_ids}`)
			for (let in_id of this.in_ids)
				await this.$root.updateNode(in_id, true)
		}
	},
	computed: {
		node() {
			console.debug(`get node(${this.id})`)
			if (this.id in this.$root.nodes) {
				console.debug(`  .. got node(${this.id})`)
				return this.$root.nodes[this.id]
			}
			 console.debug(`  .. NO node(${this.id})`)
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

const FadeCtrl = {
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
Vue.component('SunCtrl', FadeCtrl);  // temporary alias
Vue.component('FadeCtrl', FadeCtrl);


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

const CalibrationAux = {
	extends: AuxNode,
	computed: {
		label() {
			if (this.decoration === '')
				return 'Calibration'
			else
				return '<img style="width:24px">Max'
		},
	},
};
Vue.component('CalibrationAux', CalibrationAux);


const History = {
	extends: AnyNode,
	created: function() {
	  this.chart = null;
	},
	destroyed: function() {
	  if (this.chart != null)
		this.chart.destroy();
	  this.chart = null;
	},
	beforeUpdate: function() {
	  if (this.chart == null) {
		const el = document.getElementById(this.id);
		if (el != null) {
		  this.chart = new Chart(el, this.chartData);
		}
	  } else {
		this.chartData;  // trigger a re-compute, $data wasn't touched
		this.chart.update();
	  }
	},
	data: function() {
	  return {
		duration: (60 * 60 * 1000) * 1, //hour(s)
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
			  tooltip: {caretPadding: 24},
			},	//top"},
			animation: {duration: 1500, easing: "easeInOutBack"},
			interaction: {mode: "x", axis: "x", intersect: false},
			scales: {
			  x: {
				type: "time",
				min: Date.now() - this.duration, max: Date.now(),
				time: {
				  //unit: "minutes",
				  //unit: "hours",
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
	  chartData() {
		let store = this.$root.nodes[this.id]?.store;
		if (store != null) {
		  const now = Date.now();
		  ds_index = 0;
		  for (let series in store) {
			if (ds_index >= this.cd.data.datasets.length) {
			  this.cd.data.datasets.push( {
				label: this.$root.nodes[series].name,
				data:  [],
			  });
//				if (this.$root.nodes[series].unit != "" &&
//					"°C°FpHrHGHKHµSuS".includes(this.$root.nodes[series].unit)) {  //?? replace with node.OUT_TYPE!=ANALOG
			  if (this.$root.nodes[series].data_range == "ANALOG") {
				this.cd.data.datasets[ds_index].stepped = false;
				this.cd.data.datasets[ds_index].yAxisID = "yAnalog";
			  }
			}

//FIXME: indices shift

			this.cd.data.datasets[ds_index].data = [];
			for (let val of store[series]) {
			  this.cd.data.datasets[ds_index].data.push({x: val[0] * 1000, y: val[1]});
			}
			this.cd.data.datasets[ds_index].data.push({x: now, y: this.$root.nodes[series].data});
			ds_index += 1;
		  }
		  this.cd.options.scales.x.min = now - this.duration;
		  this.cd.options.scales.x.max = now;
		}
		return this.cd;
	  },
	},
	methods: {
	  toggle_duration() {
		const dur = this.duration / 60 / 1000; //mins
		if (dur < 60)
		  this.duration = 60;
		else if (dur < 8 * 60)
		  this.duration = 8 * 60;
		else if (dur < 24 * 60)
		  this.duration = 24 * 60;
		else
		  this.duration = 15;
		this.duration *= 60 * 1000;
	  },
	  human_duration() {
		let dur = this.duration / 60 / 1000; // mins
		if (dur < 60)
		  return `${dur}min`
		dur /= 60;
		return `${dur}h`
	  }
	},
/*			  <div v-if="node != null" class="uk-padding-remove">
			  <div class="uk-grid-collapse" uk-grid>
				<canvas :id="id"></canvas>
			  </div>
			</div> */
	template: `
		<div class="uk-card uk-card-small uk-card-default">
			<div class="uk-card-header">
				<h2 class="uk-card-title">
					<span v-if="node != null">[[ node.name ]]</span>
					<span v-else>[[ id ]] loading ...</span>
					<button class="uk-align-right" @click="toggle_duration">Dauer [[ human_duration() ]]</button>
					<div v-if="node != null" class="uk-padding-remove">
						<canvas :id="id"></canvas>
					</div>
				</h2>
			</div>
		</div>
	`
};
Vue.component('History', History);

// vim: set noet ts=4 sw=4:
