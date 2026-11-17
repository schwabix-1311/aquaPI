# aquaPi installieren

Diese Anleitung richtet sich an Aquarium-Liebhaber, nicht an Computer-Profis.
Sie brauchen keine Vorkenntnisse in Linux oder Programmierung - nur einen
Raspberry Pi und die Bereitschaft, einen Befehl in ein Terminal-Fenster zu
kopieren.

## Was Sie brauchen

- Einen Raspberry Pi Zero 2 W, 3, 4 oder 5 mit angeschlossenen
  Sensoren/Aktoren für Ihr Aquarium. Ältere Modelle (Zero, Zero W, 1, 2)
  funktionieren auch, können den Verlauf für die Diagramme aber nur im
  Arbeitsspeicher halten - nach jedem Neustart beginnen die Diagramme leer.
- Eine microSD-Karte mit **Raspberry Pi OS "Bookworm", 64-bit** - die
  Variante "Lite" (ohne Bildschirm-Oberfläche) genügt. aquaPi ist mit
  dieser Version getestet; mit der neueren Version "Trixie" funktioniert
  die Installation derzeit noch nicht.
  Das offizielle [Raspberry Pi Imager](https://www.raspberrypi.com/software/)-Programm
  schreibt die SD-Karte in wenigen Minuten. Bookworm finden Sie dort unter
  "Raspberry Pi OS (other)", meist als "Legacy" bezeichnet - achten Sie auf
  "64-bit".
- Der Raspberry Pi muss mit Ihrem Heimnetzwerk verbunden sein (WLAN oder
  Netzwerkkabel) und über SSH erreichbar sein. Das lässt sich schon beim
  Schreiben der SD-Karte im Raspberry Pi Imager unter "Erweiterte
  Einstellungen" (Zahnrad-Symbol) einrichten: WLAN-Zugangsdaten eintragen
  und "SSH aktivieren" ankreuzen.

## Terminal öffnen und mit dem Raspberry Pi verbinden

- **Unter Windows**: Öffnen Sie die "Eingabeaufforderung" oder "PowerShell"
  (Suche im Startmenü).
- **Unter macOS**: Öffnen Sie "Terminal" (Spotlight-Suche, oben rechts das
  Lupensymbol, dann "Terminal" eingeben).
- **Unter Linux**: Sie wissen vermutlich schon, wie das geht.

Verbinden Sie sich dann mit Ihrem Raspberry Pi (ersetzen Sie `<Benutzername>`
und `<IP-Adresse>` durch Ihre eigenen Werte - beides haben Sie beim
Einrichten der SD-Karte selbst festgelegt bzw. finden die IP-Adresse in der
Übersicht Ihres WLAN-Routers):

```
ssh <Benutzername>@<IP-Adresse>
```

Falls Sie das erste Mal eine Verbindung zu diesem Gerät herstellen, werden
Sie gefragt, ob Sie der Verbindung vertrauen möchten - mit "yes" bestätigen.

## Installation starten

Kopieren Sie die folgenden zwei Zeilen in Ihr Terminal-Fenster und drücken
Sie die Eingabetaste (Enter):

```
curl -fsSL -o install.sh https://github.com/schwabix-1311/aquaPI/releases/latest/download/install.sh
bash install.sh
```

Das Installationsskript führt Sie ab hier auf Deutsch durch den Rest der
Einrichtung. Es dauert insgesamt etwa 10-20 Minuten (je nach Internet-
Geschwindigkeit Ihres Raspberry Pi).

## Was während der Installation passiert

- Das Skript lädt die aktuelle aquaPi-Version herunter und richtet die
  benötigte Software ein. Zwischendurch kann eine Meldung "CR to continue"
  erscheinen - dann einfach die Eingabetaste drücken.
- Falls Sie einen **TC420-LED-Controller** besitzen, wird dieser automatisch
  mit eingerichtet - das ist eine der Besonderheiten von aquaPi gegenüber
  anderen Lösungen. Besitzen Sie keinen, wird dieser Schritt einfach
  übersprungen bzw. bleibt wirkungslos.
- Sie werden gefragt, welche **Hardware-Anschlüsse** des Raspberry Pi aquaPi
  nutzen soll: Temperatursensoren (1-Wire), pH-Messung über einen ADS1115
  (I²C) und Hardware-PWM zum Dimmen. Im Zweifel einfach mit Enter
  bestätigen. Diese Anschlüsse sind erst nach einem Neustart aktiv - das
  Skript bietet ihn ganz am Ende an.
- Ist der Raspberry Pi per WLAN verbunden, richtet das Skript einen
  **WLAN-Watchdog** ein: Bleibt der WLAN-Chip hängen (beim Raspberry Pi
  gelegentlich zu beobachten), lädt er den WLAN-Treiber neu, sodass der Pi
  nach wenigen Minuten wieder erreichbar ist. aquaPi regelt in der Zwischenzeit
  ohne Unterbrechung weiter.
- Sie werden gefragt, ob Sie **Benachrichtigungen per E-Mail oder Telegram**
  einrichten möchten (z.B. für Warnungen, wenn etwas nicht stimmt). Das
  können Sie auch überspringen und später jederzeit nachholen.
- Am Ende wird aquaPi als **Dienst** eingerichtet, der automatisch startet -
  auch nach einem Neustart Ihres Raspberry Pi.

Was dabei am System des Raspberry Pi verändert wird, damit Sie es
nachvollziehen können:

- aquaPi selbst liegt in `~/aquaPI`, der Verlauf für die Diagramme
  (QuestDB) in `~/.questdb`.
- Systemdienste `aquapi` und `questdb`, bei WLAN zusätzlich
  `wifi-watchdog` (Programm in `/usr/local/sbin`).
- Die eingeschalteten Hardware-Anschlüsse (1-Wire, I²C über
  `raspi-config`, Hardware-PWM als Zeile in `/boot/firmware/config.txt`).
- Eine Regel für den TC420 in `/etc/udev/rules.d/`, und Ihr Benutzer wird
  Mitglied der Gruppe `plugdev`.
- In `/etc/ssh/sshd_config` zwei Zeilen (`ClientAliveInterval`) und in
  `~/.ssh/config` ein Abschnitt `Host *` (`ServerAliveInterval`), damit
  eine nach einem WLAN-Aussetzer abgebrochene SSH-Verbindung schnell
  erkannt wird.

## Fertig - aquaPi öffnen

Am Ende der Installation zeigt das Skript eine Internetadresse an, z.B.:

```
http://192.168.1.42:5000
```

Öffnen Sie diese Adresse in einem Webbrowser auf einem beliebigen Gerät in
Ihrem Heimnetzwerk (Computer, Tablet, Smartphone) - dort finden Sie die
aquaPi-Oberfläche.

Direkt darunter zeigt das Skript Ihren **Admin-Zugang** an (Benutzername
`admin` und ein zufällig erzeugtes Passwort). Notieren Sie das Passwort -
es wird nur dieses eine Mal angezeigt. Ohne Anmeldung können Sie die
Oberfläche nur ansehen; zum Einrichten melden Sie sich oben rechts an und
ändern das Passwort danach im Menü "Benutzer".

## aquaPi aktualisieren

Für eine neue aquaPi-Version führen Sie die Installation einfach erneut
aus (die zwei Zeilen aus "Installation starten"). Das Skript erkennt die
vorhandene Installation und fragt nach - wählen Sie **"Aktualisieren"**.
Ihre Einstellungen, Benutzer, Benachrichtigungen und Sicherungen bleiben
erhalten; vor dem Update legt das Skript zusätzlich eine Sicherung an.
Nur "Neu installieren" löscht alles.

## Hilfe

Falls etwas nicht funktioniert oder Sie Fragen haben, können Sie sich gerne
(auf Deutsch) melden:

- [Discussions](https://github.com/schwabix-1311/aquaPI/discussions) für
  Fragen und Ideen.
- [Issues](https://github.com/schwabix-1311/aquaPI/issues) für konkrete
  Probleme/Fehler.
