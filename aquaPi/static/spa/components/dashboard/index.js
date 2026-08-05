import './comps.js'
import {registerGlobalComponent} from '../app/registry.js'
import {useUiStore} from '../../store/modules/ui.js'
import {useDashboardStore} from '../../store/modules/dashboard.js'

const AquapiDashboardConfigurator = {
	template: `
		<teleport to="body">
		<v-navigation-drawer
			:model-value="uiStore.isActiveDialog('AquapiDashboardConfigurator')"
			@update:model-value="(v) => (v ? null : hideConfigurator())"
			width="500"
			location="right"
			temporary
			:style="($vuetify.theme.global.current.dark ? 'max-width:100vw; background-color: rgba(33,33,33,0.7);' : 'max-width:100vw; background-color: rgba(255,255,255,0.7);')"
			id="dashboard_configurator"
		>
			<v-card elevation="0" color="transparent">
				<v-card-title class="d-flex flex-row pa-2">
					{{ $t('dashboard.configurator.headline') }}
					<v-spacer></v-spacer>
					<v-btn icon variant="text" color="grey-darken-1" @click.stop="hideConfigurator()">
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
					<div ref="widgetList">
						<v-card 
							v-for="(item, idx) in widgets"
							:key="item.identifier"
							class="d-flex flex-row align-center col col-12 mb-1 pa-0"
							elevation="0"
							variant="outlined"
							tile
						>
 						<v-btn icon tile variant="text" color="grey-darken-1" :ripple="false" class="handle">
 							<v-icon>
 								mdi-drag
 							</v-icon>
 						</v-btn>
 						<v-btn icon tile variant="text" color="grey-darken-1" :ripple="false" @click.stop="toggleVisibility(item)">
 							<v-icon :color="(item.visible ? 'green-lighten-2' : 'red-lighten-2')">
 								{{ (item.visible ? 'mdi-eye-outline' : 'mdi-eye-off-outline') }}
 							</v-icon>
 						</v-btn>
							<v-row class="ml-1 justify-space-between align-center">
								<v-col cols="7">
									<v-text-field
										v-model="item.name"
										variant="underlined"
										density="compact"
										hide-details="auto"
										class="pa-0 ma-0"
									></v-text-field>
								</v-col>
								<v-col>
									<div class="text-grey-darken-1">
										<v-icon size="small" color="grey" class="mr-1">{{ typeIcon(item) }}</v-icon>
										<span>{{ typeLabel(item) }}</span>
									</div>
								</v-col>
							</v-row>
						</v-card>
					</div>

				</v-card-text>

				<v-divider></v-divider>
				<v-card-actions>
					<v-btn block variant="flat" color="primary" @click.stop="persistConfig">
						{{ $t('dashboard.configurator.btnSave.label') }}
					</v-btn>
				</v-card-actions>
			</v-card>
		</v-navigation-drawer>
		</teleport>
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
				ALERTS: 'mdi-alert',
			}
		}
	},

	computed: {
		uiStore() {
			return useUiStore()
		},
		dashboardStore() {
			return useDashboardStore()
		},
		widgets: {
			get() {
				return this.dashboardStore.widgets
			},
			set(items) {
				this.dashboardStore.setWidgets(items)
			}
		},
	},

	methods: {
		showConfigurator() {
			this.uiStore.showDialog(this.dialogName)
		},
		hideConfigurator() {
			this.uiStore.hideDialog(this.dialogName)
		},
		toggleVisibility(item) {
			item.visible = !item.visible
		},
		reorderWidgets(from, to) {
			if (from === to) {
				return
			}
			const items = this.widgets.slice()
			const [moved] = items.splice(from, 1)
			items.splice(to, 0, moved)
			this.widgets = items
		},
		typeLabel(item) {
			return ['AUX', 'CTRL', 'HISTORY', 'IN_ENDP', 'OUT_ENDP', 'ALERTS'].includes(item.role)
				? this.$t('misc.nodeTypes.' + item.role.toLowerCase())
				: item.role
		},
		typeIcon(item) {
			return this.typeIcons[item.role]
				? this.typeIcons[item.role]
				: 'mdi-user'
		},
		persistConfig: async function() {
			const result = await this.dashboardStore.persistConfig(this.widgets)
			if (result) {
				this.$toast.success(this.$t('misc.toast.saveSuccess'))
			} else {
				this.$toast.error(this.$t('misc.toast.saveError'))
			}
			this.hideConfigurator()
		},
	},

	mounted() {
		this._sortable = Sortable.create(this.$refs.widgetList, {
			handle: '.handle',
			onEnd: (evt) => this.reorderWidgets(evt.oldIndex, evt.newIndex),
		})
	},
	unmounted() {
		if (this._sortable) {
			this._sortable.destroy()
			this._sortable = null
		}
	},
}
registerGlobalComponent('AquapiDashboardConfigurator', AquapiDashboardConfigurator)

const AquapiDashboardWidget = {
	template: `
		<v-card
			tile
			variant="outlined"
			elevation="3"
			:loading="false"
			class="pb-0"
			style="border-color: rgba(0,0,0,0.3);"
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
						:class="($vuetify.theme.global.current.dark ? 'text--darken-2' : 'text--lighten-4')"
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
				ALERTS: 'mdi-alert',
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
		dashboardStore() {
			return useDashboardStore()
		},
		node() {
			return this.dashboardStore.node(this.item.id)
		},
		nodes: {
			get() {
				return this.dashboardStore.nodes
			},
			set(items) {
				this.dashboardStore.setNodes(items)
			}
		},
		widgetTitleIcon() {
			let icon = null
			let w_key = this.item.role + '.' + this.item.type

			if (this.node) {
				w_key += '.' + this.node.rcv_unit.trim()
			}

			for (const k in this.typeIcons) {
				if (w_key.includes(k)) {
					icon = this.typeIcons[k];
					break
				}
			}
			return icon
		},

		alert() {
			if ((this.node == null) || (this.node.alert == null)) {
				return ''
			}
			return this.node.alert[0]
		},
		alertColor() {
			let ret = 'info lighten-1'
			if ((this.node == null) || (this.node.alert == null)) {
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
registerGlobalComponent('AquapiDashboardWidget', AquapiDashboardWidget)

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

				<div class="aquapi-dashboard-masonry" ref="masonryContainer">
					<div
						v-for="(column, colIndex) in columns"
						:key="colIndex"
						class="aquapi-dashboard-masonry-col"
					>
						<div 
							v-for="item in column" 
							:key="item.identifier"
							class="mb-6"
						>
							<aquapi-dashboard-widget
								:item="item"
								:addTitle="true"
							>
							</aquapi-dashboard-widget>
						</div>
					</div>
				</div>
			</v-card-text>
		</v-card>
	`,

	data() {
		return {
			containerWidth: (typeof window !== 'undefined' ? window.innerWidth : 1264),
		};
	},

	computed: {
		dashboardStore() {
			return useDashboardStore()
		},
		widgets: {
			get() {
				return this.dashboardStore.widgets.filter(item => item.visible)
			},
			set(items) {
				this.dashboardStore.setWidgets(items)
			}
		},
		nodes: {
			get() {
				return this.dashboardStore.nodes
			},
			set(items) {
				this.dashboardStore.setNodes(items)
			}
		},
		// measured from the dashboard's own masonry container (via
		// ResizeObserver, see mounted()) rather than the raw window width,
		// so the nav drawer's width/the container's padding are accounted
		// for; mirrors the old vue-masonry-css {default: 3, 1264: 3, 960: 2, 600: 1} breakpoints
		desiredColumns() {
			if (this.containerWidth >= 960) {
				return 3
			}
			if (this.containerWidth >= 600) {
				return 2
			}
			return 1
		},
		// never create more columns than there are visible widgets, so
		// toggling a widget's visibility never leaves a trailing column
		// completely empty
		columnCount() {
			return Math.min(this.desiredColumns, this.widgets.length || 1)
		},
		columns() {
			const cols = Array.from({length: this.columnCount}, () => [])
			this.widgets.forEach((item, i) => cols[i % this.columnCount].push(item))
			return cols
		},
	},

	methods: {
		showConfigurator() {
			useUiStore().showDialog('AquapiDashboardConfigurator')
			this.$nextTick(() => {
				document.querySelectorAll('#dashboard_configurator div.v-navigation-drawer__content')[0].scrollTo(0, 0)
			})
		},
		hideConfigurator() {
			useUiStore().hideDialog('AquapiDashboardConfigurator')
		},
		async loadConfig() {
			const result = await this.dashboardStore.loadConfig()
			if (result)	{
				this.widgets = result
			}
		},
	},
	async mounted() {
		await this.loadConfig()
		if (this.$refs.masonryContainer) {
			this.containerWidth = this.$refs.masonryContainer.getBoundingClientRect().width
			this._resizeObserver = new ResizeObserver((entries) => {
				this.containerWidth = entries[0].contentRect.width
			})
			this._resizeObserver.observe(this.$refs.masonryContainer)
		}
	},
	unmounted() {
		if (this._resizeObserver) {
			this._resizeObserver.disconnect()
			this._resizeObserver = null
		}
	},
}
registerGlobalComponent('AquapiDashboard', AquapiDashboard)
export {AquapiDashboard, AquapiDashboardConfigurator}

// vim: set noet sts ts=4 sw=4:
