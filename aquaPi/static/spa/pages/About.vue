<template>
	<v-card elevation="0" tile>
		<aquapi-page-heading
			:heading="$t('pages.about.heading')"
			icon="mdi-information-outline"
		></aquapi-page-heading>

		<v-card-text>
			<v-row justify="start">
				<v-col :cols="12">
					<v-alert
						closable
						border="left"
						elevation="3"
						type="info"
					>
						{{ $t('pages.about.apiDocsHint') }}
						<a href="/api/" target="_blank">/api/</a>
					</v-alert>
				</v-col>
			</v-row>
			<p>{{ $t('pages.about.version') }}: {{ appVersion }}</p>
			<p><div class="text-h5">{{ $t('pages.about.copyright') }}</div></p>
			<p>This software is released under GNU GPL v.3</br>
				(c) 2023 Markus Kuhn, released under GNU GPL v.3</p>
			<p>Part of this software is based on Adam Wallner's excellent library for the TC420 LED Controller.<br>
				(c) 2020 Adam Wallner, released under GNU GPL v.3</p>
		</v-card-text>
	</v-card>
</template>

<script>
export default {
	data() {
		return {
			appVersion: window.__APP_VERSION__ || 'dev',
		}
	},
}
</script>
