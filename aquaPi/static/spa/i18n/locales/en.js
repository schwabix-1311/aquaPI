export default
{
	app: {
		name: 'aquaPi',
		subtitle: 'Your fish will love it!',
		loading: {
			message: 'Loading<br>Data',
		}
	},

	pages: {
		register: {
			label: 'Register'
		},
		login: {
			label: 'Login'
		},
		logout: {
			label: 'Logout'
		},
		home: {
			label: 'Start'
		},
		dashboard: {
			label: 'Dashboard',
			title: 'Dashboard',
			heading: 'aquaPi Dashboard',
		},
		settings: {
			label: 'Settings',
			heading: 'Settings',
		},
		config: {
			label: 'Configuration',
			heading: 'Configuration',
		},
		about: {
			label: 'About',
			heading: 'About',
			copyright: 'Copyright',
		}
	},

	auth: {
		login: {
			form: {
				heading: 'Login',
				username: {
					label: 'Username',
					errors: {
						empty: 'Username is required'
					}
				},
				password: {
					label: 'Password',
					errors: {
						empty: 'Password is required'
					}
				},
				btnSubmit: {
					label: 'Login'
				},
				btnCancel: {
					label: 'Cancel'
				},
				hintMandatory: '* mandatory fields'
			}
		}
	},

	dashboard: {
		configurator: {
			headline: 'Dashboard Configuration',
			hint: 'Which tiles should be shown?',
			btnSave: {
				label: 'Save'
			}
		},
		configuration: {
			hintEmpty: 'No items are selected for the dashboard yet',
			btnSetup: 'Configure widgets'
		},
		widget: {
			inputs: {
				label: 'Inputs'
			},
			history: {
				period: {
					label: 'Period %s'
				}
			}
		}

	},

	misc: {
		nodeTypes: {
			aux: 'Connection',
			ctrl: 'Control',
			history: 'Diagram',
			in_endp: 'Input',
			out_endp: 'Output',
		},
		dataRange: {
			default: {
				label: 'Value'
			},
			analog: {
				label: 'Measurement'
			},
			binary: {
				label: 'Status',
				value: {
					on: 'On',
					off: 'Off'
				}
			},
			percent: {
				label: 'Status',
				value: {
					on: 'On',
					off: 'Off'
				}
			},
			cronspec: {
				label: 'Switching status',
				value: {
					on: 'On',
					off: 'Off'
				}
			}
		}
	}
}

// vim: set noet ts=4 sw=4:
