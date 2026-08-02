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
			hintEmpty: 'No configurable controllers found',
			ungrouped: 'Ungrouped',
			scheduleHint: 'Minute Hour DayOfMonth Month DayOfWeek',
		},
		config: {
			label: 'Configuration',
			heading: 'Configuration',
			addNode: 'Add node',
			editNode: 'Edit node',
			nodeType: 'Node type',
			nodeName: 'Name',
			receives: 'Receives from',
			group: 'Group',
			connect: 'Connect',
			edit: 'Edit',
			delete: 'Delete',
			save: 'Save',
			cancel: 'Cancel',
			hintEmpty: 'No nodes yet - use "Add node" to create one',
			hintConnecting: 'Click the target node to connect, or the palette to cancel',
			errNameType: 'Please choose a type and enter a name',
			confirmDelete: 'Delete node "%{name}"? Any wiring to it will be removed.',
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
			setpoint: {
				minimum: 'Setpoint >= ',
				maximum: 'Setpoint <= ',
				equals: 'Setoint = ',
			},
			history: {
				period: {
					label: 'Period %s'
				}
			}
		}
	},

	misc: {
		duration: {
			min: 'min',
			mins: 'min',
			hour: 'h',
			hours: 'h',
			day: 'day',
			days: 'days',
		},
		nodeTypes: {
			aux: 'Connection',
			ctrl: 'Control',
			history: 'Diagram',
			in_endp: 'Input',
			out_endp: 'Output',
			alerts: 'Alert',
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
			},
			aux: {
				label: 'Calculated',
			}
		}
	}
}

// vim: set noet ts=4 sw=4:
