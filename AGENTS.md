  # AGENTS.md

Diese Datei gibt KI-Coding-Agenten (Junie, Claude Code, Codex, Cursor, ...) Kontext zum aquaPi-Projekt.

## Projektüberblick

aquaPi ist ein Aquarium-/Fischbecken-Controller für Raspberry Pi. Die Software besteht aus modularen
Funktionsblöcken ("Nodes", z. B. Sensor-Input, Schwellwert, Relais-Output, History), die zu Regelketten
verbunden werden. Zielplattform ist Raspberry Pi OS (32/64bit); Entwicklung funktioniert auf jedem Linux-
System mit Python 3.10+. Alle Hardware-Treiber unterstützen einen Simulationsmodus, sodass für die
Entwicklung kein echter Raspberry Pi nötig ist.

- **Backend**: Python/Flask, liegt unter `aquaPi/`.
- **Frontend**: Vue-SPA (Vuetify) unter `aquaPi/static/spa`, eingebunden über
  `aquaPi/templates/pages/spa.html.jinja2`.
- **Zeitreihen-Datenbank**: QuestDB (optional/für History-Daten); Backend-Tests benötigen sie aber nicht.
- **Kernmodule** in `aquaPi/`: `machineroom/` (Node-Engine/Regelketten), `driver/` (Hardware-Treiber, u. a.
  `driver/tc420`), `home/`, `pages/`, `settings/`, `config/`, `api.py`, `auth.py`, `db.py`.

## Setup & Ausführen

```bash
. init            # muss gesourced werden ("." nicht "bash init"), erstellt venv und installiert Abhängigkeiten
./run             # startet die Entwicklungsinstanz
```

`init` erkennt Debian- vs. Arch-basierte Systeme und installiert bei Bedarf `python3-venv`/`python3-dev`.
Beim ersten Aufruf werden zusätzlich Git-Submodule initialisiert (u. a. `aquaPi/driver/tc420`).

`run` setzt `FLASK_APP=aquaPi` und startet `flask run`. Optionen:
- `-t TOPO`: verwendet `instance/TOPO.pickle` zum Speichern der Regelketten-Topologie (Default: `topo`).
- `-r`: setzt die Topologie zurück (löscht die Pickle-Datei vor dem Start).

Abhängigkeiten stehen in `requirements.txt` (u. a. Flask, Flask-Login, RPi.GPIO, Adafruit-Blinka/ADS1x15
für den ADC, croniter für Zeitpläne); `requirements-dev.txt` ergänzt nur `pytest`/`pytest-mock` für die
Testsuite und referenziert `requirements.txt` per `-r`.

## Architektur & Kernmodule

- `aquaPi/__init__.py`: Flask-App-Factory, Registrierung von Blueprints.
- `aquaPi/api.py`, `aquaPi/auth.py`, `aquaPi/db.py`: REST-API, Authentifizierung (Flask-Login), DB-Zugriff.
- `aquaPi/machineroom/`: Node-Engine der Regelketten.
  - `msg_bus.py`/`msg_types.py`: Nachrichtenbus, über den Nodes lose gekoppelt kommunizieren.
  - `in_nodes.py`: Eingangs-Nodes (Sensoren, z. B. Temperatur, pH, ADC).
  - `ctrl_nodes.py`: Steuerungs-/Logik-Nodes (z. B. Schwellwert, Durchschnitt).
  - `out_nodes.py`: Ausgangs-Nodes (z. B. Relais, PWM-Dimmer).
  - `aux_nodes.py`, `alert_nodes.py`, `hist_nodes.py`: Hilfs-, Alarm- und History-Nodes.
- `aquaPi/driver/`: Hardware-Treiber, jeweils mit Simulationsmodus.
  - `base.py`: gemeinsame Basisklassen/Interfaces für Treiber.
  - `DriverGPIO.py`, `DriverPWM.py`, `DriverOneWire.py` (z. B. DS1820), `DriverADC.py` (z. B. ADS1115 für
    pH-Sonden), `DriverTC420.py`, `DriverText.py` (Debug/Simulation).
  - `driver/tc420/`: Git-Submodul für den externen TC420-LED-Controller.
- `aquaPi/home/`, `aquaPi/pages/`, `aquaPi/settings/`: Flask-Blueprints für Startseite, allgemeine Seiten
  und Einstellungen.
- `aquaPi/static/spa/`: Vue-SPA-Quellcode (Komponenten, Store), eingebunden via
  `aquaPi/templates/pages/spa.html.jinja2`.
- Laufzeitdaten liegen in `instance/` (u. a. die Topologie-Pickle-Datei und die SQLite-Datenbank) und
  `logs/` (`aquaPi.log`).

Die Blueprints werden in `aquaPi/__init__.py` (App-Factory `create_app`) in dieser Reihenfolge registriert:
`auth.bp` (Login/Auth-Routen), `api.bp` (REST-API, u. a. Node-CRUD, History, Dashboards, Notifications),
`pages/spa.bp` (liefert die Vue-SPA aus). `aquaPi/api.py`, `aquaPi/auth.py` und `aquaPi/db.py` sind mit
941, 401 bzw. 1860 Zeilen die umfangreichsten Backend-Module.

Logging ist in `aquaPi/__init__.py` über `logging.config.dictConfig()` konfiguriert, gesteuert durch das
Dict `log_default` (dient als Vorlage für eine optionale `instance/log_config.json`, die zur Laufzeit
Vorrang hat, falls vorhanden). Zwei Handler sind aktiv:
- `stdout` (`logging.StreamHandler`, Level `INFO`) für die Konsolenausgabe.
- `file` (`logging.handlers.RotatingFileHandler`, Level `WARNING`) schreibt nach `logs/aquaPi.log`
  (max. 1 MB, 3 Backups).

Beide nutzen das Format `%(asctime)s %(levelname).3s %(name)s: %(message)s` mit Zeitstempel `%H:%M:%S`.
Der `root`-Logger steht auf `WARNING` und nutzt beide Handler; darunter sind eigene Logger je Modulgruppe
vordefiniert (`aquaPi`, `machineroom`, `driver`, `pages`, jeweils `NOTSET`, d. h. sie erben das Level vom
`root`-Logger), sowie feingranularere, aktuell auskommentierte Logger je Einzelmodul (z. B.
`aquaPi.api`, `machineroom.ctrl_nodes`, `driver.DriverADC`), die bei Bedarf gezielt aktiviert werden
können. Der Kommentar in `__init__.py` weist darauf hin, dass diese Liste gelegentlich mit
`grep logging.getLogger $(git ls-files *.py)` synchronisiert werden sollte. Der `werkzeug`-Logger ist
separat auf `WARNING` gesetzt (mit `propagate: False`), da er bei `INFO` jeden HTTP-Request protokolliert.

Auf dem Logger `aquaPi` (`log = logging.getLogger('aquaPi')`) existiert zusätzlich der Alias
`log.brief = log.warning` für kurze Statusmeldungen; `logging.addLevelName(logging.WARN, 'LOG')` sorgt
dafür, dass WARNING-Meldungen im Log als Level "LOG" erscheinen, während INFO für ausführlichere
Meldungen genutzt wird. Beim App-Start wird `logging.warning("Press CTRL+C to quit")` ausgegeben, sodass
diese Zeile stets als erste Meldung im Log erscheint.

## Frontend (SPA)

Die Vue-SPA liegt komplett unter `aquaPi/static/spa/` und wird ohne Build-Step ausgeliefert: alle
Bibliotheken (Vue 3.5.40, Pinia 4.0.2, vue-router 4.6.4, vue-i18n 9.14.5, Vuetify 3.13.0, chart.js,
luxon, sortablejs, `vue3-sfc-loader`) liegen als statische Dateien unter `aquaPi/static/libs/` und
werden in `aquaPi/templates/pages/spa.html.jinja2` per `<script>`-Tags eingebunden (im Debug-Modus die
unminifizierten `*.global.js`-Varianten, sonst die `*.min.js`-Varianten). Einstiegspunkt ist
`aquaPi/static/spa/main.js` (als ES-Modul `type="module"` eingebunden), das App, Router, Pinia, i18n
und Vuetify verdrahtet und global mountet (`app.mount('#app')`).

- **Kein Build/Bundler**: `.vue`-Single-File-Components werden nicht vorkompiliert, sondern zur Laufzeit
  im Browser per `vue3-sfc-loader` (`aquaPi/static/spa/sfc/loadSfc.js`) geladen und kompiliert. Der
  Flask-Backend liefert `.vue`-Dateien einfach als statische Assets aus.
  - Kompilierte Module werden zusätzlich im `localStorage` unter dem Präfix `aquapi.sfc.<CACHE_VERSION>.`
    gecacht; `CACHE_VERSION` in `loadSfc.js` muss bei Änderungen an Loader/Compiler-Semantik erhöht
    werden, um alte Caches zu invalidieren.
  - Wichtige Einschränkung: `vue3-sfc-loader` parst `.js`-Abhängigkeiten mit Babels "script"-Sourcetype,
    daher können `.vue`-SFCs normale `.js`-Module nicht direkt per `import` einbinden. Stattdessen
    werden gemeinsame Module (z. B. `EventBus`, Pinia-Stores, `loadSfc` selbst) über `moduleCache` in
    `loadSfc.js` unter virtuellen Modulnamen wie `app/EventBus`, `store/ui`, `sfc/loadSfc` bereitgestellt,
    die SFCs dann importieren können.
- **Routing**: `aquaPi/static/spa/router/index.js` nutzt `vue-router` mit `createWebHashHistory()`
  (Hash-basierte URLs, `/#/...`). Seiten (`Home.vue`, `Settings.vue`, `Config.vue`, `About.vue`,
  `Users.vue`) liegen unter `aquaPi/static/spa/pages/` und werden lazy per `loadSfc()` geladen; das
  Layout `layouts/Default.vue` ist die gemeinsame Route-Wurzel. Die `users`-Route hat einen
  `beforeEnter`-Guard, der nur Admins zulässt (sonst Redirect auf `home`).
- **State-Management**: Pinia-Stores liegen unter `aquaPi/static/spa/store/modules/` (`auth.js`,
  `config.js`, `dashboard.js`, `settings.js`, `ui.js`, `users.js`); `store/index.js` erstellt nur die
  zentrale Pinia-Instanz.
- **Globale Komponenten**: Da Vue 3 kein globales `Vue.component(...)` mehr kennt, registrieren sich
  Komponenten-Module (z. B. `components/dashboard/index.js`, `components/config/index.js`,
  `components/settings/index.js`, `components/users/index.js`, `components/app/index.js`)
  selbst zur Ladezeit über `registerGlobalComponent()` (`components/app/registry.js`); `main.js` ruft
  einmalig `installGlobalComponents(app)` nach `Vue.createApp()` auf, spätere Registrierungen (z. B.
  durch lazy geladene Seiten) gehen direkt an die gemerkte `app`-Instanz.
- **Sonstiges**: `components/app/EventBus.js` dient als einfacher Event-Bus für app-weite Events
  (`AQUAPI_EVENTS`, u. a. `APP_LOADING`, `AUTH_LOGGED_IN`, `CONFIRM_REQUESTED`, `TOAST_REQUESTED`).
  `i18n/index.js` mit Locales unter `i18n/locales/` (`de.js`, `en.js`) übersetzt die Oberfläche; Theme
  (Dark/Light) und Sprache werden im `localStorage` unter `aquapi.theme` bzw. `aquapi.locale`
  persistiert. Der eingeloggte User wird beim Start via `usersStore.fetchCurrentUser()` gegen die
  Flask-Login-Session abgeglichen, damit ein Browser-Refresh die Session korrekt widerspiegelt.

## Sicherheit

- **Keine Secrets in den Agenten-Kontext laden**: Folgende Dateien/Verzeichnisse enthalten sensible
  Daten (Passwort-Hashes, Session-Secrets, ggf. SMTP-Zugangsdaten, Tokens) und dürfen niemals geöffnet,
  zitiert, geloggt oder in Prompts/Commits eingefügt werden:
  - `instance/` komplett, insbesondere `instance/secret_key` (persistierter Flask `SECRET_KEY`, siehe
    `auth.py: _get_or_create_secret_key()`) und die SQLite-Datenbank(en) darin (Users-Tabelle mit
    `password_hash`, `notification_config`-Tabelle mit SMTP-Login/Passwort für E-Mail-Alarme sowie
    Password-Reset-Tokens).
  - `logs/aquaPi.log` (und Rotationsdateien) - kann im Fehlerfall unbeabsichtigt sensible Details
    enthalten, sollte daher nicht ungeprüft weiterverarbeitet werden.
  - `.env`-Dateien oder ähnliche lokale Konfigurationsdateien mit Zugangsdaten, falls vorhanden.
  - Alle Dateien, die auf `.gitignore` stehen, sind grundsätzlich als potenziell sensibel zu behandeln.
- **Passwörter**: Werden ausschließlich als `werkzeug`-Passwort-Hash gespeichert (`auth.py`,
  `db.py`), nie im Klartext. Der initiale Admin-Account erhält beim ersten Start ein zufällig
  generiertes Passwort (`db.ensure_default_admin()`), das nur einmalig geloggt wird.
- **`SECRET_KEY`**: In `create_app()` (`aquaPi/__init__.py`) zunächst nur ein Platzhalter
  (`'ToDo during installation'`); `auth.init_app()` überschreibt ihn zur Laufzeit mit einem in
  `instance/secret_key` persistierten, zufällig generierten Wert. Dieser Wert darf niemals hartcodiert,
  ausgegeben oder versioniert werden.
- **Keine Klartext-Zugangsdaten im Code oder in Beispielen**: SMTP-Zugangsdaten für Alarm-E-Mails
  werden über die `notification_config`-Tabelle (DB) verwaltet, nicht im Quellcode. Neue Features
  sollten Zugangsdaten analog über DB/Instance-Konfiguration statt über Konstanten oder Kommentare
  im Code handhaben.
- **Login-Schutz**: `auth.py` implementiert ein einfaches Lockout nach fehlgeschlagenen Login-Versuchen
  (nach Username, sonst nach Remote-IP) sowie Single-Use-Tokens für Passwort-Reset-Links - diese
  Mechanismen sollten bei Änderungen an `auth.py` nicht versehentlich geschwächt werden.
- Beim Diagnostizieren von Bugs oder Analysieren von Logs: Ausgaben grundsätzlich auf enthaltene
  Zugangsdaten/Hashes/Tokens prüfen, bevor sie zitiert oder weitergegeben werden.

## Commit & Push

- KI-Agenten sollen niemals eigenständig committen oder pushen, außer der Nutzer fordert dies explizit an.
- Wird ein Commit explizit gewünscht, ist ein Co-Autor-Trailer anzuhängen, z. B. für Junie:
  `git commit --trailer "Co-authored-by: Junie <junie@jetbrains.com>"` (andere Tools nutzen ihren eigenen
  Namen/E-Mail-Trailer entsprechend).
- Commit-Messages sollen kurz und aussagekräftig sein und den geänderten Bereich benennen (z. B.
  `AGENTS.md: ...`, `api: ...`, `spa: ...`); sie sind immer auf Englisch zu verfassen, unabhängig von
  der Sprache der Konversation mit dem Nutzer.
- Niemals Dateien aus dem Abschnitt "Sicherheit" (`instance/`, `logs/`, `.env`, `.gitignore`-Einträge)
  committen oder deren Inhalte in Commit-Messages zitieren.
- Vor einem Commit `pytest -m "not questdb"` lokal ausführen, sofern Backend-Code geändert wurde.
- Kein `git push` ohne ausdrückliche Aufforderung des Nutzers; ebenso keine destruktiven Git-Operationen
  (`reset`, `checkout`, `restore`, `stash`, `clean`, `push --force`) auf bereits committete oder
  gepushte Änderungen, außer explizit gewünscht.
- Größere, risikoreiche Änderungen (Refactorings, DB-Schema) nicht ungefragt committen, siehe Abschnitt
  "Nicht-Ziele".

## Tests

Die Backend-Testsuite (`tests/`) nutzt `pytest`, braucht keine echte Hardware und keine laufende
QuestDB-Instanz - jeder Test baut sich eine eigene temporäre SQLite-DB und einen Node-Bus im
Simulationsmodus auf.

```bash
pip install -r requirements-dev.txt
pytest
```

Ein Teil der Tests ist mit dem Marker `questdb` versehen und läuft nur sinnvoll gegen eine echte
QuestDB-Instanz. Ohne diese Instanz gezielt ausschließen:

```bash
pytest -m "not questdb"
```

Testkonfiguration: `pytest.ini` (`testpaths = tests`). Gemeinsame Fixtures liegen in
`tests/conftest.py`. Testdateien folgen dem Schema `tests/test_<bereich>.py`
(z. B. `test_auth.py`, `test_auth_db.py`, `test_api_nodes.py`, `test_node_crud_api.py`,
`test_history_export.py`, `test_dashboards.py`, `test_notifications.py`).

## Konventionen

- Neue Tests folgen dem bestehenden Namensschema `test_*.py` und nutzen die Fixtures aus
  `tests/conftest.py` statt eigene DB-/App-Instanzen aufzusetzen.
- Änderungen am Backend sollten mit `pytest -m "not questdb"` lokal geprüft werden, bevor QuestDB-
  abhängige Tests separat betrachtet werden.
- Frontend-Code liegt unter `aquaPi/static/spa`; Änderungen dort sollten den bestehenden Vue/Vuetify-Stil
  beibehalten.
- Pläne liegen unter `.junie/plans/`; das ist ein Junie-spezifisches Format, andere Tools (Claude Code,
  Cursor, ...) lesen diese Dateien nicht automatisch und müssen explizit darauf verwiesen werden.

## Bekannte Stolpersteine

- Im Projekt-Root liegen QuestDB-Archive/Verzeichnisse (`questdb-7.1.3*`) - diese sind Laufzeit-Artefakte
  und keine zu bearbeitenden Quellcode-Dateien.
- `instance/` und `logs/` enthalten Laufzeitdaten (u. a. `logs/aquaPi.log`) und sollten nicht versioniert
  oder als Quellcode behandelt werden.
- Die Konfiguration der Regelketten (Nodes) hat noch keine vollständige UI; teilweise muss dafür
  weiterhin Python-Quellcode angepasst werden.

## Nicht-Ziele

- Keine großen Refactorings ohne Rücksprache.
- Keine Änderungen am DB-Schema ohne begleitende Migration.
- Keine Abhängigkeit neuer Tests von echter Hardware oder einer laufenden QuestDB-Instanz (Marker
  `questdb` verwenden, falls unvermeidbar).
