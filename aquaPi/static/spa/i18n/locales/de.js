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
			hintEmpty: 'Keine einstellbaren Regler gefunden',
			ungrouped: 'Ohne Gruppe',
			scheduleHint: 'Minute Stunde Tag(Monat) Monat Wochentag',
		},
		config: {
			label: 'Konfiguration',
			heading: 'Konfiguration',
			addNode: 'Node hinzufügen',
			editNode: 'Node bearbeiten',
			nodeType: 'Node-Typ',
			nodeName: 'Name',
			receives: 'Empfängt von',
			group: 'Gruppe',
			connect: 'Verbinden',
			edit: 'Bearbeiten',
			delete: 'Löschen',
			save: 'Speichern',
			cancel: 'Abbrechen',
			hintEmpty: 'Noch keine Nodes - über "Node hinzufügen" anlegen',
			hintConnecting: 'Ziel-Node anklicken zum Verbinden, oder Palette zum Abbrechen',
			errNameType: 'Bitte Typ wählen und Namen eingeben',
			confirmDelete: 'Node "%{name}" löschen? Bestehende Verbindungen werden entfernt.',
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
		},
		configuration: {
			hintEmpty: 'Es sind noch keine Elemente für das Dashboard ausgewählt',
			btnSetup: 'Elemente konfigurieren'
		},
		widget: {
			inputs: {
				label: 'Eingänge'
			},
			setpoint: {
				minimum: 'Sollwert >= ',
				maximum: 'Sollwert <= ',
				equals: 'Sollwert = ',
			},
			history: {
				period: {
					label: 'Zeitraum %s'
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
			day: 'Tag',
			days: 'Tage',
		},
		nodeTypes: {
			aux: 'Verknüpfung',
			ctrl: 'Steuerung',
			history: 'Diagramm',
			in_endp: 'Eingang',
			out_endp: 'Ausgang',
			alerts: 'Störung',
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
			},
			aux: {
				label: 'Berechnet',
			},
		}
	}
}

// vim: set noet ts=4 sw=4:

