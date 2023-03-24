const About = {
	template: `
		<v-card elevation="0" tile>
			<aquapi-page-heading 
				:heading="$t('pages.about.heading')" 
				icon="mdi-information-outline"
				:buttons="[{icon: 'mdi-gift', action: donate}]"
			></aquapi-page-heading>	   

			<v-card-text>
				<v-row justify="start">
					<v-col :cols="12">
						<v-alert
							dismissible
							border="left"
							elevation="3"
							type="info"
							YYtext
							:icon="'mdi-clock'"
							YYcolor="'orange'"
						>
							Someday this page will show version, copyright, system state.<br>
							... and a link to REST API documentation.
						</v-alert>     
					</v-col>
				</v-row>
			</v-card-text>
		</v-card>
    `,

	methods: {
		donate() {
			window.alert('Lob bitte an tkuhn, Bugs darfst du behalten.')
		}
	}

};

export { About };
