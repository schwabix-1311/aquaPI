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
			id="dashboard_configurator"
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
			// FIXME: could be shared with DashboardWidgets.typeIcons
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
		<v-card 
			tile 
			outlined
			elevation="3" 
			:loading="false"
			class="pb-0"
		>
			<v-card-title
				class="pb-1"
			>
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
				
				<template
					v-if="alert"
				>
					<v-spacer />
					<v-chip
						v-if="alert"
						label
						:ripple="false"
						small
						:color="alertColor"
						text-color="white"
					>
						{{ alert }}
					</v-chip>
				</template>
			</v-card-title>

			<template v-if="node">
				<component 
					:is="node.type" 
					:id="node.identifier" 
					:node="node"
					:addNodeTitle="false"
					:level="1"
				></component>
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
			typeIcons: {	// <ES2015 would need a Map to keep the order
				// Order must be: most specialized to most generic!
				//
				// specialized controllers, unit doesn't matter
				'SunCtrl': 'sun.svg',
				'FadeCtrl': 'light.svg',

				// Min/Max, common units
				'MinimumCtrl.°C': 'thermo_min.svg',
				'MaximumCtrl.°C': 'thermo_max.svg',
				'MinimumCtrl.°F': 'thermo_min.svg',
				'MaximumCtrl.°F': 'thermo_max.svg',
				'MinimumCtrl.rH': 'faucet.svg',
				'MaximumCtrl.rH': 'faucet.svg',
				'MinimumCtrl.pH': 'gas_min.svg',
				'MaximumCtrl.pH': 'gas_max.svg',

				// Min/Max, uncommon/undef unit
				'MinimumCtrl': 'min.svg',
				'MaximumCtrl': 'max.svg',

				// ?? unit, controller type doesn't matter
				'°C': 'thermo.svg',
				'°F': 'thermo.svg',
				'pH': 'gas.svg',
				'rH': 'faucet.svg',
				//'V': 'probe.png', -> svg

				// generic by role
				AUX: 'mdi-merge',
				CTRL: 'mdi-speedometer',
				HISTORY: 'mdi-chart-line',
				IN_ENDP: 'mdi-location-enter',
				OUT_ENDP: 'mdi-location-exit',
			},
			severityMap: {
				'act': 'success',
				'wrn': 'warning',
				'err': 'error',
				'std': 'info lighten-1'
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
			let w_key = this.item.role + '.' + this.item.type

			if (this.node) {
				w_key += '.' + this.node.unit.trim()
			}
			//w_key = w_key.replace('HISTORY', '')

			for (const k in this.typeIcons) {
				if (w_key.includes(k)) {
					icon = this.typeIcons[k];
					break
				}
			}
			return icon
		},

		alert() {
			if ((this.node == null) || !('alert' in this.node)) {
				return ''
			}
			return this.node.alert[0]
		},
		alertColor() {
			let ret = 'info lighten-1'
			if ((this.node == null) || !('alert' in this.node)) {
				return ret
			}
			const severity = this.node.alert[1]
			if (severity in this.severityMap) {
				ret = this.severityMap[severity]
			} else {
				console.warn('Unknown alert severity: "' + severity + '" used by ' + this.id)
			}
			return ret
		},
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

			<v-card-text class="aquapi-dashboard">
				<v-row 
					v-if="!(widgets.length)"
					justify="center"
					class="mb-3"
				>
					<v-col :cols="12" :md="6">
						<v-alert
							elevation="0"
							type="info"
							text
							:icon="'mdi-alert'"
						>
							{{ $t('dashboard.configuration.hintEmpty') }}<br>
							<div class="d-flex justify-end">
								<v-btn color="primary" class="mt-2" @click="showConfigurator">
									{{ $t('dashboard.configuration.btnSetup') }}
								</v-btn>
							</div>
						</v-alert>
					</v-col>
				</v-row>

				<masonry
					:cols="{default: 3, 1264: 3, 960: 2, 600: 1}"
					:gutter="24"
				>
					<div 
						v-for="(item, index) in widgets" 
						:key="index"
						class="mb-6"
					>
						<aquapi-dashboard-widget
							:item="item"
						>
						</aquapi-dashboard-widget>
					</div>
				</masonry>
			</v-card-text>
		</v-card>
	`,

	data() {
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
			this.$nextTick(() => {
				document.querySelectorAll('#dashboard_configurator div.v-navigation-drawer__content')[0].scrollTo(0, 0)
			})
		},
		hideConfigurator() {
			this.$store.dispatch('ui/hideDialog', 'AquapiDashboardConfigurator')
		},
		async loadConfig() {
			const result = await this.$store.dispatch('dashboard/loadConfig')
			if (result) {
				this.widgets = result
			}
		},
	},

	created() {
		this.loadConfig()
	},
}
Vue.component('AquapiDashboard', AquapiDashboard)
export {AquapiDashboard, AquapiDashboardConfigurator}

// vim: set noet ts=4:
