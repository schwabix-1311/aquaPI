#!/usr/bin/env bash
# aquaPi - Installationsskript für eine fertige (Kunden-)Installation.
#
# Bitte NICHT per "curl ... | bash" ausführen - erst herunterladen, dann
# starten, damit Eingabeaufforderungen während der Einrichtung
# funktionieren:
#
#   curl -fsSL -o install.sh https://github.com/schwabix-1311/aquaPI/releases/latest/download/install.sh
#   bash install.sh
#
# Eine ausführliche, bebilderte Anleitung finden Sie in INSTALLATION.de.md
# (https://github.com/schwabix-1311/aquaPI/blob/main/INSTALLATION.de.md).

set -euo pipefail

REPO="schwabix-1311/aquaPI"
INSTALL_DIR="${AQUAPI_INSTALL_DIR:-$HOME/aquaPI}"

echo "======================================================"
echo " aquaPi wird eingerichtet"
echo "======================================================"
echo

# --- Voraussetzungen prüfen ------------------------------------------------

if ! grep -qi debian /usr/lib/os-release 2>/dev/null; then
  echo "Hinweis: Dieses Skript ist für Raspberry Pi OS (bzw. andere"
  echo "Debian-basierte Systeme) gedacht. Ihr System scheint ein anderes zu sein."
  read -r -p "Trotzdem fortfahren? [j/N] " antwort
  case "$antwort" in
    [jJ]*) ;;
    *) echo "Abgebrochen."; exit 1 ;;
  esac
fi

for cmd in curl tar python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "FEHLER: '$cmd' wird benötigt, ist aber nicht installiert."
    echo "Bitte installieren Sie es (z.B. mit 'sudo apt-get install $cmd') und starten Sie dieses Skript erneut."
    exit 1
  fi
done

# --- Installationsverzeichnis wählen ---------------------------------------

if [ -d "$INSTALL_DIR" ]; then
  echo "Das Verzeichnis $INSTALL_DIR existiert bereits."
  read -r -p "Vorhandene Installation dort löschen und neu einrichten? [j/N] " antwort
  case "$antwort" in
    [jJ]*) rm -rf "$INSTALL_DIR" ;;
    *) echo "Abgebrochen. Es wurde nichts verändert."; exit 1 ;;
  esac
fi

echo
echo "Installationsverzeichnis: $INSTALL_DIR"

# --- Release herunterladen und entpacken -----------------------------------

echo
echo "Lade die aktuelle aquaPi-Version herunter ..."
TMP_ARCHIVE=$(mktemp)
trap 'rm -f "$TMP_ARCHIVE"' EXIT
curl -fsSL -o "$TMP_ARCHIVE" \
  "https://github.com/${REPO}/releases/latest/download/aquapi-latest.tar.gz"

mkdir -p "$INSTALL_DIR"
tar xzf "$TMP_ARCHIVE" -C "$INSTALL_DIR"
cd "$INSTALL_DIR"

# --- Python-Umgebung und Abhängigkeiten einrichten --------------------------

echo
echo "Richte Python-Umgebung und Abhängigkeiten ein (das kann einige Minuten dauern) ..."
echo "Falls dabei 'CR to continue' erscheint: einfach die Eingabetaste (Enter) drücken."
# shellcheck disable=SC1091
. ./init Prod

# --- TC420-LED-Controller vorbereiten (schadet nicht, falls nicht vorhanden) -

echo
echo "Bereite den optionalen TC420-LED-Controller vor (überspringen Sie das"
echo "einfach gedanklich, falls Sie keinen besitzen - es schadet nichts)."
sudo cp aquaPi/driver/tc420/etc/udev/rules.d/99-tc420.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo usermod -aG plugdev "$(whoami)"

# --- SSH-Verbindungen robuster gegen Netzwerkaussetzer machen ---------------
# Ein Pi läuft oft über WLAN; ohne diese Einstellung kann eine SSH-Sitzung
# nach einem kurzen Netzwerkaussetzer stundenlang unbemerkt offen hängen,
# statt zügig als abgebrochen erkannt zu werden.

if [ -f /etc/ssh/sshd_config ] && ! grep -q '^ClientAliveInterval' /etc/ssh/sshd_config; then
  echo
  echo "Richte SSH so ein, dass unterbrochene Verbindungen (z.B. nach einem"
  echo "WLAN-Aussetzer) innerhalb weniger Sekunden erkannt werden."
  printf '\n# von aquaPi install.sh ergaenzt: haengende SSH-Sitzungen zuegig erkennen\nClientAliveInterval 15\nClientAliveCountMax 3\n' \
    | sudo tee -a /etc/ssh/sshd_config >/dev/null
  sudo systemctl reload ssh 2>/dev/null || sudo systemctl reload sshd 2>/dev/null || true
fi

# --- Admin-Zugang anlegen -------------------------------------------------
# Muss vor dem ersten Start des Dienstes passieren: sonst legt aquaPi das
# Konto selbst an und schreibt das Passwort nur ins Systemprotokoll.
# Angezeigt wird es erst ganz am Ende, zusammen mit der Adresse.

ADMIN_INFO=$(./manage init-admin)

# --- Benachrichtigungen einrichten ------------------------------------------

echo
echo "======================================================"
echo " Benachrichtigungen einrichten"
echo "======================================================"
echo "Sie können jetzt E-Mail- oder Telegram-Benachrichtigungen einrichten"
echo "(z.B. für Alarme). Das können Sie auch jederzeit später nachholen mit:"
echo "  ./manage reconfig"
echo
./manage reconfig

# --- Als Dienst einrichten ---------------------------------------------------

echo
echo "======================================================"
echo " aquaPi als Dienst einrichten"
echo "======================================================"
echo "aquaPi wird jetzt als Systemdienst eingerichtet, damit es automatisch"
echo "startet - auch nach einem Neustart des Raspberry Pi."
echo
./manage service-unit --install --yes

# --- Fertig -------------------------------------------------------------

IP=$(hostname -I | awk '{print $1}')
echo
echo "======================================================"
echo " Fertig! aquaPi läuft jetzt."
echo "======================================================"
echo
echo " Öffnen Sie in Ihrem Webbrowser:"
echo "   http://${IP}:5000"
echo
echo "${ADMIN_INFO}" | sed 's/^/ /'
echo
echo " Eine ausführliche Anleitung finden Sie hier:"
echo "   https://github.com/${REPO}/blob/main/INSTALLATION.de.md"
echo "======================================================"
