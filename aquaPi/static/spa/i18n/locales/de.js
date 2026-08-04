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
			hintSelecting: 'Nodes anklicken, um sie für ein Template auszuwählen (%{count} ausgewählt)',
			errNameType: 'Bitte Typ wählen und Namen eingeben',
			confirmDelete: 'Node "%{name}" löschen? Bestehende Verbindungen werden entfernt.',
			selectNodes: 'Nodes auswählen',
			templatesSnapshots: 'Templates & Snapshots',
			templates: 'Templates',
			snapshots: 'Snapshots',
			templateName: 'Template-Name',
			snapshotName: 'Snapshot-Name',
			saveSelection: 'Auswahl als Template speichern',
			saveSnapshot: 'Aktuelle Konfiguration speichern',
			selectedCount: '%{count} Node(s) ausgewählt',
			insert: 'Einfügen',
			restore: 'Wiederherstellen',
			close: 'Schließen',
			hintNoTemplates: 'Noch keine Templates gespeichert',
			hintNoSnapshots: 'Noch keine Snapshots gespeichert',
			confirmDeleteTemplate: 'Template "%{name}" löschen?',
			confirmDeleteSnapshot: 'Snapshot "%{name}" löschen?',
			confirmRestoreSnapshot: 'Snapshot "%{name}" wiederherstellen? Dies ersetzt die komplette aktuelle Konfiguration.',
			restoringSnapshot: 'Snapshot wird wiederhergestellt, bitte warten…',
			unsavedChanges: 'Ungespeicherte Änderungen',
			discard: 'Verwerfen',
			saveChanges: 'Speichern',
			confirmDiscard: 'Alle ungespeicherten Änderungen verwerfen?',
			confirmLeaveUnsaved: 'Es gibt ungespeicherte Änderungen. Diese verwerfen und die Seite verlassen?',
			deleteConnection: 'Verbindung löschen',
			changesDiscarded: 'Änderungen verworfen',
		},
		about: {
			label: 'Über aquaPi',
			heading: 'Über aquaPi',
			copyright: 'Copyright',
			donateMessage: 'Lob bitte an tkuhn, Bugs darfst du behalten.',
			hintPlaceholder: 'Diese Seite wird irgendwann Version, Copyright, Systemstatus etc. anzeigen.<br>... und einen Link zur REST-API-Dokumentation.',
		},
		users: {
			label: 'Benutzer',
			heading: 'Benutzerverwaltung',
			username: 'Benutzername',
			email: 'E-Mail',
			emailHint: 'Optional, wird nur für den Passwort-Reset-Link benötigt',
			password: 'Passwort',
			newPassword: 'Neues Passwort',
			passwordHintOptional: 'Leer lassen, um das Passwort nicht zu ändern',
			role: 'Rolle',
			addUser: 'Benutzer hinzufügen',
			editUser: 'Benutzer bearbeiten',
			errUsernamePassword: 'Benutzername und Passwort sind erforderlich',
			confirmDelete: 'Benutzer "%{name}" löschen?',
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
				hintMandatory: '* Pflichtfelder',
				errors: {
					invalid: 'Benutzername oder Passwort ist falsch'
				}
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
		legacySettingsLink: '(alte) Settings',
		dummyComponentText: 'Einfach nur \'ne Dummy-Komponente für Testzwecke',
		language: {
			label: 'Sprache',
			de: 'Deutsch',
			en: 'English',
		},
		dialog: {
			confirm: 'Bestätigen',
			cancel: 'Abbrechen',
			ok: 'OK',
		},
		toast: {
			saveSuccess: 'Erfolgreich gespeichert',
			saveError: 'Speichern fehlgeschlagen',
			deleteSuccess: 'Erfolgreich gelöscht',
			deleteError: 'Löschen fehlgeschlagen',
		},
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

