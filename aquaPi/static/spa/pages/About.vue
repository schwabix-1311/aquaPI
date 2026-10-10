<template>
	<v-card elevation="0" tile>
		<aquapi-page-heading
			:heading="$t('pages.about.heading')"
			icon="mdi-information-outline"
		></aquapi-page-heading>

		<v-card-text class="text-body-1" style="max-width: 60rem">
			<p class="mb-6">{{ $t('pages.about.intro') }}</p>

			<v-row v-for="row in infoRows" :key="row.label" dense>
				<v-col cols="auto" class="font-weight-medium" style="min-width: 7rem">{{ row.label }}</v-col>
				<v-col>
					<template v-for="(link, i) in row.links" :key="link.href">
						<span v-if="i"> · </span>
						<a :href="link.href" target="_blank" rel="noopener">{{ link.text }}</a>
					</template>
					<span v-if="row.text">{{ row.text }}</span>
				</v-col>
			</v-row>

			<div class="text-h6 mt-8 mb-2">{{ $t('pages.about.license') }}</div>
			<p>
				© 2022–2026 Markus Kuhn, Thomas Kuhn –
				<a href="https://www.gnu.org/licenses/gpl-3.0.html" target="_blank" rel="noopener">GNU GPL v3</a>
			</p>
			<p class="mt-2 text-accent font-weight-medium">{{ $t('pages.about.disclaimer') }}</p>

			<div class="text-h6 mt-8 mb-2">{{ $t('pages.about.thirdParty') }}</div>
			<p>{{ $t('pages.about.tc420') }} © 2020 Adam Wallner – GNU GPL v3</p>
			<p class="mt-2">Vue, Vuetify, Pinia, vue-router, vue-i18n, Chart.js, Luxon, SortableJS, vue3-sfc-loader – MIT</p>
		</v-card-text>
	</v-card>
</template>

<script>
const REPO = 'https://github.com/schwabix-1311/aquaPI'

export default {
	data() {
		return {
			appVersion: window.__APP_VERSION__ || 'dev',
		}
	},
	computed: {
		infoRows() {
			return [
				{label: this.$t('pages.about.version'), text: this.appVersion},
				{label: this.$t('pages.about.project'), links: [
					{href: REPO, text: 'github.com/schwabix-1311/aquaPI'},
					{href: REPO + '/issues', text: this.$t('pages.about.reportIssue')},
				]},
				{label: this.$t('pages.about.api'), links: [{href: '/api/', text: '/api/'}]},
			]
		},
	},
}
</script>
