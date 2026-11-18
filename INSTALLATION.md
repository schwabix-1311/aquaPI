# Installing aquaPi

*Deutsche Version: [INSTALLATION.de.md](INSTALLATION.de.md)*

This guide is written for aquarium keepers, not computer professionals. You
don't need any experience with Linux or programming - just a Raspberry Pi
and the willingness to copy a command into a terminal window.

## What you need

- A Raspberry Pi Zero 2 W, 3 or 4 (recommended) with the sensors and
  actuators for your aquarium connected.
- **Raspberry Pi 5:** not fully supported yet - outputs and inputs wired
  directly to GPIO pins (e.g. relays) and hardware PWM don't work there.
  Temperature sensors (1-Wire), I²C chips (ADS1115, PCA9685), the TC420,
  Shelly devices and notifications do.
- A microSD card with **Raspberry Pi OS "Bookworm", 64-bit** (recommended) -
  the "Lite" variant (without desktop) is enough. aquaPi is tested with
  this version; the installation does not work yet with the newer
  version "Trixie".
- **Absolute minimum:** a Raspberry Pi Zero W (or another older model)
  and/or Raspberry Pi OS "Bookworm" in the **32-bit** variant. aquaPi
  controls your tank just the same, but with limited charts: the history
  is kept in memory only, so the charts start empty after every restart.
  Older models such as the Zero W can only run the 32-bit variant anyway.
  The official [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
  writes the SD card within a few minutes. You'll find Bookworm there under
  "Raspberry Pi OS (other)", usually labelled "Legacy" - make sure to pick
  "64-bit".
- The Raspberry Pi must be connected to your home network (WiFi or network
  cable) and reachable via SSH. You can set this up while writing the SD
  card in the Raspberry Pi Imager under "Advanced options" (gear icon):
  enter your WiFi credentials and tick "Enable SSH".

## Open a terminal and connect to the Raspberry Pi

- **On Windows**: open "Command Prompt" or "PowerShell" (search in the
  Start menu).
- **On macOS**: open "Terminal" (Spotlight search, the magnifying glass at
  the top right, then type "Terminal").
- **On Linux**: you probably know how already.

Then connect to your Raspberry Pi (replace `<username>` and `<IP address>`
with your own values - you chose the username when preparing the SD card,
and you'll find the IP address in the device list of your WiFi router):

```
ssh <username>@<IP address>
```

The first time you connect to this device, you are asked whether you trust
it - confirm with "yes".

## Start the installation

Copy the following two lines into your terminal window and press Enter:

```
curl -fsSL -o install.sh https://github.com/schwabix-1311/aquaPI/releases/latest/download/install.sh
bash install.sh
```

The installer first asks for the language ("[d]eutsch / [e]nglish") -
press `e` for English. From here on it guides you through the rest of the
setup. It takes about 10-20 minutes in total (depending on your Raspberry Pi's
internet speed).

## What happens during the installation

- The installer downloads the current aquaPi version and sets up the
  software it needs. A message "CR to continue" may appear in between -
  just press Enter.
- If you own a **TC420 LED controller**, it is set up automatically - one
  of aquaPi's specialties compared to other solutions. If you don't have
  one, this step is skipped or simply has no effect.
- You are asked which **hardware interfaces** of the Raspberry Pi aquaPi
  should use: temperature sensors (1-Wire), pH measurement via an ADS1115
  (I²C) and hardware PWM for dimming. If in doubt, just press Enter. These
  interfaces only become active after a reboot - the installer offers one
  at the very end.
- If the Raspberry Pi is connected via WiFi, the installer sets up a
  **WiFi watchdog**: if the WiFi chip hangs (which happens with Raspberry
  Pis now and then), it reloads the WiFi driver, so the Pi is reachable
  again within a few minutes. aquaPi keeps controlling your tank without
  interruption meanwhile.
- You are asked whether you want to set up **notifications by email or
  Telegram** (e.g. for warnings when something is wrong). You can skip
  this and do it any time later, see "Set up notifications".
- Finally aquaPi is set up as a **service** that starts automatically -
  also after a reboot of your Raspberry Pi.

What the installer changes on the Raspberry Pi's system, so you can keep
track of it:

- aquaPi itself lives in `~/aquaPI`, the chart history (QuestDB) in
  `~/.questdb`.
- System services `aquapi` and `questdb`, with WiFi also
  `wifi-watchdog` (program in `/usr/local/sbin`).
- The enabled hardware interfaces (1-Wire and I²C via `raspi-config`,
  hardware PWM as a line in `/boot/firmware/config.txt`).
- A rule for the TC420 in `/etc/udev/rules.d/`, and your user becomes a
  member of the group `plugdev`.
- Two lines (`ClientAliveInterval`) in `/etc/ssh/sshd_config` and a
  `Host *` section (`ServerAliveInterval`) in `~/.ssh/config`, so an SSH
  connection dropped by a WiFi hiccup is detected quickly.

## Done - open aquaPi

At the end of the installation the installer shows a web address, e.g.:

```
http://192.168.1.42:5000
```

Open this address in a web browser on any device in your home network
(computer, tablet, smartphone) - that's where you'll find the aquaPi user
interface.

Right below it the installer shows your **admin login** (username `admin`
and a randomly generated password). Write the password down - it is shown
only this one time. Without logging in you can only look at the interface;
to set things up, log in at the top right, then change the password in the
"Users" menu.

## Set up notifications

You set up email and Telegram during the installation, or any time later
with this command (in the terminal, connected to the Raspberry Pi):

```
cd ~/aquaPI && ./manage reconfig
```

**Email:** you need the credentials of your mailbox (SMTP server, username,
password) - many providers require a separate "app password" instead of
your normal password.

**Telegram:** aquaPi writes through its own Telegram bot.

1. Create the bot: chat with **@BotFather** in Telegram, send `/newbot`
   and choose a name. BotFather replies with a **bot token** (e.g.
   `123456789:AA...`) - that's the first thing `./manage reconfig` asks
   for.
2. Choose the chat: `./manage reconfig` then shows your bot's name and
   asks you to send a message:
   - to a **group** (e.g. with your family): add the bot to the group and
     send `/aquapi@<your bot's name>` there,
   - or **to yourself**: open the bot in Telegram and send `aquaPi`.
3. Press Enter - aquaPi finds the chat and asks whether to use it.

If Telegram later converts a group into a "supergroup" (happens e.g. when
it gets many members), the group gets a new chat ID - then simply run
`./manage reconfig` again.

## Update aquaPi

For a new aquaPi version, simply run the installation again (the two lines
from "Start the installation"). The installer detects the existing
installation and asks - choose **[U] Update**. Your settings,
users, notifications and backups are kept; before updating, the installer
also creates a backup. Only [R] Reinstall deletes
everything.

## Help

If something doesn't work or you have questions, feel free to get in touch
(in English or German):

- [Discussions](https://github.com/schwabix-1311/aquaPI/discussions) for
  questions and ideas.
- [Issues](https://github.com/schwabix-1311/aquaPI/issues) for concrete
  problems/bugs.
