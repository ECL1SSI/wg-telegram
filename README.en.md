# WireGuard + wg-easy + Telegram: setup from scratch

[Русский](README.md) · **English** · [Français](README.fr.md)

Complete guide for **Ubuntu Server 24.04 LTS**: prepare a VPS → install Docker →
install wg-easy → connect your phone → install the Telegram bot → update and troubleshoot.

The bot creates VPN clients, sends `.conf` files and QR codes, lists devices,
enables or disables access, deletes clients after confirmation, and displays current
traffic counters. Only the administrator can manage it, in a private chat.
Configuration forwarding is allowed by default.

> If wg-easy is already running, skip to **7. Telegram bot**.
> If the bot is installed too, use **10. Updates**.
> This project's installer installs the bot. Install Docker and wg-easy separately
> using the commands below. You do not need to reinstall an existing VPS.
> The current installer and bot interface are in Russian; this document explains their controls in English.

## Contents

1. [Server and required information](#1-server-and-required-information)
2. [Connect and prepare Ubuntu](#2-connect-and-prepare-ubuntu)
3. [Install Docker](#3-install-docker)
4. [Firewall and ports](#4-firewall-and-ports)
5. [Install wg-easy](#5-install-wg-easy)
6. [Set up the panel and test the VPN](#6-set-up-the-panel-and-test-the-vpn)
7. [Telegram bot](#7-telegram-bot)
8. [Using the bot](#8-using-the-bot)
9. [Settings and forwarding](#9-settings-and-forwarding)
10. [Updates](#10-updates)
11. [Troubleshooting](#11-troubleshooting)
12. [Check and package the project](#12-check-and-package-the-project)

## 1. Server and required information

In your VPS provider's dashboard, create a server with **Ubuntu Server 24.04 LTS,
amd64 or arm64**. You need a public IP, SSH access, and kernel support for WireGuard.
The standard Ubuntu kernel is suitable for a typical VPS. For restricted container
VPS hosting, ask your provider whether WireGuard is supported.

The provider's dashboard installs the operating system. **Do not reinstall the OS**
on a server already hosting bots, websites, or other data.

| Information | Where to get it |
| --- | --- |
| Server public IP | VPS provider dashboard |
| SSH username and password or key | Provider dashboard |
| wg-easy username and password | Create them in the initial panel wizard |
| Telegram bot token | @BotFather, `/newbot` |
| Administrator's numeric Telegram ID | For example, @userinfobot |

You do not need a domain for this setup. Replace `SERVER_IP` with your actual public
VPS address in the examples, without angle brackets.

## 2. Connect and prepare Ubuntu

**On your computer**, use Windows PowerShell, macOS Terminal, or a Linux terminal:

```powershell
ssh root@SERVER_IP
```

At the first connection, compare the SSH host key fingerprint with the provider's
information. Enter the password; its characters are not displayed. If your provider
uses the `ubuntu` account, connect with `ssh ubuntu@SERVER_IP`, then run `sudo -i`.

**Run the following Linux commands on the server as root**, unless explicitly
marked as commands for your computer.

Check the operating system and install basic tools:

```bash
cat /etc/os-release
uname -m
apt update
apt install -y ca-certificates curl nano python3
```

Expect Ubuntu 24.04 and `x86_64` or `aarch64`. You can install routine updates with
`apt upgrade`. If a kernel update requires a reboot, schedule it and reconnect over
SSH afterwards. Account for other services on an existing server.

## 3. Install Docker

First check whether Docker is already installed:

```bash
docker --version
docker compose version
```

If both commands work, skip to the `hello-world` check below. The next block is for
a fresh Ubuntu 24.04 installation without Docker. If `docker.io`, `podman-docker`,
or a separate `containerd` is installed, read the conflicting packages section of
the [official Docker guide](https://docs.docker.com/engine/install/ubuntu/) first.

Add the official repository and install Docker with Compose:

```bash
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
```

Do not add a duplicate Docker source if one already exists in `docker.list` or
`docker.sources`.

Verify the installation:

```bash
docker run --rm hello-world
docker compose version
systemctl is-active docker
```

Expect `Hello from Docker!`, a Compose version, and `active`.

## 4. Firewall and ports

Allow these ports in **your VPS provider's firewall**:

| Port | Purpose | Access |
| --- | --- | --- |
| TCP 22 or your custom SSH port | SSH and the SSH tunnel | Your IP, if it is static |
| UDP 51820 | WireGuard VPN | Devices that connect to the VPN |
| TCP 51821 | Web panel | Server localhost only; do not expose publicly |

The bot needs no inbound HTTP port: it receives Telegram updates through outbound
HTTPS requests. The server needs outbound DNS and HTTPS access to Ubuntu repositories,
Docker Registry, GitHub, PyPI, and Telegram.

Check UFW:

```bash
ufw status
```

If UFW is inactive, you do not need to enable it for this guide. If it is active,
allow WireGuard:

```bash
ufw allow 51820/udp
```

Do not change SSH rules or enable UFW before allowing your SSH port. Docker can
bypass normal UFW rules for published container ports. That is why the panel below
binds specifically to `127.0.0.1`; the provider firewall additionally controls VPN access.

## 5. Install wg-easy

This section is for a new installation. If `/opt/wg-easy` exists and your VPN works,
do not overwrite its configuration.

Create the Compose file:

```bash
mkdir -p /opt/wg-easy
cd /opt/wg-easy

cat > docker-compose.yml <<'YAML'
volumes:
  etc_wireguard:

services:
  wg-easy:
    image: ghcr.io/wg-easy/wg-easy:15
    container_name: wg-easy
    environment:
      INSECURE: "true"
    networks:
      wg:
        ipv4_address: 10.42.42.42
        ipv6_address: fdcc:ad94:bacf:61a3::2a
    volumes:
      - etc_wireguard:/etc/wireguard
      - /lib/modules:/lib/modules:ro
    ports:
      - "51820:51820/udp"
      - "127.0.0.1:51821:51821/tcp"
    restart: unless-stopped
    cap_add:
      - NET_ADMIN
      - SYS_MODULE
    sysctls:
      - net.ipv4.ip_forward=1
      - net.ipv4.conf.all.src_valid_mark=1
      - net.ipv6.conf.all.disable_ipv6=0
      - net.ipv6.conf.all.forwarding=1
      - net.ipv6.conf.default.forwarding=1

networks:
  wg:
    driver: bridge
    enable_ipv6: true
    ipam:
      driver: default
      config:
        - subnet: 10.42.42.0/24
        - subnet: fdcc:ad94:bacf:61a3::/64
YAML

docker compose config --quiet
docker compose up -d
docker compose ps
docker compose logs --tail=50
```

The initial image download can take several minutes. `health: starting` is normal
immediately after startup; later, expect `healthy`. The panel's published port must
show **`127.0.0.1:51821`**, rather than `0.0.0.0:51821`.

This is based on the [official wg-easy Compose configuration](https://github.com/wg-easy/wg-easy/blob/master/docker-compose.yml).
HTTP is allowed for the local connection; remote panel access travels through an
encrypted SSH tunnel. Settings and keys are stored in the `wg-easy_etc_wireguard`
volume. Do not run `docker compose down -v`: it deletes the data volume. If these
subnets overlap existing VPS networks, choose unused subnets and update both the
network and container addresses consistently before starting.

## 6. Set up the panel and test the VPN

### Open an SSH tunnel

**On your computer, open a second PowerShell or terminal window:**

```powershell
ssh -N -L 51821:127.0.0.1:51821 root@SERVER_IP
```

Replace `root` if you use another SSH account. Add `-p YOUR_PORT` for a custom SSH
port. Enter your SSH password and keep the window open. No further output is normal.
Closing it closes this panel tunnel; the VPN and bot keep running.

Open [http://localhost:51821](http://localhost:51821) **on the same computer**.
On a phone, use an SSH client with local port forwarding: local `51821` →
`127.0.0.1:51821` on the VPS. Opening `localhost` on another device without its own
tunnel will not work.

### Complete the wg-easy wizard

1. Create a panel administrator username and a strong password. These are separate
   credentials and do not have to match your SSH account.
2. Set the VPN server address to the **public VPS IP**, not `localhost` or `10.42.42.42`.
3. Keep the WireGuard port at `51820`.
4. Complete the wizard. Keep other defaults unless you have specific DNS or routing requirements.
5. Save the username and password; the bot needs them for API access.

The bot uses the wg-easy Basic Auth API. According to the [API documentation](https://wg-easy.github.io/wg-easy/latest/advanced/api/),
this method does not work with 2FA enabled. This setup uses a local panel and Basic
Auth without 2FA. Keeping 2FA would require a different integration method, which
the current bot does not implement.

### Connect the first device

1. Create a client in the panel, for example `Phone`.
2. Install [WireGuard](https://www.wireguard.com/install/).
3. Add a tunnel by scanning its QR code. If the panel is on the same phone,
   download the `.conf` file and import it into WireGuard.
4. Enable the tunnel and check that websites load and your external IP changes.
5. With a full tunnel, your external IPv4 should match the VPS public IPv4.

If the VPN does not work, resolve that first using the troubleshooting section.
The bot manages clients; it does not repair WireGuard networking. Create a separate
client for every device.

## 7. Telegram bot

### Create the bot and get your ID

1. Open [@BotFather](https://t.me/BotFather) and send `/newbot`.
2. Choose a name and an available username ending in `bot`.
3. Save the issued token. Enter it only on your server.
4. Find your **numeric** Telegram ID, for example with [@userinfobot](https://t.me/userinfobot).
   An `@username` is not a numeric ID.

Do not publish the token or panel password in repositories, messages, or screenshots.

### Run the installer on the server

```bash
curl -fL https://raw.githubusercontent.com/ECL1SSI/wg-telegram/main/setup-wg-telegram.sh -o /tmp/setup-wg-telegram.sh
bash /tmp/setup-wg-telegram.sh
```

The installer asks for missing settings. Its prompts are currently in Russian:

| Prompt | Enter |
| --- | --- |
| Токен от BotFather | The complete token for your bot |
| Твой числовой Telegram ID | Your personal account's numeric ID |
| Логин веб-панели wg-easy | The panel username created in the wizard |
| Пароль веб-панели wg-easy | The panel password, not the SSH password |

The token and password are hidden while typing. Enter each value separately and
press Enter. An existing `/opt/wg-telegram/.env` is reused; filled fields are not
requested again.

The installer installs Python dependencies in a venv, checks `/api/client` and the
Telegram token, and creates the `wg-telegram` system user and systemd service.
The bot has no root privileges or Docker access. The installer leaves existing VPN
clients, Docker, firewall rules, and wg-easy configuration intact.

Check startup:

```bash
systemctl status wg-telegram --no-pager -l
journalctl -u wg-telegram -n 30 --no-pager -o cat
```

Expect `active (running)` and the log message `Бот запущен; API wg-easy доступен`
(bot started; wg-easy API available). Open your bot in Telegram and send **`/start`**.

## 8. Using the bot

The bot currently displays Russian button labels:

| Button | Action |
| --- | --- |
| ➕ Создать подключение | Create connection: enter a name; receive a `.conf` and QR code |
| 📋 Подключения | Connections: list all wg-easy clients, including panel-created clients |
| 📄 Конфиг + QR | Config + QR: download the selected device's configuration again |
| ⏸ Отключить / ▶️ Включить | Disable / enable: pause or restore client access |
| 🗑 Удалить | Delete a client after separate confirmation |
| 📊 Статистика | Statistics: device count and current traffic counters |

`/start` and `/menu` open the menu. `/cancel` cancels name entry. Delete confirmations
are single-use and expire after two minutes. Only the ID in `.env` can manage the
bot in a private chat. Management is blocked in groups, even for the administrator.

To give a friend access, create a separate client and forward its `.conf` or QR code.
They do not need access to the bot itself. Anyone receiving that configuration can
use the VPN, so do not post it in a public chat. Files and QR codes contain a private
key and are sent through a regular Telegram private chat.

## 9. Settings and forwarding

Edit settings on the server:

```bash
nano /opt/wg-telegram/.env
```

Example structure — **do not replace real credentials with these placeholders**:

```dotenv
TELEGRAM_BOT_TOKEN=BOTFATHER_TOKEN
TELEGRAM_ADMIN_ID=NUMERIC_ID
WG_EASY_URL=http://127.0.0.1:51821
WG_EASY_USERNAME=PANEL_USERNAME
WG_EASY_PASSWORD="PANEL_PASSWORD"
PROTECT_CONTENT=false
```

The installer writes values with the required escaping. When editing manually,
follow `.env` syntax for special characters; do not run `source .env`.

- `PROTECT_CONTENT=false`: allow forwarding of configurations and QR codes.
- `PROTECT_CONTENT=true`: protect newly sent messages from forwarding.
- `WG_EASY_URL`: the local HTTP panel on this server. Remote URLs are intentionally rejected.

After editing:

```bash
systemctl restart wg-telegram
```

Request **«Конфиг + QR»** again to apply the forwarding setting to newly sent files.
Previously sent messages retain their previous protection. The bot reads `.env`
directly; the file is not uploaded to Git.

## 10. Updates

### Telegram bot

Run the installation commands again:

```bash
curl -fL https://raw.githubusercontent.com/ECL1SSI/wg-telegram/main/setup-wg-telegram.sh -o /tmp/setup-wg-telegram.sh
bash /tmp/setup-wg-telegram.sh
```

Settings in `.env` are retained. Previous code files are copied to
`*.backup-<timestamp>`. Afterwards, send `/start` and check the client list.
This updates the bot, not wg-easy.

### wg-easy within major version 15

Before updating, back up wg-easy configuration and data using your VPS backup system
or a separate consistent backup of the Docker volume. Then run:

```bash
cd /opt/wg-easy
docker compose pull
docker compose up -d
docker compose ps
docker compose logs --tail=50
```

The `:15` image receives updates within this major version. The wg-easy API is
unstable and may change. Authentication and client listing have been confirmed on
**15.4.0** in this setup; test live create, download, and delete operations after
installing the bot. Check compatibility before changing the major version.
Do not use `docker compose down -v` or remove the keys volume.

## 11. Troubleshooting

### The panel will not open

1. Make sure the SSH tunnel is open on the same device as the browser.
2. Open `http://localhost:51821`, not the public IP with port 51821.
3. Check the server:

```bash
cd /opt/wg-easy
docker compose ps
docker compose logs --tail=80
curl -I http://127.0.0.1:51821
```

If your local port is busy, use
`ssh -N -L 51822:127.0.0.1:51821 root@SERVER_IP`, then open `http://localhost:51822`.

### The VPN is enabled, but websites will not load

Check the public IP in wg-easy, UDP 51820 at the provider, client status, and the
latest handshake. On the server:

```bash
docker exec wg-easy wg show
```

No recent handshake usually indicates an unreachable UDP port, an incorrect endpoint,
or a configuration issue. If a handshake exists, check DNS, routing, and server logs.
After changing the server address, obtain an updated configuration and import it again.

### The bot does not respond

```bash
systemctl status wg-telegram --no-pager -l
journalctl -u wg-telegram -n 80 --no-pager -o cat
```

Check the numeric `TELEGRAM_ADMIN_ID`, private chat, and outbound connectivity to
`api.telegram.org`. Only one running bot instance should use a token. The installer
uses long polling and does not require an HTTPS webhook.

### wg-easy returns HTTP 401

Try signing in to the panel again with the same credentials. Check
`WG_EASY_USERNAME` and `WG_EASY_PASSWORD`; use the panel login, not `root`.
Remember the 2FA restriction for Basic Auth API. Restart `wg-telegram` after fixing `.env`.

### Creating a client or sending a configuration fails

After a timeout, check the list first: the client may have been created. Use
«Конфиг + QR» to request the file again. Creation is not automatically retried.
Telegram updates are marked as processed before VPN changes to prevent duplicate
creation after crashes. A crash can lose a response; check the client list before retrying.

### Service management

```bash
systemctl restart wg-telegram
systemctl stop wg-telegram
systemctl start wg-telegram
systemctl is-enabled wg-telegram
```

Docker and the bot use systemd. The wg-easy container uses `restart: unless-stopped`.
If stopped manually, run `cd /opt/wg-easy` and `docker compose up -d`.
Traffic figures are current WireGuard counters, not permanent monthly statistics;
they may reset when the interface restarts.

## 12. Check and package the project

Python runs from a venv; a separate executable binary is not needed for Ubuntu.
In the downloaded or cloned project:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q bot.py configure.py build.py
bash -n install.sh
python3 build.py
bash -n dist/setup-wg-telegram.sh
```

`dist/` contains a single-file installer and a source archive. With source files
already on the VPS, you can install with `sudo bash install.sh`.

GitHub Actions runs checks and saves the `wg-telegram-installers` artifact in
[Actions](https://github.com/ECL1SSI/wg-telegram/actions). Open a successful
**Check and package** run and download the artifact at the bottom. GitHub sign-in
may be required to download artifacts.

Unit tests use mocked APIs. Tokens, `.env`, VPN configurations, images, and venvs
are excluded from Git. The package contains this bot and installer, not wg-easy source code.

## Official references

- [Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [wg-easy documentation](https://wg-easy.github.io/wg-easy/latest/)
- [Official wg-easy Compose file](https://github.com/wg-easy/wg-easy/blob/master/docker-compose.yml)
- [Local HTTP without a reverse proxy](https://wg-easy.github.io/wg-easy/latest/examples/tutorials/reverse-proxyless/)
- [wg-easy API and authentication limitations](https://wg-easy.github.io/wg-easy/latest/advanced/api/)
- [WireGuard clients](https://www.wireguard.com/install/)
