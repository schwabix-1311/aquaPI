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
			heading: 'Dashboard',
			ungrouped: '@:pages.settings.ungrouped',
		},
		settings: {
			label: 'Parameters',
			heading: 'Parameters',
			hintEmpty: 'No nodes found',
			ungrouped: 'Ungrouped',
			inputs: 'Inputs',
			outputs: 'Outputs',
			noControllerInBranch: 'No controller in this branch',
			escalation: {
				title: 'Escalation',
				channel: 'Escalate to',
				afterMinutes: 'After (min)',
				save: 'Save escalation',
				none: 'None',
			},
			fields: {
				unit: 'Unit',
				calibrationPoints: 'Calibration',
				unfairAvg: 'Unweighted average [0=off]',
				inputPort: 'Input port',
				outputPort: 'Output port',
				alertPort: 'Send to',
				initval: 'Initial value',
				value: 'Value',
				readInterval: 'Read interval',
				inverted: 'Inverted',
				avg: 'Averaging [1=direct]',
				frequency: 'Repeat every',
				duration: 'On for',
				anchor: 'Start time',
				weekdays: 'Weekdays',
				repeat: 'Repeat',
				conditions: 'Alert conditions',
				alertCondClass: 'Condition',
				alertCondWatchedNode: 'Watched element',
				alertCondLimit: 'Threshold',
				alertCondDuration: 'Min. duration (min)',
				receives: 'Receives from',
				setpoint: 'Setpoint [{unit}]',
				hysteresis: 'Hysteresis [{unit}]',
				pFact: 'P factor (%/{unit})',
				iFact: 'I factor',
				dFact: 'D factor',
				fadeIn: 'Fade-in duration',
				fadeOut: 'Fade-out duration',
				ascendDescend: 'Ascend/descend duration',
				cycle: 'PWM cycle time',
				minimum: 'Minimum [%]',
				maximum: 'Maximum [%]',
				percept: 'Perceptive',
				capacity: 'In-memory history capacity',
			},
		},
		wiring: {
			label: 'Wiring',
			heading: 'Wiring',
			addNode: 'Add node',
			autoArrange: 'Auto-arrange',
			editNode: 'Edit node "{name}"',
			nodeType: 'Node type',
			nodeName: 'Name',
			receives: '@:pages.settings.fields.receives',
			group: 'Group',
			hintEmpty: 'No nodes yet - quickest via "Templates", or add them one by one via "Add node"',
			hintSelecting: 'Click nodes to select them for a template ({count} selected)',
			errNameType: 'Please choose a type and enter a name',
			confirmDelete: 'Delete node "{name}"? Any wiring to it will be removed.',
			templatesSnapshots: 'Templates & Snapshots',
			templates: 'Templates',
			snapshots: 'Snapshots',
			templatesListHeading: 'Control-group templates',
			templateName: 'Template name',
			templatePredefined: 'predefined',
			snapshotName: 'Snapshot name',
			saveSelection: 'Save selection as template',
			saveSnapshot: 'Save current configuration',
			selectedCount: '{count} node(s) selected',
			insert: 'Insert',
			restore: 'Restore',
			close: 'Close',
			hintNoTemplates: 'No templates saved yet',
			hintNoSnapshots: 'No snapshots saved yet',
			confirmDeleteTemplate: 'Delete template "{name}"?',
			confirmDeleteSnapshot: 'Delete snapshot "{name}"?',
			confirmRestoreSnapshot: 'Restore snapshot "{name}"? This replaces the entire current configuration.',
			restoringSnapshot: 'Restoring snapshot, please wait…',
			discard: 'Discard',
			saveChanges: 'Apply',
			confirmDiscard: 'Discard all unsaved changes?',
			confirmLeaveUnsaved: 'There are unsaved changes to this configuration.',
			draftDirtyBlocksTemplates: 'Save or discard your changes first.',
			deleteConnection: 'Delete connection',
			changesDiscarded: 'Changes discarded',
			portIn: 'Input (drag to connect)',
			portOut: 'Output (drag to connect)',
			errors: {
				diffShape: 'Invalid diff format',
				unknownDeleteId: 'Unknown element id to delete: {id}',
				updateNotObject: 'Each update entry must be an object',
				unknownUpdateId: 'Unknown or deleted element id: {id}',
				duplicateUpdateId: 'Duplicate update for element id: {id}',
				createNotObject: 'Each create entry must be an object',
				unknownNodeType: 'Unknown or non-creatable element type: {type}',
				nameRequired: 'Name must not be empty',
				duplicateName: 'An element named "{name}" already exists',
				duplicateTempId: 'Duplicate temporary id: {tempId}',
				receivesNotList: '"Receives from" must be a list of element ids',
				fieldsNotObject: 'Fields must be an object',
				unknownReceivesId: 'Unknown element id for "Receives from": {id}',
				receivesNotSupported: '{type} does not support changing receives',
				fieldsNotSupported: '{type} does not support editing fields',
				notANumber: '{key} must be a number',
				incompatibleDataRange: '"{id}" produces {dataRange} data, which cannot be wired as an input',
				cycleDetected: 'This wiring would create a cycle',
				receivesNotAccepted: 'This element type does not accept any receives',
				receivesTooMany: 'This element type accepts at most 1 receives entry',
				missingValue: '"{node}" has no value for {fieldLabel}',
				notConnected: '"{node}" is not connected to anything',
			},
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
			anonymousFieldDisabledHint: 'Not available for this reserved account',
			password: 'Password',
			newPassword: 'New password',
			passwordHintOptional: 'Leave empty to keep the current password',
			suggestPassword: 'Suggest a new password',
			revealPassword: 'Show/hide password',
			role: 'Role',
			addUser: 'Add user',
			editUser: 'Edit user',
			errUsernamePassword: 'Username and password are required',
			confirmDelete: 'Delete user "{name}"?',
			confirmAnonymousRoleChange: 'This role will then apply to every visitor who is not logged in. Really change it?',
			passwordSentEmail: 'Saved. The password was emailed to {email}.',
			passwordSentLog: 'Saved. The password could not be emailed, check the server log.',
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
		},
		resetPassword: {
			request: {
				heading: 'Reset password',
				linkLabel: 'Forgot your password?',
				hint: 'Enter your username - if an email address is on file, we will send you a reset link.',
				username: {
					label: 'Username'
				},
				btnSubmit: {
					label: 'Send link'
				},
				btnBack: {
					label: 'Back to login'
				},
				sentHint: 'If this account exists and has an email address on file, a link has been sent. Please check your email.'
			},
			confirm: {
				heading: 'Set new password',
				password: {
					label: 'New password'
				},
				password2: {
					label: 'Repeat password'
				},
				btnSubmit: {
					label: 'Set password'
				},
				invalidHint: 'This link is invalid or has expired.',
				btnRequestNew: {
					label: 'Request a new link'
				},
				errors: {
					mismatch: 'Passwords do not match'
				},
				successToast: 'Password has been reset - please log in'
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
			elementNotFound: 'Error: Node not found',
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
					label: 'Time range %s'
				},
				forceDailySampling: {
					label: 'Daily averages'
				}
			},
			scaleAux: {
				formula: 'reading * {factor} + {offset}',
			},
			avgAux: {
				unweighted: 'Unweighted',
				movingAvg: 'Moving average ({n})',
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
			schedule: {
				always: 'Always on',
				daily: 'Daily {start}–{end}',
				repeat: 'Every {freq} for {dur}, from {anchor}',
			},
		}
	},

	misc: {
		dummyComponentText: 'Just a dummy component for testing purposes',
		genericLabel: 'Label',
		genericValue: 'Value',
		noActiveAlerts: 'No active alerts',
		actions: {
			edit: 'Edit',
			delete: 'Delete',
			save: 'Save',
			cancel: 'Cancel',
		},
		recordList: {
			add: 'Add',
			remove: 'Remove',
			empty: 'No entries yet',
		},
		calibration: {
			heading: 'Calibration',
			measured: 'Measured ({unit})',
			reference: 'Reference ({unit})',
			readSensorStart: 'Continuously follow the live value. Tip: temporarily shorten the source\'s read interval during calibration for faster updates.',
			readSensorStop: 'Stop following',
			apply: 'Apply calibration',
			preview: 'Result: offset {offset}, factor {factor}',
			identicalMeasured: 'Both measured values are identical - no valid calibration possible',
			jblHint: 'JBL reference values: a new probe reads about 0 mV at pH 7 and about 186 mV at pH 4 (probe/amplifier input voltage, not necessarily the same as the value measured here). A probe is considered worn out at a zero-point offset beyond ±40 mV, or a voltage difference of less than 90 mV between pH 7 and pH 4.',
			measuredDiff: 'Measured difference between the points: {diff}',
			historyHeading: 'Calibration history',
			historyEmpty: 'No calibration recorded yet',
		},
		footer: {
			servedBy: 'Served by {os}',
			platform: ' on {model}',
			pct: '{pct}%',
			cpuLabel: 'CPU',
			ramLabel: 'RAM',
			swapLabel: 'Swap',
			diskLabel: 'Storage',
		},
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
			loadError: 'Failed to load: {what}',
			what: {
				nodes: 'Nodes',
				nodeTypes: 'Node types',
				templates: '@:pages.wiring.templates',
				snapshots: '@:pages.wiring.snapshots',
				users: '@:pages.users.label',
				nodeSettings: 'Node settings',
				history: 'History data',
			},
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
			month: 'month',
			months: 'months',
			halfYear: '1/2 year',
			year: 'year',
			years: 'years',
		},
		nodeTypes: {
			aux: 'Connection',
			ctrl: 'Control',
			history: 'Diagram',
			in_endp: 'Input',
			out_endp: 'Output',
			alerts: 'Alert',
		},
		alertConds: {
			AlertAbove: 'Above',
			AlertBelow: 'Below',
		},
		weekday: {
			0: 'Mon', 1: 'Tue', 2: 'Wed', 3: 'Thu', 4: 'Fri', 5: 'Sat', 6: 'Sun',
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
			string: {
				label: 'Text'
			},
			aux: {
				label: 'Calculated',
			}
		}
	}
}

// vim: set noet ts=4 sw=4:
