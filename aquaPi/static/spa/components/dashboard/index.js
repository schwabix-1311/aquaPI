import './comps.js'
const AquapiDashboardConfigurator = {
	template: `
		<v-navigation-drawer
			v-show="$store.getters['ui/isActiveDialog']('AquapiDashboardConfigurator')"
			width="500"
			fixed
			right
			permanent
			:overlay-opacity="0.8"
			:style="'max-width:100vw;'"
		>
			<v-card elevation="0">
				<v-card-title class="d-flex flex-row pa-2">
					{{ $t('dashboard.configurator.headline') }}
					<v-spacer></v-spacer>
					<v-btn icon @click.stop="hideConfigurator()">
						<v-icon>
							mdi-close
						</v-icon>
					</v-btn>
				</v-card-title>				
				<v-card-subtitle class="pa-2">
					{{ $t('dashboard.configurator.hint') }}
				</v-card-subtitle>
				
				<v-divider></v-divider>
	
				<v-card-text class="pa-2">
					<draggable v-model="widgets" handle=".handle" direction="vertical">
						<v-card 
							v-for="(item, idx) in widgets"
							:key="item.identifier"
							class="d-flex flex-row align-center col col-12 mb-1 pa-0" 
							elevation="0"
							outlined
							tile
						>
							<v-btn icon tile :ripple="false" class="handle text--grey">
								<v-icon>
									mdi-drag
								</v-icon>
							</v-btn>
							<v-btn icon tile :ripple="false" @click.stop="toggleVisibility(item)">
								<v-icon :class="(item.visible ? 'green--text text--lighten-2' : 'red--text text--lighten-2')">
									{{ (item.visible ? 'mdi-eye-outline' : 'mdi-eye-off-outline') }}
								</v-icon>
							</v-btn>
							<v-row class="ml-1 justify-space-between align-center">
								<v-col cols="7">
									<v-text-field 
										v-model="item.name" 
										solo 
										flat 
										dense 
										hide-details="auto" 
										:background-color="($vuetify.theme.dark ? 'grey darken-4' : 'grey lighten-5')" 
										class="pa-0 ma-0"
									></v-text-field>
								</v-col>
								<v-col>
									<div class="grey--text text--darken-1">
										<v-icon small class="grey--text mr-1">{{ typeIcon(item) }}</v-icon>
										<span>{{ typeLabel(item) }}</span>
									</div>
								</v-col>
							</v-row>
						</v-card>
					</draggable>
	
				</v-card-text>	
				
				<v-divider></v-divider>
				<v-card-actions>
					<v-btn block color="primary" @click.stop="persistConfig">
						{{ $t('dashboard.configurator.btnSave.label') }}
					</v-btn>
				</v-card-actions>
			</v-card>
		</v-navigation-drawer>
	`,

	data: function() {
		return {
			dialogName: 'AquapiDashboardConfigurator',
			typeIcons: {
				AUX: 'mdi-merge',
				CTRL: 'mdi-speedometer',
				HISTORY: 'mdi-chart-line',
				IN_ENDP: 'mdi-location-enter',
				OUT_ENDP: 'mdi-location-exit',
			}
		}
	},

	computed: {
		widgets: {
			get() {
				return this.$store.getters['dashboard/widgets']
			},
			set(items) {
				this.$store.commit('dashboard/setWidgets', items)
			}
		},
	},

	methods: {
		showConfigurator() {
			this.$store.dispatch('ui/showDialog', this.dialogName)
		},
		hideConfigurator() {
			this.$store.dispatch('ui/hideDialog', this.dialogName)
		},
		toggleVisibility(item) {
			item.visible = !item.visible
		},
		typeLabel(item) {
			return ['AUX', 'CTRL', 'HISTORY', 'IN_ENDP', 'OUT_ENDP'].includes(item.role)
				? this.$t('misc.nodeTypes.' + item.role.toLowerCase())
				: item.role
		},
		typeIcon(item) {
			return this.typeIcons[item.role]
				? this.typeIcons[item.role]
				: 'mdi-user'
		},
		persistConfig: async function() {
			const result = await this.$store.dispatch('dashboard/persistConfig', this.widgets)
			this.hideConfigurator()
		},
	}
}
Vue.component('AquapiDashboardConfigurator', AquapiDashboardConfigurator)

const AquapiDashboardWidget = {
	template: `
		<v-card tile elevation="3" :loading="false">
			<v-card-title>
				<template v-if="widgetTitleIcon">
					<v-img
						v-if="(widgetTitleIcon.match(/\.svg$/))"
						:src="'static/' + widgetTitleIcon"
						max-height="24"
						max-width="24"
						class="mr-2"
					/>
					<v-icon
					    v-else 
						:color="'blue-grey'" 
						:class="($vuetify.theme.dark ? 'text--darken-2' : 'text--lighten-4')"
						left
					>
						{{ widgetTitleIcon }}
					</v-icon>
				</template>
				{{ item.name }}
			</v-card-title>

			<template v-if="(999 == 111)">
				<div style="border:1px solid lime">
					<strong>item:</strong> {{ item }}<br>
					<strong>node:</strong> {{ node }}
				</div>
			</template>
			
			<template v-if="node">
				<div v-if="(999 == 111)">
					[node.type: {{ node.type}} | node.name: {{ node.name}} | node.id: {{ node.id }} | node.identifier: {{ node.identifier }}]
				</div>
				<component :is="node.type" :id="node.identifier" :node="node"></component>
			</template>
		</v-card>
	`,
	props: {
		item: {
			type: Object,
			required: true
		},
	},
	data() {
		return {
			typeIcons: {
				AUX: 'mdi-merge',
				CTRL: 'mdi-speedometer',
				HISTORY: 'mdi-chart-line',
				IN_ENDP: 'mdi-location-enter',
				OUT_ENDP: 'mdi-location-exit',

				'CTRL#MinimumCtrl': 'min.svg', // 'min.svg'
				'CTRL#MaximumCtrl': 'max.svg', // 'max.svg'
				'MinimumCtrl#pH': 'gas_max.svg', // 'gas_min.svg'
				'MaximumCtrl#pH': 'gas_min.svg', // 'gas_max.svg'
				'SunCtrl#%': 'light.svg',
				'FadeCtrl#%': 'light.svg',

				'°C': 'thermo.svg',
				'MinimumCtrl#°C': 'thermo_min.svg',
				'MaximumCtrl#°C': 'thermo_max.svg',
				'°F': 'thermo.svg',
				'MinimumCtrl#°F': 'thermo_min.svg',
				'MaximumCtrl#°F': 'thermo_max.svg',
				// 'pH': 'gas.svg',
				// 'pH.min': 'gas_min.svg',
				// 'pH.max': 'gas_max.svg',
				// ' pH': 'gas.svg',
				// ' pH.min': 'gas_min.svg',
				// ' pH.max': 'gas_max.svg',
				'rH': 'faucet.svg',
				'MinimumCtrl#rH': 'faucet.svg',
				'MaximumCtrl#rH': 'faucet.svg',
				// ' rH': 'faucet.svg',
				// ' rH.min': 'faucet.svg',
				// ' rH.max': 'faucet.svg',
				'MinimumCtrl#%': 'min.svg',
				'MaximumCtrl#%': 'max.svg',
				// '%.min': 'min.',
				// '%.max': 'max.svg',
				// ' %.min': 'min.',
				// ' %.max': 'max.svg',
				'.min': 'min.svg',
				'.max': 'max.svg'
			}
		}
	},
	computed: {
		node() {
			return this.$store.getters['dashboard/node'](this.item.id)
		},
		nodes: {
			get() {
				return this.$store.getters['dashboard/nodes']
			},
			set(items) {
				this.$store.commit('dashboard/setNodes', items)
			}
		},
		widgetTitleIcon() {
			let icon = null
			let keys = []
			keys.push(this.item.role)
			if (this.item.role != 'HISTORY') {
				keys.push(this.item.type)
			}

			if (this.node) {
				let unit = this.node.unit ? this.node.unit.trim() : ''
				if (unit.length) {
					keys.push(unit)
				}
			}

			let key = keys.join('#')
			if (this.$data.typeIcons[key]) {
				return this.$data.typeIcons[key]
			}
			if (keys.length > 2) {
				key = [keys[1], keys[2]].join('#')
				if (this.$data.typeIcons[key]) {
					return this.$data.typeIcons[key]
				}

				key = [keys[0], keys[2]].join('#')
				if (this.$data.typeIcons[key]) {
					return this.$data.typeIcons[key]
				}
			}

			key = keys[0]
			if (this.$data.typeIcons[key]) {
				return this.$data.typeIcons[key]
			}

			if (keys.length > 2) {
				key = keys[2]
				if (this.$data.typeIcons[key]) {
					return this.$data.typeIcons[key]
				}
			}

			return icon
		}
	}
}
Vue.component('AquapiDashboardWidget', AquapiDashboardWidget)

const AquapiDashboard = {
	template: `
		<v-card elevation="0" tile>

			<aquapi-dashboard-configurator></aquapi-dashboard-configurator>
			
			<aquapi-page-heading 
				:heading="$t('pages.dashboard.heading')" 
				:icon="'mdi-view-dashboard'"
				:buttons="[{icon: 'mdi-apps', action: showConfigurator}]"
			></aquapi-page-heading>

			<v-card-text>
				<v-row justify="center">
					<v-col :cols="12" :md="6"
						v-if="!(widgets.length)"
					>
						<v-alert
							elevation="0"
							type="info"
							text
							:icon="'mdi-alert'"
						>
							# TODO: translation #  dashboard noch nicht konfiguriert<br>
							<div class="d-flex justify-end"> 
								<v-btn color="primary" class="mt-2" @click="showConfigurator">Widgets konfigurieren</v-btn>
							</div>
						</v-alert>     
					</v-col>
				</v-row>

				<v-row justify="start">
					<v-col :cols="12" :md="6"
						v-for="item in widgets"
						:key="item.identifier"
					>
						<aquapi-dashboard-widget
							:item="item"
						>
						</aquapi-dashboard-widget>

						<v-card v-if="999 == 111" elevation="3" :loading="false">
							{{ nodes[item.id] }}

							<v-card-title>
								{{ item.name}}
							</v-card-title>
							<v-card-subtitle>
								{{ item.identifier }}
							</v-card-subtitle>
							<v-card-text>
								{{ item }}
							</v-card-text>
							<v-card-actions>
								<v-btn small outlined>button 1</v-btn>
								<v-spacer></v-spacer>
								<v-btn color="primary">button 2</v-btn>
							</v-card-actions>
						</v-card>
					</v-col>
				</v-row>
			</v-card-text>
		</v-card>
    `,

	data: function() {
		return {
		};
	},

	computed: {
		widgets: {
			get() {
				return this.$store.getters['dashboard/widgets'].filter(item => item.visible)
			},
			set(items) {
				this.$store.commit('dashboard/setWidgets', items)
			}
		},
		nodes: {
			get() {
				return this.$store.getters['dashboard/nodes']
			},
			set(items) {
				this.$store.commit('dashboard/setNodes', items)
			}
		}
	},

	methods: {
		showConfigurator() {
			this.$store.dispatch('ui/showDialog', 'AquapiDashboardConfigurator')
		},
		hideConfigurator() {
			this.$store.dispatch('ui/hideDialog', 'AquapiDashboardConfigurator')
		},
		loadConfig: async function() {
			const result = await this.$store.dispatch('dashboard/loadConfig')
			if (result) {
				this.widgets = result
			}
		},
	},

	created: function() {
		this.loadConfig()
	},
}
Vue.component('AquapiDashboard', AquapiDashboard)
export {AquapiDashboard, AquapiDashboardConfigurator}

