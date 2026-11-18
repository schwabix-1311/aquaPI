# aquaPi installieren

*English version: [INSTALLATION.md](INSTALLATION.md)*

Diese Anleitung richtet sich an Aquarium-Liebhaber, nicht an Computer-Profis.
Du brauchst keine Vorkenntnisse in Linux oder Programmierung - nur einen
Raspberry Pi und die Bereitschaft, einen Befehl in ein Terminal-Fenster zu
kopieren.

## Was du brauchst

- Einen Raspberry Pi Zero 2 W, 3, 4 oder 5 (empfohlen) mit angeschlossenen
  Sensoren/Aktoren für dein Aquarium.
- Eine microSD-Karte mit **Raspberry Pi OS "Bookworm", 64-bit** (empfohlen) -
  die Variante "Lite" (ohne Bildschirm-Oberfläche) genügt. aquaPi ist mit
  dieser Version getestet; mit der neueren Version "Trixie" funktioniert
  die Installation derzeit noch nicht.
- **Absolutes Minimum:** ein Raspberry Pi Zero W (oder ein anderes älteres
  Modell) und/oder Raspberry Pi OS "Bookworm" in der **32-bit**-Variante.
  aquaPi regelt damit genauso, aber mit Einschränkungen bei den
  Diagrammen: Der Verlauf wird nur im Arbeitsspeicher gehalten, nach jedem
  Neustart beginnen die Diagramme leer. Ältere Modelle wie der Zero W
  können ohnehin nur die 32-bit-Variante verwenden.
  Das offizielle [Raspberry Pi Imager](https://www.raspberrypi.com/software/)-Programm
  schreibt die SD-Karte in wenigen Minuten. Bookworm findest du dort unter
  "Raspberry Pi OS (other)", meist als "Legacy" bezeichnet - achte auf
  "64-bit".
- Der Raspberry Pi muss mit deinem Heimnetzwerk verbunden sein (WLAN oder
  Netzwerkkabel) und über SSH erreichbar sein. Das lässt sich schon beim
  Schreiben der SD-Karte im Raspberry Pi Imager unter "Erweiterte
  Einstellungen" (Zahnrad-Symbol) einrichten: WLAN-Zugangsdaten eintragen
  und "SSH aktivieren" ankreuzen.

## Terminal öffnen und mit dem Raspberry Pi verbinden

- **Unter Windows**: Öffne die "Eingabeaufforderung" oder "PowerShell"
  (Suche im Startmenü).
- **Unter macOS**: Öffne "Terminal" (Spotlight-Suche, oben rechts das
  Lupensymbol, dann "Terminal" eingeben).
- **Unter Linux**: Du weißt vermutlich schon, wie das geht.

Verbinde dich dann mit deinem Raspberry Pi (ersetze `<Benutzername>` und
`<IP-Adresse>` durch deine eigenen Werte - den Benutzernamen hast du beim
Einrichten der SD-Karte selbst festgelegt, die IP-Adresse findest du in der
Übersicht deines WLAN-Routers):

```
ssh <Benutzername>@<IP-Adresse>
```

Wenn du dich das erste Mal mit diesem Gerät verbindest, wirst du gefragt,
ob du der Verbindung vertraust - mit "yes" bestätigen.

## Installation starten

Kopiere die folgenden zwei Zeilen in dein Terminal-Fenster und drücke die
Eingabetaste (Enter):

```
curl -fsSL -o install.sh https://github.com/schwabix-1311/aquaPI/releases/latest/download/install.sh
bash install.sh
```

Das Installationsskript führt dich ab hier auf Deutsch durch den Rest der
Einrichtung. Es dauert insgesamt etwa 10-20 Minuten (je nach Internet-
Geschwindigkeit deines Raspberry Pi).

## Was während der Installation passiert

- Das Skript lädt die aktuelle aquaPi-Version herunter und richtet die
  benötigte Software ein. Zwischendurch kann eine Meldung "CR to continue"
  erscheinen - dann einfach die Eingabetaste drücken.
- Falls du einen **TC420-LED-Controller** besitzt, wird dieser automatisch
  mit eingerichtet - das ist eine der Besonderheiten von aquaPi gegenüber
  anderen Lösungen. Besitzt du keinen, wird dieser Schritt einfach
  übersprungen bzw. bleibt wirkungslos.
- Du wirst gefragt, welche **Hardware-Anschlüsse** des Raspberry Pi aquaPi
  nutzen soll: Temperatursensoren (1-Wire), pH-Messung über einen ADS1115
  (I²C) und Hardware-PWM zum Dimmen. Im Zweifel einfach mit Enter
  bestätigen. Diese Anschlüsse sind erst nach einem Neustart aktiv - das
  Skript bietet ihn ganz am Ende an.
- Ist der Raspberry Pi per WLAN verbunden, richtet das Skript einen
  **WLAN-Watchdog** ein: Bleibt der WLAN-Chip hängen (beim Raspberry Pi
  gelegentlich zu beobachten), lädt er den WLAN-Treiber neu, sodass der Pi
  nach wenigen Minuten wieder erreichbar ist. aquaPi regelt in der Zwischenzeit
  ohne Unterbrechung weiter.
- Du wirst gefragt, ob du **Benachrichtigungen per E-Mail oder Telegram**
  einrichten möchtest (z.B. für Warnungen, wenn etwas nicht stimmt). Das
  kannst du auch überspringen und später jederzeit nachholen, siehe
  "Benachrichtigungen einrichten".
- Am Ende wird aquaPi als **Dienst** eingerichtet, der automatisch startet -
  auch nach einem Neustart deines Raspberry Pi.

Was dabei am System des Raspberry Pi verändert wird, damit du es
nachvollziehen kannst:

- aquaPi selbst liegt in `~/aquaPI`, der Verlauf für die Diagramme
  (QuestDB) in `~/.questdb`.
- Systemdienste `aquapi` und `questdb`, bei WLAN zusätzlich
  `wifi-watchdog` (Programm in `/usr/local/sbin`).
- Die eingeschalteten Hardware-Anschlüsse (1-Wire, I²C über
  `raspi-config`, Hardware-PWM als Zeile in `/boot/firmware/config.txt`).
- Eine Regel für den TC420 in `/etc/udev/rules.d/`, und dein Benutzer wird
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

Öffne diese Adresse in einem Webbrowser auf einem beliebigen Gerät in
deinem Heimnetzwerk (Computer, Tablet, Smartphone) - dort findest du die
aquaPi-Oberfläche.

Direkt darunter zeigt das Skript deinen **Admin-Zugang** an (Benutzername
`admin` und ein zufällig erzeugtes Passwort). Notiere das Passwort - es
wird nur dieses eine Mal angezeigt. Ohne Anmeldung kannst du die
Oberfläche nur ansehen; zum Einrichten meldest du dich oben rechts an und
änderst das Passwort danach im Menü "Benutzer".

## Benachrichtigungen einrichten

E-Mail und Telegram richtest du während der Installation oder später
jederzeit mit diesem Befehl ein (im Terminal, verbunden mit dem Raspberry
Pi):

```
cd ~/aquaPI && ./manage reconfig
```

**E-Mail:** Du brauchst die Zugangsdaten deines E-Mail-Postfachs
(SMTP-Server, Benutzername, Passwort) - bei vielen Anbietern ein eigenes
"App-Passwort" statt deines normalen Passworts.

**Telegram:** aquaPi schreibt über einen eigenen Telegram-Bot.

1. Bot anlegen: In Telegram mit **@BotFather** chatten, `/newbot` senden
   und einen Namen wählen. BotFather antwortet mit einem **Bot-Token**
   (z.B. `123456789:AA...`) - den gibst du in `./manage reconfig` als
   Erstes ein.
2. Chat festlegen: `./manage reconfig` zeigt dann den Namen deines Bots an
   und bittet dich, eine Nachricht zu senden:
   - in eine **Gruppe** (z.B. mit der Familie): den Bot zur Gruppe
     hinzufügen und dort `/aquapi@<Name deines Bots>` senden,
   - oder **direkt an dich**: den Bot in Telegram öffnen und `aquaPi`
     senden.
3. Enter drücken - aquaPi findet den Chat und fragt, ob es ihn verwenden
   soll.

Wird eine Gruppe später von Telegram in eine "Supergruppe" umgewandelt
(passiert z.B. bei vielen Mitgliedern), bekommt sie eine neue Chat-ID -
dann `./manage reconfig` einfach noch einmal ausführen.

## aquaPi aktualisieren

Für eine neue aquaPi-Version führst du die Installation einfach erneut aus
(die zwei Zeilen aus "Installation starten"). Das Skript erkennt die
vorhandene Installation und fragt nach - wähle **"Aktualisieren"**. Deine
Einstellungen, Benutzer, Benachrichtigungen und Sicherungen bleiben
erhalten; vor dem Update legt das Skript zusätzlich eine Sicherung an.
Nur "Neu installieren" löscht alles.

## Hilfe

Falls etwas nicht funktioniert oder du Fragen hast, melde dich gerne
(auf Deutsch):

- [Discussions](https://github.com/schwabix-1311/aquaPI/discussions) für
  Fragen und Ideen.
- [Issues](https://github.com/schwabix-1311/aquaPI/issues) für konkrete
  Probleme/Fehler.
