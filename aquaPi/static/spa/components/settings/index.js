import './comps.js'
import {registerGlobalComponent} from '../app/registry.js'
import {useDashboardStore} from '../../store/modules/dashboard.js'
import {isRoot, cardTitle, descendants} from './chains.js'

const AquapiSettings = {
	template: `
		<v-card elevation="0" tile>
			<aquapi-page-heading
				:heading="$t('pages.settings.heading')"
				:icon="'mdi-tune'"
			></aquapi-page-heading>

			<v-card-text class="aquapi-settings">
				<v-row v-if="loading" justify="center">
					<v-col cols="12" class="text-center pa-10">
						<aquapi-loading-indicator></aquapi-loading-indicator>
					</v-col>
				</v-row>

				<v-row v-else-if="!roots.length" justify="center">
					<v-col cols="12" md="6">
						<v-alert elevation="0" type="info" text :icon="'mdi-info'">
							{{ $t('pages.settings.hintEmpty') }}
						</v-alert>
					</v-col>
				</v-row>

				<template v-else-if="hasNamedGroups">
					<v-expansion-panels multiple v-model="openPanels" tile>
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
				</template>

				<template v-else>
					<node-settings-card
						v-for="node in sortedRoots"
						:key="node.identifier"
						:node="node"
					></node-settings-card>
				</template>
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
		dashboardStore() {
			return useDashboardStore()
		},
		nodes: function() {
			return this.dashboardStore.nodes
		},
		// a root is either a node whose own receives is empty (the origin
		// of a potential chain), or a HISTORY/ALERTS node unconditionally -
		// those always get their own dedicated card, never nested inside
		// whatever they're recording/watching. See ./chains.js.
		roots: function() {
			return Object.values(this.nodes).filter(node => isRoot(node))
		},
		// chains, then standalone nodes, then HISTORY, then ALERTS,
		// alphabetical within each category
		sortedRoots: function() {
			return this.roots.slice().sort((a, b) => {
				const rank = this.rootRank(a) - this.rootRank(b)
				return rank !== 0 ? rank : (a.name || '').localeCompare(b.name || '')
			})
		},
		grouped: function() {
			const groups = {}
			this.sortedRoots.forEach(node => {
				// the displayed/anchor card's own group decides the panel,
				// not necessarily the root's group
				const key = cardTitle(node, this.nodes).group || ''
				if (!groups[key]) {
					groups[key] = []
				}
				groups[key].push(node)
			})
			return groups
		},
		// suppress the group/"Ohne Gruppe" UI entirely until the user has
		// actually named at least one group - pointless otherwise. Checks
		// every node, not just roots/anchors: a group set on a nested
		// Eingang/Ausgang member (which never becomes a panel key itself,
		// since panels key off the anchor's own group) still counts.
		hasNamedGroups: function() {
			return Object.values(this.nodes).some(node => node.group)
		},
	},

	methods: {
		// display order within a panel: chains, then standalone nodes,
		// then HISTORY, then ALERTS
		rootRank(node) {
			if (node.role === 'HISTORY') {
				return 2
			}
			if (node.role === 'ALERTS') {
				return 3
			}
			return descendants(node, this.nodes).length > 0 ? 0 : 1
		},
		async loadNodes() {
			this.loading = true
			if (!this.dashboardStore.allNodesLoaded) {
				await this.dashboardStore.fetchNodes()
			}
			this.loading = false
			// default all groups to expanded, once known, so the user sees
			// every controller immediately without an extra click
			this.openPanels = Object.keys(this.grouped).map((_, i) => i)
		},
	},

	created() {
		this.loadNodes()
	},
}

registerGlobalComponent('AquapiSettings', AquapiSettings)
export {AquapiSettings}

// vim: set noet ts=4 sw=4:
