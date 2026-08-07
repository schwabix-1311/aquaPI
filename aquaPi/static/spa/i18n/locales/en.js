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
			hintEmpty: 'No nodes found',
			ungrouped: 'Ungrouped',
			scheduleHint: 'Minute Hour DayOfMonth Month DayOfWeek',
			inputs: 'Inputs',
			outputs: 'Outputs',
			fields: {
				unit: 'Unit',
				offset: 'Offset',
				scaleFactor: 'Scale factor',
				unfairAvg: 'Unweighted average [0=off]',
				inputPort: 'Input port',
				outputPort: 'Output port',
				readInterval: 'Read interval',
				inverted: 'Inverted',
				avg: 'Averaging [1=direct]',
				cronspec: 'CRON (m h DoM M DoW)',
				repeat: 'Repeat',
				receives: 'Receives from',
				setpoint: 'Setpoint [%{unit}]',
				hysteresis: 'Hysteresis [%{unit}]',
				pFact: 'P factor',
				iFact: 'I factor',
				dFact: 'D factor',
				fadeIn: 'Fade-in time',
				fadeOut: 'Fade-out time',
				ascendDescend: 'Ascend/descend time',
				cycle: 'PWM cycle time',
				minimum: 'Minimum [%]',
				maximum: 'Maximum [%]',
				percept: 'Perceptive',
				duration: 'Max. duration',
			},
		},
		config: {
			label: 'Configuration',
			heading: 'Configuration',
			addNode: 'Add node',
			editNode: 'Edit node',
			nodeType: 'Node type',
			nodeName: 'Name',
			receives: '@:pages.settings.fields.receives',
			group: 'Group',
			connect: 'Connect',
			edit: 'Edit',
			delete: 'Delete',
			save: 'Save',
			cancel: 'Cancel',
			hintEmpty: 'No nodes yet - use "Add node" to create one',
			hintConnecting: 'Click the target node to connect, or the palette to cancel',
			hintSelecting: 'Click nodes to select them for a template (%{count} selected)',
			errNameType: 'Please choose a type and enter a name',
			confirmDelete: 'Delete node "%{name}"? Any wiring to it will be removed.',
			selectNodes: 'Select nodes',
			templatesSnapshots: 'Templates & Snapshots',
			templates: 'Templates',
			snapshots: 'Snapshots',
			templateName: 'Template name',
			snapshotName: 'Snapshot name',
			saveSelection: 'Save selection as template',
			saveSnapshot: 'Save current configuration',
			selectedCount: '%{count} node(s) selected',
			insert: 'Insert',
			restore: 'Restore',
			close: 'Close',
			hintNoTemplates: 'No templates saved yet',
			hintNoSnapshots: 'No snapshots saved yet',
			confirmDeleteTemplate: 'Delete template "%{name}"?',
			confirmDeleteSnapshot: 'Delete snapshot "%{name}"?',
			confirmRestoreSnapshot: 'Restore snapshot "%{name}"? This replaces the entire current configuration.',
			restoringSnapshot: 'Restoring snapshot, please wait…',
			unsavedChanges: 'Unsaved changes',
			discard: 'Discard',
			saveChanges: 'Save',
			confirmDiscard: 'Discard all unsaved changes?',
			confirmLeaveUnsaved: 'There are unsaved changes. Discard them and leave the page?',
			deleteConnection: 'Delete connection',
			changesDiscarded: 'Changes discarded',
			portIn: 'Input',
			portOut: 'Output',
		},
		about: {
			label: 'About',
			heading: 'About',
			copyright: 'Copyright',
			donateMessage: 'Please send praise to tkuhn, you may keep the bugs.',
			hintPlaceholder: 'Someday this page will show version, copyright, system state, etc.<br>... and a link to REST API documentation.',
		},
		users: {
			label: 'Users',
			heading: 'User Management',
			username: 'Username',
			email: 'Email',
			emailHint: 'Optional, only used to deliver the password reset link',
			password: 'Password',
			newPassword: 'New password',
			passwordHintOptional: 'Leave empty to keep the current password',
			role: 'Role',
			addUser: 'Add user',
			editUser: 'Edit user',
			errUsernamePassword: 'Username and password are required',
			confirmDelete: 'Delete user "%{name}"?',
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
				hintMandatory: '* mandatory fields',
				errors: {
					invalid: 'Invalid username or password'
				}
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
			},
			scaleAux: {
				formula: 'reading * %{factor} + %{offset}',
			},
			avgAux: {
				unweighted: 'Unweighted',
				movingAvg: 'Moving average (%{n})',
			},
			sunCtrl: {
				// odd cloudiness -> shorter, darker clouds (Cloud class,
				// ctrl_nodes.py's `cloudiness & 1` check); even -> longer,
				// milder ones. Wording alternates mood (moody/dark for odd,
				// cosy/calm for even) on top of the increasing amount, to
				// hint at that without showing the raw number.
				cloudiness: {
					c0: 'not a cloud in sight',
					c1: 'grumpy clouds scurry by',
					c2: 'cosy little clouds',
					c3: 'moody wisps of cloud',
					c4: 'clouds drifting leisurely',
					c5: 'gloomy cloud bustle',
					c6: 'melancholy sky, "Obscured by Clouds"',
					c7: 'stormy, better stay indoors',
				},
			},
		}
	},

	misc: {
		dummyComponentText: 'Just a dummy component for testing purposes',
		genericLabel: 'Label',
		genericValue: 'Value',
		language: {
			label: 'Language',
			de: 'Deutsch',
			en: 'English',
		},
		dialog: {
			confirm: 'Confirm',
			cancel: 'Cancel',
			ok: 'OK',
			valueRequired: 'A value is required',
		},
		toast: {
			saveSuccess: 'Saved successfully',
			saveError: 'Save failed',
			deleteSuccess: 'Deleted successfully',
			deleteError: 'Delete failed',
		},
		duration: {
			sec: 's',
			secs: 's',
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
