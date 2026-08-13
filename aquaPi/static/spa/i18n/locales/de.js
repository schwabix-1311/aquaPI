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
			hintEmpty: 'Keine Nodes gefunden',
			ungrouped: 'Ohne Gruppe',
			scheduleHint: 'Minute Stunde Tag(Monat) Monat Wochentag',
			inputs: 'Eingänge',
			outputs: 'Ausgänge',
			alertConds: {
				heading: 'Alarm-Bedingungen',
				condition: 'Bedingung',
				watchedNode: 'Beobachteter Node',
				limit: 'Grenzwert',
				duration: 'Mindestdauer (Min)',
				add: 'Bedingung hinzufügen',
				remove: 'Bedingung entfernen',
				save: 'Bedingungen speichern',
				hintEmpty: 'Noch keine Bedingungen - dieser Alarm wird nie auslösen',
				confirmClearAll: 'Letzte Bedingung entfernen? Dieser Alarm löst dann nicht mehr aus, bis wieder eine Bedingung hinzugefügt wird.',
			},
			fields: {
				unit: 'Einheit',
				offset: 'Offset',
				scaleFactor: 'Skalierfaktor',
				unfairAvg: 'Ungewichteter Mittelwert [0=aus]',
				inputPort: 'Eingangsport',
				outputPort: 'Ausgangsport',
				alertPort: 'Sende an',
				readInterval: 'Leseintervall',
				inverted: 'Invertiert',
				avg: 'Mittelwert [1=direkt]',
				cronspec: 'CRON (m h DoM M DoW)',
				repeat: 'Wiederholung',
				receives: 'Empfängt von',
				setpoint: 'Sollwert [{unit}]',
				hysteresis: 'Hysterese [{unit}]',
				pFact: 'P-Faktor',
				iFact: 'I-Faktor',
				dFact: 'D-Faktor',
				fadeIn: 'Einblenddauer',
				fadeOut: 'Ausblenddauer',
				ascendDescend: 'Auf-/Abblendzeit',
				cycle: 'PWM-Zykluszeit',
				minimum: 'Minimum [%]',
				maximum: 'Maximum [%]',
				percept: 'Wahrnehmungskorrektur',
				capacity: 'Verlaufskapazität (In-Memory)',
			},
		},
		config: {
			label: 'Konfiguration',
			heading: 'Konfiguration',
			addNode: 'Node hinzufügen',
			autoArrange: 'Automatisch anordnen',
			editNode: 'Node bearbeiten',
			nodeType: 'Node-Typ',
			nodeName: 'Name',
			receives: '@:pages.settings.fields.receives',
			group: 'Gruppe',
			connect: 'Verbinden',
			edit: 'Bearbeiten',
			delete: 'Löschen',
			save: 'Speichern',
			cancel: 'Abbrechen',
			hintEmpty: 'Noch keine Nodes - über "Node hinzufügen" anlegen',
			hintConnecting: 'Ziel-Node anklicken zum Verbinden, oder Palette zum Abbrechen',
			hintSelecting: 'Nodes anklicken, um sie für ein Template auszuwählen ({count} ausgewählt)',
			errNameType: 'Bitte Typ wählen und Namen eingeben',
			confirmDelete: 'Node "{name}" löschen? Bestehende Verbindungen werden entfernt.',
			selectNodes: 'Nodes auswählen',
			templatesSnapshots: 'Templates & Snapshots',
			templates: 'Templates',
			snapshots: 'Snapshots',
			templateName: 'Template-Name',
			snapshotName: 'Snapshot-Name',
			saveSelection: 'Auswahl als Template speichern',
			saveSnapshot: 'Aktuelle Konfiguration speichern',
			selectedCount: '{count} Node(s) ausgewählt',
			insert: 'Einfügen',
			restore: 'Wiederherstellen',
			close: 'Schließen',
			hintNoTemplates: 'Noch keine Templates gespeichert',
			hintNoSnapshots: 'Noch keine Snapshots gespeichert',
			confirmDeleteTemplate: 'Template "{name}" löschen?',
			confirmDeleteSnapshot: 'Snapshot "{name}" löschen?',
			confirmRestoreSnapshot: 'Snapshot "{name}" wiederherstellen? Dies ersetzt die komplette aktuelle Konfiguration.',
			restoringSnapshot: 'Snapshot wird wiederhergestellt, bitte warten…',
			discard: 'Verwerfen',
			saveChanges: 'Speichern',
			confirmDiscard: 'Alle ungespeicherten Änderungen verwerfen?',
			confirmLeaveUnsaved: 'Es gibt ungespeicherte Änderungen an dieser Konfiguration.',
			deleteConnection: 'Verbindung löschen',
			changesDiscarded: 'Änderungen verworfen',
			portIn: 'Eingang',
			portOut: 'Ausgang',
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
			anonymousFieldDisabledHint: 'Für dieses reservierte Konto nicht verfügbar',
			password: 'Passwort',
			newPassword: 'Neues Passwort',
			passwordHintOptional: 'Leer lassen, um das Passwort nicht zu ändern',
			suggestPassword: 'Neues Passwort vorschlagen',
			revealPassword: 'Passwort anzeigen/verbergen',
			role: 'Rolle',
			addUser: 'Benutzer hinzufügen',
			editUser: 'Benutzer bearbeiten',
			errUsernamePassword: 'Benutzername und Passwort sind erforderlich',
			confirmDelete: 'Benutzer "{name}" löschen?',
			confirmAnonymousRoleChange: 'Diese Rolle gilt dann für jeden nicht angemeldeten Besucher der App. Wirklich ändern?',
			passwordSentEmail: 'Gespeichert. Das Passwort wurde per Email an {email} verschickt.',
			passwordSentLog: 'Gespeichert. Das Passwort konnte nicht per Email verschickt werden, siehe Server-Log.',
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
		},
		resetPassword: {
			request: {
				heading: 'Passwort zurücksetzen',
				linkLabel: 'Passwort vergessen?',
				hint: 'Benutzername eingeben - falls eine E-Mail-Adresse hinterlegt ist, senden wir einen Link zum Zurücksetzen.',
				username: {
					label: 'Benutzername'
				},
				btnSubmit: {
					label: 'Link senden'
				},
				btnBack: {
					label: 'Zurück zum Login'
				},
				sentHint: 'Falls dieses Konto existiert und eine E-Mail-Adresse hinterlegt ist, wurde ein Link gesendet. Bitte E-Mails prüfen.'
			},
			confirm: {
				heading: 'Neues Passwort setzen',
				password: {
					label: 'Neues Passwort'
				},
				password2: {
					label: 'Passwort wiederholen'
				},
				btnSubmit: {
					label: 'Passwort setzen'
				},
				invalidHint: 'Dieser Link ist ungültig oder abgelaufen.',
				btnRequestNew: {
					label: 'Neuen Link anfordern'
				},
				errors: {
					mismatch: 'Passwörter stimmen nicht überein'
				},
				successToast: 'Passwort wurde zurückgesetzt - bitte neu einloggen'
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
				},
				forceDailySampling: {
					label: 'Tagesmittelwerte'
				}
			},
			scaleAux: {
				formula: 'Messwert * {factor} + {offset}',
			},
			avgAux: {
				unweighted: 'Ungewichtet',
				movingAvg: 'Gleitender Mittelwert ({n})',
			},
			sunCtrl: {
				// odd cloudiness -> shorter, darker clouds (Cloud class,
				// ctrl_nodes.py's `cloudiness & 1` check); even -> longer,
				// milder ones. Wording alternates mood (moody/dark for odd,
				// cosy/calm for even) on top of the increasing amount, to
				// hint at that without showing the raw number.
				cloudiness: {
					c0: 'wolkenlos',
					c1: 'mürrische Wolken huschen vorbei',
					c2: 'gemütliche Wölkchen',
					c3: 'launische Wolkenfetzen',
					c4: 'gemächlich ziehende Wolken',
					c5: 'düsteres Wolkentreiben',
					c6: 'schwermütig – "Obscured by Clouds"',
					c7: 'stürmisch, bleib besser zuhause',
				},
			},
		}
	},

	misc: {
		dummyComponentText: 'Einfach nur \'ne Dummy-Komponente für Testzwecke',
		genericLabel: 'Bezeichnung',
		genericValue: 'Wert',
		noActiveAlerts: 'Keine aktiven Warnungen',
		footer: {
			servedBy: 'Server: {os}',
			platform: ' auf {model}',
			pct: '{pct}%',
			cpuLabel: 'CPU',
			ramLabel: 'RAM',
			swapLabel: 'Swap',
			diskLabel: 'Speicher',
		},
		language: {
			label: 'Sprache',
			de: 'Deutsch',
			en: 'English',
		},
		dialog: {
			confirm: 'Bestätigen',
			cancel: 'Abbrechen',
			ok: 'OK',
			valueRequired: 'Ein Wert ist erforderlich',
		},
		toast: {
			saveSuccess: 'Erfolgreich gespeichert',
			saveError: 'Speichern fehlgeschlagen',
			deleteSuccess: 'Erfolgreich gelöscht',
			deleteError: 'Löschen fehlgeschlagen',
			loadError: 'Laden fehlgeschlagen: {what}',
			what: {
				nodes: 'Nodes',
				nodeTypes: 'Node-Typen',
				templates: '@:pages.config.templates',
				snapshots: '@:pages.config.snapshots',
				users: '@:pages.users.label',
				nodeSettings: 'Node-Einstellungen',
				history: 'Verlaufsdaten',
			},
		},
		duration: {
			sec: 's',
			secs: 's',
			min: 'min',
			mins: 'min',
			hour: 'h',
			hours: 'h',
			day: 'Tag',
			days: 'Tage',
			month: 'Monat',
			months: 'Monate',
			halfYear: '1/2 Jahr',
			year: 'Jahr',
			years: 'Jahre',
		},
		nodeTypes: {
			aux: 'Verknüpfung',
			ctrl: 'Steuerung',
			history: 'Diagramm',
			in_endp: 'Eingang',
			out_endp: 'Ausgang',
			alerts: 'Störung',
		},
		alertConds: {
			AlertAbove: 'Über',
			AlertBelow: 'Unter',
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

