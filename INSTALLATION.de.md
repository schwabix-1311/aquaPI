# aquaPi installieren

Diese Anleitung richtet sich an Aquarium-Liebhaber, nicht an Computer-Profis.
Sie brauchen keine Vorkenntnisse in Linux oder Programmierung - nur einen
Raspberry Pi und die Bereitschaft, einen Befehl in ein Terminal-Fenster zu
kopieren.

## Was Sie brauchen

- Einen Raspberry Pi (empfohlen: Raspberry Pi 3 oder neuer) mit angeschlossenen
  Sensoren/Aktoren für Ihr Aquarium.
- Eine microSD-Karte, auf die bereits **Raspberry Pi OS** installiert wurde.
  Falls noch nicht geschehen: Das offizielle
  [Raspberry Pi Imager](https://www.raspberrypi.com/software/)-Programm
  macht das in wenigen Minuten - einfach eine SD-Karte auswählen,
  "Raspberry Pi OS" auswählen und schreiben lassen.
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
- Sie werden gefragt, ob Sie **Benachrichtigungen per E-Mail oder Telegram**
  einrichten möchten (z.B. für Warnungen, wenn etwas nicht stimmt). Das
  können Sie auch überspringen und später jederzeit nachholen.
- Am Ende wird aquaPi als **Dienst** eingerichtet, der automatisch startet -
  auch nach einem Neustart Ihres Raspberry Pi.

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

## Hilfe

Falls etwas nicht funktioniert oder Sie Fragen haben, können Sie sich gerne
(auf Deutsch) melden:

- [Discussions](https://github.com/schwabix-1311/aquaPI/discussions) für
  Fragen und Ideen.
- [Issues](https://github.com/schwabix-1311/aquaPI/issues) für konkrete
  Probleme/Fehler.
