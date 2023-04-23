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
							Someday this page will show version, copyright, system state, etc.<br>
							... and a link to REST API documentation.
						</v-alert>
					</v-col>
				</v-row>
				<p><div class="text-h5">{{ $t('pages.about.copyright') }}</div></p>
				<p>This software is released under GNU GPL v.3</br>
					(c) 2023 Markus Kuhn, released under GNU GPL v.3</p>
				<p>Part of this software is based on Adam Wallner's excellent library for the TC420 LED Controller.<br>
					(c) 2020 Adam Wallner, released under GNU GPL v.3</p>
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

// vim: set noet ts=4 sw=4:
