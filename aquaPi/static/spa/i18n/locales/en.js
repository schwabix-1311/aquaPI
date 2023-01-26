export default
{
	app: {
		name: 'aquaPi',
		subtitle: 'the one and only aquarium control center',
		loading: {
			message: 'Loading<br>Data',
		}
	},

	pages: {
		login: {
			label: 'Login'
		},
		home: {
			label: 'Start'
		},
		dashboard: {
			label: 'Dashboard',
			title: 'Dashboard',
			heading: 'AquaPi Dashboard'
		},
		settings: {
			label: 'Settings'
		},
		about: {
			label: 'About'
		}
	},

	auth: {
		login: {
			form: {
				heading: 'Login',
				username: 'Username',
				password: 'Password',
				btnSubmit: 'Login',
				btnCancel: 'Cancel',
				hintMandatory: '* mandatory fields'
			}
		}
	},

	dashboard: {
		configurator: {
			headline: 'Dashboard Configuration',
			hint: 'Which tiles should be shown?',
			btnSave: 'Save'

		}
	},

	misc: {
		nodeTypes: {
			aux: 'Auxiliary / Connection',
			ctrl: 'Control',
			history: 'Diagram',
			in_endp: 'Input',
			out_endp: 'Output',
		}
	}
}
