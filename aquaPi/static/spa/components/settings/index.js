import './comps.js'
import {registerGlobalComponent} from '../app/registry.js'

const AquapiSettings = {
	template: `
		<v-card elevation="0" tile>
			<aquapi-page-heading
				:heading="$t('pages.settings.heading')"
				:icon="'mdi-tune'"
			></aquapi-page-heading>

			<v-card-text>
				<v-row v-if="loading" justify="center">
					<v-col cols="12" class="text-center pa-10">
						<aquapi-loading-indicator></aquapi-loading-indicator>
					</v-col>
				</v-row>

				<v-row v-else-if="!controllers.length" justify="center">
					<v-col cols="12" md="6">
						<v-alert elevation="0" type="info" text :icon="'mdi-info'">
							{{ $t('pages.settings.hintEmpty') }}
						</v-alert>
					</v-col>
				</v-row>

				<v-expansion-panels v-else multiple v-model="openPanels" tile>
					<v-expansion-panel
						v-for="(items, group) in grouped"
						:key="group"
					>
						<v-expansion-panel-title class="py-0 px-4">
							{{ group || $t('pages.settings.ungrouped') }}
						</v-expansion-panel-title>
						<v-expansion-panel-text>
							<node-settings-card
								v-for="node in items"
								:key="node.identifier"
								:node="node"
							></node-settings-card>
						</v-expansion-panel-text>
					</v-expansion-panel>
				</v-expansion-panels>
			</v-card-text>
		</v-card>
	`,

	data: function() {
		return {
			loading: true,
			openPanels: [],
		}
	},

	computed: {
		nodes: function() {
			return this.$store.getters['dashboard/nodes']
		},
		controllers: function() {
			return Object.values(this.nodes)
				.filter(node => node.role === 'CTRL')
		},
		grouped: function() {
			const groups = {}
			this.controllers
				.slice()
				.sort((a, b) => (a.name || '').localeCompare(b.name || ''))
				.forEach(node => {
					const key = node.group || ''
					if (!groups[key]) {
						groups[key] = []
					}
					groups[key].push(node)
				})
			return groups
		},
	},

	methods: {
		async loadNodes() {
			this.loading = true
			if (!this.$store.getters['dashboard/allNodesLoaded']) {
				await this.$store.dispatch('dashboard/fetchNodes')
			}
			this.loading = false
		},
	},

	created() {
		this.loadNodes()
	},
}

registerGlobalComponent('AquapiSettings', AquapiSettings)
export {AquapiSettings}

// vim: set noet ts=4 sw=4:
