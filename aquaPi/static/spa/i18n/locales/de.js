export default
{
	app: {
		name: 'aquaPi',
		subtitle: 'Deine Fische lieben es!',
		loading: {
			message: 'Lade<br>Daten',
		}
	},

	pages: {
		register: {
			label: 'Registrierung'
		},
		login: {
			label: 'Anmelden'
		},
		logout: {
			label: 'Abmelden'
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
			label: 'Einstellungen',
			heading: 'Einstellungen',
		},
		config: {
			label: 'Konfiguration',
			heading: 'Konfiguration',
		},
		about: {
			label: 'Über aquaPi',
			heading: 'Über aquaPi',
                        copyright: 'Copyright',
		}
	},

	auth: {
		login: {
			form: {
				heading: 'Login',
				username: {
					label: 'Benutzername',
					errors: {
						empty: 'Benutzername ist erforderlich'
					}
				},
				password: {
					label: 'Passwort',
					errors: {
						empty: 'Passwort ist erforderlich'
					}
				},
				btnSubmit: {
					label: 'Login'
				},
				btnCancel: {
					label: 'Abbrechen'
				},
				hintMandatory: '* Pflichtfelder'
			}
		}
	},

	dashboard: {
		configurator: {
			headline: 'Dashboard Konfiguration',
			hint: 'Welche Elemente sollen angezeigt werden?',
			btnSave: {
				label: 'Speichern'
			}
		}
	},

	misc: {
		nodeTypes: {
			aux: 'Verknüpfung',
			ctrl: 'Steuerung',
			history: 'Diagramm',
			in_endp: 'Eingang',
			out_endp: 'Ausgang',
		},
		dataRange: {
			default: {
				label: 'Wert'
			},
			analog: {
				label: 'Messwert'
			},
			binary: {
				label: 'Status',
				value: {
					on: 'An',
					off: 'Aus'
				}
			},
			percent: {
				label: 'Status',
				value: {
					on: 'An',
					off: 'Aus'
				}
			},
			cronspec: {
				label: 'Schaltzustand',
				value: {
					on: 'An',
					off: 'Aus'
				}
			}
		}
	}
}

// vim: set noet ts=4 sw=4:

