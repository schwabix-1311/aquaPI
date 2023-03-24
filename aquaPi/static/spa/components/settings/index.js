import './comps.js'

const AquapiSettings = {
	template: `
		<v-card elevation="0" tile>
			<aquapi-page-heading 
				:heading="$t('pages.settings.heading')" 
				:icon="'mdi-view-dashboard'"
			></aquapi-page-heading>

			<v-card-text>
				<v-row justify="center">
					<v-alert
						elevation="0"
						type="info"
						text
						:icon="'mdi-info'"
						YYcolor="'orange'"
					>
						Hier denn die (CTRL) nodes mit einstellbaren Werten
					</v-alert>     
				</v-row>
			</v-card-text>
		</v-card>
    `,

	data: function() {
		return {
		};
	},
}

Vue.component('AquapiSettings', AquapiSettings)
export {AquapiSettings}
