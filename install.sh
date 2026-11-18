#!/usr/bin/env bash
# aquaPi - Installationsskript für eine fertige (Kunden-)Installation.
# aquaPi - installer for a release (end-user) installation.
#
# Bitte NICHT per "curl ... | bash" ausführen - erst herunterladen, dann
# starten, damit Eingabeaufforderungen während der Einrichtung
# funktionieren. / Do NOT run it via "curl ... | bash" - download it
# first, so the prompts during setup work:
#
#   curl -fsSL -o install.sh https://github.com/schwabix-1311/aquaPI/releases/latest/download/install.sh
#   bash install.sh
#
# Sprache / language: wird am Anfang gefragt, Vorgabe aus $LANG; ohne
# Frage mit "bash install.sh --lang de|en" oder AQUAPI_LANG=de|en.
#
# Anleitung / guide: INSTALLATION.de.md, INSTALLATION.md
# (https://github.com/schwabix-1311/aquaPI/blob/main/INSTALLATION.md).

set -euo pipefail

REPO="schwabix-1311/aquaPI"
INSTALL_DIR="${AQUAPI_INSTALL_DIR:-$HOME/aquaPI}"

# --- Sprache / language -----------------------------------------------------
# Raspberry Pi OS steht ab Werk auf en_GB, und über SSH kommt $LANG oft
# nicht an - deshalb wird gefragt, $LANG ist nur die Vorgabe. Die Wahl geht
# per AQUAPI_LANG an ./manage und wird in instance/language gespeichert,
# damit ein späteres "./manage reconfig" dieselbe Sprache spricht.

UI_LANG="${AQUAPI_LANG:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --lang=*) UI_LANG="${1#--lang=}"; shift ;;
    --lang) shift; UI_LANG="${1:-}"; [ $# -gt 0 ] && shift ;;
    *) shift ;;
  esac
done
if [ -z "$UI_LANG" ]; then
  case "${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}" in
    de*) default_lang=d ;;
    *) default_lang=e ;;
  esac
  read -r -p "Sprache / Language: [d]eutsch / [e]nglish [$default_lang] " antwort
  UI_LANG="${antwort:-$default_lang}"
fi
case "$UI_LANG" in
  [dD]*) UI_LANG=de ;;
  *) UI_LANG=en ;;
esac
export AQUAPI_LANG="$UI_LANG"

# t "deutsch" "english" - gibt den Text in der gewählten Sprache aus
t() {
  if [ "$UI_LANG" = de ]; then printf '%s\n' "$1"; else printf '%s\n' "$2"; fi
}

# Ja/Nein-Fragen; j und y gelten in beiden Sprachen
frage_nein() {  # $1/$2 = Frage de/en; Enter bedeutet Nein
  local antwort
  read -r -p "$(t "$1 [j/N]" "$2 [y/N]") " antwort
  case "$antwort" in
    [jJyY]*) return 0 ;;
    *) return 1 ;;
  esac
}

frage_ja() {  # $1/$2 = Frage de/en; Enter bedeutet Ja
  local antwort
  read -r -p "$(t "$1 [J/n]" "$2 [Y/n]") " antwort
  case "$antwort" in
    [nN]*) return 1 ;;
    *) return 0 ;;
  esac
}

abbruch() {  # Abbrechen, ohne etwas verändert zu haben
  t "Abgebrochen. Es wurde nichts verändert." "Cancelled. Nothing was changed."
  exit 1
}

echo
echo "======================================================"
t " aquaPi wird eingerichtet" " Setting up aquaPi"
echo "======================================================"
echo

# --- Voraussetzungen prüfen ------------------------------------------------

if ! grep -qi debian /usr/lib/os-release 2>/dev/null; then
  t "Hinweis: Dieses Skript ist für Raspberry Pi OS (bzw. andere" \
    "Note: this script is meant for Raspberry Pi OS (or other"
  t "Debian-basierte Systeme) gedacht. Dein System scheint ein anderes zu sein." \
    "Debian-based systems). Your system seems to be a different one."
  frage_nein "Trotzdem fortfahren?" "Continue anyway?" || abbruch
fi

for cmd in curl tar python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    t "FEHLER: '$cmd' wird benötigt, ist aber nicht installiert." \
      "ERROR: '$cmd' is required but not installed."
    t "Bitte installiere es (z.B. mit 'sudo apt-get install $cmd') und starte dieses Skript erneut." \
      "Please install it (e.g. with 'sudo apt-get install $cmd') and run this script again."
    exit 1
  fi
done

# Empfohlen und getestet: Raspberry Pi OS Bookworm, 64 Bit. Nur Hinweise,
# kein Abbruch - aquaPi läuft auch anders, mit Einschränkungen.
if [ "$(getconf LONG_BIT)" != "64" ]; then
  echo
  t "Hinweis: Dies ist ein 32-Bit-System. aquaPi läuft, kann den Verlauf" \
    "Note: this is a 32-bit system. aquaPi runs, but can only keep the"
  t "für die Diagramme aber nur im Arbeitsspeicher halten - nach jedem" \
    "chart history in memory - after every restart the charts start"
  t "Neustart beginnen die Diagramme leer. Empfohlen: Raspberry Pi OS (64-bit)." \
    "empty. Recommended: Raspberry Pi OS (64-bit)."
fi
if ! grep -q '^VERSION_CODENAME=bookworm' /etc/os-release 2>/dev/null; then
  echo
  t "Hinweis: aquaPi ist mit Raspberry Pi OS 'Bookworm' getestet. Dein System" \
    "Note: aquaPi is tested with Raspberry Pi OS 'Bookworm'. Your system"
  t "ist eine andere Version - die Installation kann fehlschlagen." \
    "is a different version - the installation may fail."
  frage_nein "Trotzdem fortfahren?" "Continue anyway?" || abbruch
fi

# --- Installationsverzeichnis wählen ---------------------------------------

# UPDATE=1: vorhandene Installation aktualisieren. instance/ (Verdrahtung,
# Benutzer, Benachrichtigungen, Sicherungen), venv/, logs/ und QuestDB
# bleiben erhalten, nur das Programm selbst wird ersetzt.
UPDATE=0
if [ -d "$INSTALL_DIR/instance" ]; then
  t "In $INSTALL_DIR ist aquaPi bereits installiert." \
    "aquaPi is already installed in $INSTALL_DIR."
  echo
  if [ "$UI_LANG" = de ]; then
    echo "  [A] Aktualisieren - deine Einstellungen, Benutzer und Sicherungen"
    echo "      bleiben erhalten (empfohlen)"
    echo "  [N] Neu installieren - löscht ALLES, auch deine Einstellungen und"
    echo "      Sicherungen"
    echo "  [Q] Abbrechen"
    echo
    read -r -p "Deine Wahl [A/n/q] " antwort
    neu='[nN]*'
  else
    echo "  [U] Update - your settings, users and backups are kept"
    echo "      (recommended)"
    echo "  [R] Reinstall - deletes EVERYTHING, including your settings and"
    echo "      backups"
    echo "  [Q] Quit"
    echo
    read -r -p "Your choice [U/r/q] " antwort
    neu='[rR]*'
  fi
  # shellcheck disable=SC2254  # $neu ist absichtlich ein Muster
  case "$antwort" in
    $neu)
      frage_nein "Wirklich alles löschen, auch alle Sicherungen?" \
                 "Really delete everything, including all backups?" || abbruch
      rm -rf "$INSTALL_DIR" ;;
    [qQ]*) abbruch ;;
    *) UPDATE=1 ;;
  esac
elif [ -d "$INSTALL_DIR" ]; then
  t "Das Verzeichnis $INSTALL_DIR existiert bereits." \
    "The directory $INSTALL_DIR already exists."
  frage_nein "Vorhandenes Verzeichnis löschen und neu einrichten?" \
             "Delete the existing directory and set it up anew?" || abbruch
  rm -rf "$INSTALL_DIR"
fi

echo
t "Installationsverzeichnis: $INSTALL_DIR" "Installation directory: $INSTALL_DIR"

# --- Release herunterladen und entpacken -----------------------------------

echo
t "Lade die aktuelle aquaPi-Version herunter ..." "Downloading the current aquaPi version ..."
TMP_ARCHIVE=$(mktemp)
trap 'rm -f "$TMP_ARCHIVE"' EXIT
curl -fsSL -o "$TMP_ARCHIVE" \
  "https://github.com/${REPO}/releases/latest/download/aquapi-latest.tar.gz"

if [ "$UPDATE" -eq 1 ]; then
  echo
  t "Sichere deine Einstellungen und stoppe aquaPi für das Update ..." \
    "Backing up your settings and stopping aquaPi for the update ..."
  (cd "$INSTALL_DIR" && ./manage backup) \
    || t "Hinweis: Die Sicherung vor dem Update ist fehlgeschlagen - die tägliche Sicherung in instance/backups bleibt erhalten." \
         "Note: the backup before the update failed - the daily backups in instance/backups are kept."
  sudo systemctl stop aquapi 2>/dev/null || true
  # alles außer den Nutzerdaten und der Laufzeitumgebung entfernen, damit
  # im neuen Release gelöschte Dateien nicht liegen bleiben
  find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 \
    ! -name instance ! -name venv ! -name logs ! -name 'questdb-*' \
    -exec rm -rf {} +
fi

mkdir -p "$INSTALL_DIR"
tar xzf "$TMP_ARCHIVE" -C "$INSTALL_DIR"
cd "$INSTALL_DIR"
mkdir -p instance
printf '%s\n' "$UI_LANG" > instance/language

# --- Python-Umgebung und Abhängigkeiten einrichten --------------------------

echo
t "Richte Python-Umgebung und Abhängigkeiten ein (das kann einige Minuten dauern) ..." \
  "Setting up Python and dependencies (this can take a few minutes) ..."
t "Falls dabei 'CR to continue' erscheint: einfach die Eingabetaste (Enter) drücken." \
  "If 'CR to continue' shows up: just press Enter."
# shellcheck disable=SC1091
. ./init Prod

# --- TC420-LED-Controller vorbereiten (schadet nicht, falls nicht vorhanden) -

echo
t "Bereite den optionalen TC420-LED-Controller vor (überspring das" \
  "Preparing the optional TC420 LED controller (just ignore this"
t "einfach gedanklich, falls du keinen besitzt - es schadet nichts)." \
  "if you don't own one - it does no harm)."
sudo cp aquaPi/driver/tc420/etc/udev/rules.d/99-tc420.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo usermod -aG plugdev "$(whoami)"

# --- SSH-Verbindungen robuster gegen Netzwerkaussetzer machen ---------------
# Ein Pi läuft oft über WLAN; ohne diese Einstellung kann eine SSH-Sitzung
# nach einem kurzen Netzwerkaussetzer stundenlang unbemerkt offen hängen,
# statt zügig als abgebrochen erkannt zu werden.

if [ -f /etc/ssh/sshd_config ] && ! grep -q '^ClientAliveInterval' /etc/ssh/sshd_config; then
  echo
  t "Richte SSH so ein, dass unterbrochene Verbindungen (z.B. nach einem" \
    "Setting up SSH so broken connections (e.g. after a WiFi dropout)"
  t "WLAN-Aussetzer) innerhalb weniger Sekunden erkannt werden." \
    "are detected within a few seconds."
  printf '\n# von aquaPi install.sh ergaenzt: haengende SSH-Sitzungen zuegig erkennen\nClientAliveInterval 15\nClientAliveCountMax 3\n' \
    | sudo tee -a /etc/ssh/sshd_config >/dev/null
  sudo systemctl reload ssh 2>/dev/null || sudo systemctl reload sshd 2>/dev/null || true
fi

# --- WLAN-Watchdog -----------------------------------------------------------
# Der WLAN-Chip des Raspberry Pi (brcmfmac) kann hängen bleiben; der Pi ist
# dann nicht mehr erreichbar, obwohl aquaPi weiter regelt. Der Watchdog
# prüft alle 2 Minuten die Verbindung zum Router und lädt bei Bedarf den
# WLAN-Treiber neu. Nur sinnvoll, wenn der Pi über WLAN verbunden ist.

if ip -4 route show default 2>/dev/null | grep -q " dev wlan0"; then
  echo
  t "Richte den WLAN-Watchdog ein (holt eine hängende WLAN-Verbindung" \
    "Setting up the WiFi watchdog (brings a hung WiFi connection back"
  t "automatisch zurück)." "automatically)."
  system/wifi-watchdog/install.sh >/dev/null \
    || t "Hinweis: Der WLAN-Watchdog konnte nicht eingerichtet werden - aquaPi läuft trotzdem." \
         "Note: the WiFi watchdog could not be set up - aquaPi runs anyway."
fi

# --- Hardware-Schnittstellen des Raspberry Pi einschalten ------------------
# Ein frisch installiertes Raspberry Pi OS hat 1-Wire, I²C und Hardware-PWM
# ausgeschaltet. Ohne sie findet aquaPi keine DS18B20-Temperatursensoren,
# keinen ADS1115 (pH) und keine PWM-Kanäle - deren Port-Auswahl bliebe
# einfach leer. Wirksam erst nach einem Neustart, der ganz am Ende
# angeboten wird. Bereits eingeschaltete Schnittstellen werden nicht
# erneut gefragt.

NEED_REBOOT=0

if grep -qi "raspberry pi" /proc/device-tree/model 2>/dev/null \
   && command -v raspi-config >/dev/null 2>&1; then
  BOOT_CONFIG=/boot/firmware/config.txt
  [ -f "$BOOT_CONFIG" ] || BOOT_CONFIG=/boot/config.txt

  echo
  echo "======================================================"
  t " Hardware-Anschlüsse des Raspberry Pi" " Hardware interfaces of the Raspberry Pi"
  echo "======================================================"
  t "Welche Anschlüsse soll aquaPi nutzen? Im Zweifel einfach mit" \
    "Which interfaces should aquaPi use? If in doubt, just press"
  t "Enter bestätigen - ungenutzte Anschlüsse schaden nicht. Die" \
    "Enter - unused interfaces do no harm. The GPIO pins named are"
  t "genannten GPIO-Pins sind dann aber für diese Funktion reserviert." \
    "reserved for that function, though."
  echo

  # raspi-config meldet bei get_* eine 0, wenn die Schnittstelle an ist
  if [ "$(raspi-config nonint get_onewire)" != "0" ] \
     && frage_ja "Temperatursensoren DS18B20 (1-Wire, an GPIO4) verwenden?" \
                 "Use DS18B20 temperature sensors (1-Wire, on GPIO4)?"; then
    sudo raspi-config nonint do_onewire 0
    NEED_REBOOT=1
  fi
  if [ "$(raspi-config nonint get_i2c)" != "0" ] \
     && frage_ja "pH-Messung/Analogeingänge über ADS1115 (I²C, an GPIO2 und GPIO3) verwenden?" \
                 "Use pH measurement/analog inputs via ADS1115 (I²C, on GPIO2 and GPIO3)?"; then
    sudo raspi-config nonint do_i2c 0
    NEED_REBOOT=1
  fi
  # für PWM gibt es keine raspi-config-Option
  if ! grep -q '^dtoverlay=pwm' "$BOOT_CONFIG" \
     && frage_ja "Hardware-PWM zum Dimmen (an GPIO18 und GPIO19; kann einen analogen Audioausgang stören) verwenden?" \
                 "Use hardware PWM for dimming (on GPIO18 and GPIO19; may disturb an analog audio output)?"; then
    printf '\n[all]\n# von aquaPi install.sh ergaenzt: Hardware-PWM fuer Dimmer\ndtoverlay=pwm-2chan\n' \
      | sudo tee -a "$BOOT_CONFIG" >/dev/null
    NEED_REBOOT=1
  fi
fi

# --- Admin-Zugang anlegen -------------------------------------------------
# Muss vor dem ersten Start des Dienstes passieren: sonst legt aquaPi das
# Konto selbst an und schreibt das Passwort nur ins Systemprotokoll.
# Angezeigt wird es erst ganz am Ende, zusammen mit der Adresse.

ADMIN_INFO=""
if [ "$UPDATE" -eq 0 ]; then
  ADMIN_INFO=$(./manage init-admin)
fi

# --- Benachrichtigungen einrichten ------------------------------------------

GUIDE=$(t INSTALLATION.de.md INSTALLATION.md)

if [ "$UPDATE" -eq 0 ]; then
  echo
  echo "======================================================"
  t " Benachrichtigungen einrichten" " Set up notifications"
  echo "======================================================"
  t "Du kannst jetzt E-Mail- oder Telegram-Benachrichtigungen einrichten" \
    "You can now set up email or Telegram notifications (e.g. for"
  t "(z.B. für Alarme). Das kannst du auch jederzeit später nachholen mit:" \
    "alerts). You can also do this any time later with:"
  echo "  ./manage reconfig"
  t "Für Telegram brauchst du einen Bot-Token von @BotFather, siehe" \
    "For Telegram you need a bot token from @BotFather, see"
  t "\"Benachrichtigungen einrichten\" in $GUIDE." \
    "\"Set up notifications\" in $GUIDE."
  echo
  ./manage reconfig
fi

# --- Als Dienst einrichten ---------------------------------------------------

echo
echo "======================================================"
t " aquaPi als Dienst einrichten" " Setting up aquaPi as a service"
echo "======================================================"
t "aquaPi wird jetzt als Systemdienst eingerichtet, damit es automatisch" \
  "aquaPi is now set up as a system service, so it starts automatically -"
t "startet - auch nach einem Neustart des Raspberry Pi." \
  "also after a reboot of the Raspberry Pi."
echo
./manage service-unit --install --yes

# --- Fertig -------------------------------------------------------------

IP=$(hostname -I | awk '{print $1}')
echo
echo "======================================================"
if [ "$UPDATE" -eq 1 ]; then
  t " Fertig! aquaPi ist aktualisiert und läuft wieder." " Done! aquaPi is updated and running again."
else
  t " Fertig! aquaPi läuft jetzt." " Done! aquaPi is running now."
fi
echo "======================================================"
echo
t " Öffne in deinem Webbrowser:" " Open in your web browser:"
echo "   http://${IP}:5000"
echo
if [ -n "$ADMIN_INFO" ]; then
  echo "${ADMIN_INFO}" | sed 's/^/ /'
  echo
fi
t " Eine ausführliche Anleitung findest du hier:" " A detailed guide is here:"
echo "   https://github.com/${REPO}/blob/main/${GUIDE}"
echo "======================================================"

if [ "$NEED_REBOOT" -eq 1 ]; then
  echo
  t "Die neu eingeschalteten Hardware-Anschlüsse sind erst nach einem" \
    "The newly enabled hardware interfaces only become active after a"
  t "Neustart aktiv. Bitte notiere vorher dein Passwort (siehe oben)." \
    "reboot. Please write down your password first (see above)."
  if frage_ja "Raspberry Pi jetzt neu starten?" "Reboot the Raspberry Pi now?"; then
    sudo reboot
  else
    t "Bitte starte den Raspberry Pi später neu: sudo reboot" \
      "Please reboot the Raspberry Pi later: sudo reboot"
  fi
fi
