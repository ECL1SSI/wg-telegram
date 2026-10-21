# WireGuard + wg-easy + Telegram : installation complète

[Русский](README.md) · [English](README.en.md) · **Français**

Guide complet pour **Ubuntu Server 24.04 LTS** : préparer le VPS → installer Docker →
installer wg-easy → connecter un téléphone → installer le bot Telegram → mettre à jour et dépanner.

Le bot crée des clients VPN, envoie des fichiers `.conf` et des codes QR, affiche les
appareils, active ou désactive leur accès, supprime les clients après confirmation et
affiche les compteurs de trafic actuels. Seul l'administrateur peut le gérer, en
conversation privée. Le transfert des configurations est autorisé par défaut.

> Si wg-easy fonctionne déjà, passez à **7. Bot Telegram**.
> Si le bot est également installé, consultez **10. Mises à jour**.
> L'installateur de ce projet installe le bot. Docker et wg-easy s'installent
> séparément avec les commandes ci-dessous. Il n'est pas nécessaire de réinstaller le VPS.
> L'installateur et l'interface du bot sont actuellement en russe ; ce guide explique leurs commandes en français.

## Sommaire

1. [Serveur et informations nécessaires](#1-serveur-et-informations-nécessaires)
2. [Connexion et préparation Ubuntu](#2-connexion-et-préparation-ubuntu)
3. [Installation de Docker](#3-installation-de-docker)
4. [Pare-feu et ports](#4-pare-feu-et-ports)
5. [Installation de wg-easy](#5-installation-de-wg-easy)
6. [Configuration du panneau et test du VPN](#6-configuration-du-panneau-et-test-du-vpn)
7. [Bot Telegram](#7-bot-telegram)
8. [Utilisation du bot](#8-utilisation-du-bot)
9. [Paramètres et transfert](#9-paramètres-et-transfert)
10. [Mises à jour](#10-mises-à-jour)
11. [Dépannage](#11-dépannage)
12. [Vérification et création des paquets](#12-vérification-et-création-des-paquets)

## 1. Serveur et informations nécessaires

Dans le panneau de votre hébergeur VPS, créez un serveur **Ubuntu Server 24.04 LTS,
amd64 ou arm64**. Il faut une IP publique, un accès SSH et un noyau prenant en charge
WireGuard. Le noyau Ubuntu standard convient à un VPS classique. Pour un VPS en
conteneur avec des restrictions, vérifiez la disponibilité de WireGuard auprès de l'hébergeur.

Le système d'exploitation s'installe depuis le panneau de l'hébergeur.
**Ne réinstallez pas le système** d'un serveur qui héberge déjà des bots, des sites ou des données.

| Information | Où la trouver |
| --- | --- |
| IP publique du serveur | Panneau de l'hébergeur VPS |
| Identifiant SSH et mot de passe ou clé | Panneau de l'hébergeur |
| Identifiant et mot de passe wg-easy | À créer dans l'assistant du panneau |
| Jeton du bot Telegram | @BotFather, commande `/newbot` |
| ID Telegram numérique de l'administrateur | Par exemple, @userinfobot |

Aucun nom de domaine n'est nécessaire pour cette méthode. Remplacez `IP_SERVEUR`
par l'adresse publique réelle du VPS, sans ajouter de chevrons.

## 2. Connexion et préparation Ubuntu

**Sur votre ordinateur**, ouvrez PowerShell sous Windows, Terminal sous macOS ou un terminal Linux :

```powershell
ssh root@IP_SERVEUR
```

À la première connexion, comparez l'empreinte de la clé SSH avec celle fournie par
l'hébergeur. Saisissez le mot de passe ; les caractères ne s'affichent pas. Si votre
compte est `ubuntu`, utilisez `ssh ubuntu@IP_SERVEUR`, puis exécutez `sudo -i`.

**Les commandes Linux suivantes s'exécutent sur le serveur en tant que root**,
sauf indication explicite « sur votre ordinateur ».

Vérifiez le système et installez les outils de base :

```bash
cat /etc/os-release
uname -m
apt update
apt install -y ca-certificates curl nano python3
```

Le résultat attendu est Ubuntu 24.04 et `x86_64` ou `aarch64`. Les mises à jour
courantes s'installent avec `apt upgrade`. Si une mise à jour du noyau exige un
redémarrage, planifiez-le et reconnectez-vous ensuite en SSH. Tenez compte des
autres services sur un serveur déjà utilisé.

## 3. Installation de Docker

Vérifiez d'abord si Docker est installé :

```bash
docker --version
docker compose version
```

Si les deux commandes fonctionnent, passez au test `hello-world` ci-dessous.
Le bloc suivant concerne une installation Ubuntu 24.04 neuve, sans Docker.
Si `docker.io`, `podman-docker` ou un `containerd` séparé est installé, consultez
d'abord la section sur les paquets incompatibles dans la
[documentation officielle Docker](https://docs.docker.com/engine/install/ubuntu/).

Ajoutez le dépôt officiel et installez Docker avec Compose :

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

N'ajoutez pas de source Docker en double si elle existe déjà dans `docker.list`
ou `docker.sources`.

Vérifiez l'installation :

```bash
docker run --rm hello-world
docker compose version
systemctl is-active docker
```

Résultat attendu : `Hello from Docker!`, une version de Compose et `active`.

## 4. Pare-feu et ports

Autorisez les ports suivants dans **le pare-feu du panneau de votre hébergeur VPS** :

| Port | Fonction | Accès |
| --- | --- | --- |
| TCP 22 ou votre port SSH personnalisé | SSH et tunnel SSH | Votre IP, si elle est fixe |
| UDP 51820 | VPN WireGuard | Appareils se connectant au VPN |
| TCP 51821 | Panneau web | Uniquement localhost sur le serveur ; ne pas exposer publiquement |

Le bot n'a pas besoin de port HTTP entrant : il reçoit les mises à jour Telegram
par des requêtes HTTPS sortantes. Le serveur doit pouvoir accéder en sortie au DNS
et en HTTPS aux dépôts Ubuntu, à Docker Registry, GitHub, PyPI et Telegram.

Vérifiez UFW :

```bash
ufw status
```

Si UFW est inactif, son activation n'est pas nécessaire pour ce guide. S'il est
actif, autorisez WireGuard :

```bash
ufw allow 51820/udp
```

Ne modifiez pas les règles SSH et n'activez pas UFW avant d'avoir autorisé votre port
SSH. Docker peut contourner les règles UFW habituelles pour les ports publiés des
conteneurs. Le panneau ci-dessous est donc lié spécifiquement à `127.0.0.1` ;
le pare-feu de l'hébergeur contrôle également l'accès au VPN.

## 5. Installation de wg-easy

Cette section concerne une nouvelle installation. Si `/opt/wg-easy` existe et que
le VPN fonctionne, n'écrasez pas sa configuration.

Créez le fichier Compose :

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

Le premier téléchargement de l'image peut prendre plusieurs minutes.
`health: starting` est normal juste après le démarrage ; l'état attendu ensuite
est `healthy`. Le port publié du panneau doit afficher **`127.0.0.1:51821`**,
et non `0.0.0.0:51821`.

Cette configuration s'appuie sur le [fichier Compose officiel wg-easy](https://github.com/wg-easy/wg-easy/blob/master/docker-compose.yml).
HTTP est autorisé pour la connexion locale ; l'accès distant au panneau passe par
un tunnel SSH chiffré. Les paramètres et les clés sont conservés dans le volume
`wg-easy_etc_wireguard`. N'exécutez pas `docker compose down -v` : cette commande
supprime le volume de données. Si ces sous-réseaux chevauchent des réseaux existants,
choisissez des sous-réseaux libres et adaptez les adresses du réseau et du conteneur
avant le démarrage.

## 6. Configuration du panneau et test du VPN

### Ouvrir un tunnel SSH

**Sur votre ordinateur, ouvrez une deuxième fenêtre PowerShell ou terminal :**

```powershell
ssh -N -L 51821:127.0.0.1:51821 root@IP_SERVEUR
```

Remplacez `root` si vous utilisez un autre compte SSH. Pour un port SSH personnalisé,
ajoutez `-p VOTRE_PORT`. Saisissez le mot de passe SSH et laissez la fenêtre ouverte.
L'absence de texte après la connexion est normale. Fermer la fenêtre ferme ce tunnel
vers le panneau ; le VPN et le bot continuent de fonctionner.

Ouvrez [http://localhost:51821](http://localhost:51821) **sur le même ordinateur**.
Sur téléphone, utilisez un client SSH avec redirection locale : port local `51821`
→ `127.0.0.1:51821` sur le VPS. Ouvrir `localhost` sur un autre appareil sans tunnel
ne suffit pas.

### Terminer l'assistant wg-easy

1. Créez un identifiant administrateur et un mot de passe fort pour le panneau.
   Ces informations sont distinctes de celles du compte SSH.
2. Indiquez **l'IP publique du VPS** comme adresse du serveur VPN, pas `localhost`
   ni `10.42.42.42`.
3. Conservez le port WireGuard `51820`.
4. Terminez l'assistant. Gardez les autres valeurs par défaut, sauf besoin spécifique
   concernant le DNS ou le routage.
5. Conservez l'identifiant et le mot de passe : le bot les utilisera pour l'API.

Le bot utilise l'API wg-easy avec Basic Auth. Selon la
[documentation de l'API](https://wg-easy.github.io/wg-easy/latest/advanced/api/),
cette méthode ne fonctionne pas lorsque la 2FA est activée. Cette configuration
utilise un panneau local et Basic Auth sans 2FA. Conserver la 2FA demanderait une
autre méthode d'intégration, non implémentée dans le bot actuel.

### Connecter le premier appareil

1. Créez un client dans le panneau, par exemple `Téléphone`.
2. Installez [WireGuard](https://www.wireguard.com/install/).
3. Ajoutez un tunnel en scannant le code QR. Si le panneau est ouvert sur le même
   téléphone, téléchargez le fichier `.conf` et importez-le dans WireGuard.
4. Activez le tunnel et vérifiez que les sites s'ouvrent et que votre IP externe change.
5. Avec un tunnel complet, l'IPv4 externe doit correspondre à l'IPv4 publique du VPS.

Si le VPN ne fonctionne pas, corrigez-le d'abord avec la section dépannage.
Le bot gère les clients ; il ne répare pas le réseau WireGuard. Créez un client
distinct pour chaque appareil.

## 7. Bot Telegram

### Créer le bot et obtenir votre ID

1. Ouvrez [@BotFather](https://t.me/BotFather) et envoyez `/newbot`.
2. Choisissez un nom et un identifiant disponible se terminant par `bot`.
3. Conservez le jeton reçu. Saisissez-le uniquement sur votre serveur.
4. Obtenez votre ID Telegram **numérique**, par exemple avec
   [@userinfobot](https://t.me/userinfobot). Un `@username` ne remplace pas cet ID.

Ne publiez pas le jeton ou le mot de passe du panneau dans un dépôt, un message
ou une capture d'écran.

### Lancer l'installateur sur le serveur

```bash
curl -fL https://raw.githubusercontent.com/ECL1SSI/wg-telegram/main/setup-wg-telegram.sh -o /tmp/setup-wg-telegram.sh
bash /tmp/setup-wg-telegram.sh
```

L'installateur demande les paramètres manquants. Les invites sont actuellement en russe :

| Invite | Valeur à saisir |
| --- | --- |
| Токен от BotFather | Le jeton complet du bot |
| Твой числовой Telegram ID | L'ID numérique de votre compte personnel |
| Логин веб-панели wg-easy | L'identifiant du panneau créé dans l'assistant |
| Пароль веб-панели wg-easy | Le mot de passe du panneau, pas celui de SSH |

Le jeton et le mot de passe sont masqués pendant la saisie. Saisissez chaque valeur
séparément et validez avec Entrée. Le fichier `/opt/wg-telegram/.env` existant est
réutilisé ; les champs déjà remplis ne sont pas demandés de nouveau.

L'installateur installe les dépendances Python dans un venv, vérifie `/api/client`
et le jeton Telegram, puis crée l'utilisateur système `wg-telegram` et le service
systemd. Le bot n'a ni privilèges root ni accès à Docker. L'installateur conserve
les clients VPN, Docker, les règles de pare-feu et la configuration wg-easy existants.

Vérifiez le démarrage :

```bash
systemctl status wg-telegram --no-pager -l
journalctl -u wg-telegram -n 30 --no-pager -o cat
```

Résultat attendu : `active (running)` et le message
`Бот запущен; API wg-easy доступен` (bot démarré ; API wg-easy disponible).
Ouvrez votre bot dans Telegram et envoyez **`/start`**.

## 8. Utilisation du bot

Les boutons du bot sont actuellement en russe :

| Bouton | Action |
| --- | --- |
| ➕ Создать подключение | Créer une connexion : saisir un nom, recevoir le `.conf` et le QR |
| 📋 Подключения | Afficher tous les clients wg-easy, y compris ceux créés dans le panneau |
| 📄 Конфиг + QR | Recevoir de nouveau la configuration et le QR de l'appareil choisi |
| ⏸ Отключить / ▶️ Включить | Désactiver ou réactiver l'accès du client |
| 🗑 Удалить | Supprimer un client après confirmation distincte |
| 📊 Статистика | Afficher le nombre d'appareils et les compteurs de trafic actuels |

`/start` et `/menu` ouvrent le menu ; `/cancel` annule la saisie du nom.
La confirmation de suppression est à usage unique et expire après deux minutes.
Seul l'ID défini dans `.env` peut gérer le bot en conversation privée.
La gestion est interdite dans les groupes, même pour l'administrateur.

Pour donner accès à un ami, créez un client distinct et transférez son `.conf` ou
son code QR. Il n'a pas besoin d'accéder au bot. Toute personne recevant cette
configuration peut utiliser le VPN ; ne la publiez pas dans un groupe public.
Les fichiers et codes QR contiennent une clé privée et sont envoyés dans une
conversation privée Telegram ordinaire.

## 9. Paramètres et transfert

Modifiez les paramètres sur le serveur :

```bash
nano /opt/wg-telegram/.env
```

Exemple de structure — **ne remplacez pas vos vrais identifiants par ces exemples** :

```dotenv
TELEGRAM_BOT_TOKEN=JETON_BOTFATHER
TELEGRAM_ADMIN_ID=ID_NUMERIQUE
WG_EASY_URL=http://127.0.0.1:51821
WG_EASY_USERNAME=IDENTIFIANT_PANNEAU
WG_EASY_PASSWORD="MOT_DE_PASSE_PANNEAU"
PROTECT_CONTENT=false
```

L'installateur écrit les valeurs avec l'échappement nécessaire. En modification
manuelle, respectez la syntaxe `.env` pour les caractères spéciaux ; n'exécutez
pas `source .env`.

- `PROTECT_CONTENT=false` : autoriser le transfert des configurations et codes QR.
- `PROTECT_CONTENT=true` : protéger les nouveaux messages contre le transfert.
- `WG_EASY_URL` : panneau HTTP local de ce serveur. Les URL distantes sont volontairement refusées.

Après modification :

```bash
systemctl restart wg-telegram
```

Demandez de nouveau **« Конфиг + QR »** pour appliquer le réglage aux nouveaux
fichiers envoyés. Les anciens messages conservent leur protection précédente.
Le bot lit directement `.env` ; ce fichier n'est pas envoyé dans Git.

## 10. Mises à jour

### Bot Telegram

Relancez les commandes d'installation :

```bash
curl -fL https://raw.githubusercontent.com/ECL1SSI/wg-telegram/main/setup-wg-telegram.sh -o /tmp/setup-wg-telegram.sh
bash /tmp/setup-wg-telegram.sh
```

Les paramètres `.env` sont conservés. Les anciens fichiers de code sont copiés dans
`*.backup-<timestamp>`. Envoyez ensuite `/start` et vérifiez la liste des clients.
Cette opération met à jour le bot, pas wg-easy.

### wg-easy au sein de la version majeure 15

Avant la mise à jour, sauvegardez la configuration et les données wg-easy avec les
outils de sauvegarde du VPS ou une sauvegarde cohérente séparée du volume Docker.
Puis exécutez :

```bash
cd /opt/wg-easy
docker compose pull
docker compose up -d
docker compose ps
docker compose logs --tail=50
```

L'image `:15` reçoit les mises à jour de cette version majeure. L'API wg-easy est
instable et peut changer. L'authentification et la liste des clients ont été
confirmées sur **15.4.0** dans cette installation ; testez les opérations réelles
de création, téléchargement et suppression après l'installation du bot.
Vérifiez la compatibilité avant de changer de version majeure.
N'utilisez pas `docker compose down -v` et ne supprimez pas le volume des clés.

## 11. Dépannage

### Le panneau ne s'ouvre pas

1. Vérifiez que le tunnel SSH est ouvert sur le même appareil que le navigateur.
2. Ouvrez `http://localhost:51821`, pas l'IP publique avec le port 51821.
3. Vérifiez le serveur :

```bash
cd /opt/wg-easy
docker compose ps
docker compose logs --tail=80
curl -I http://127.0.0.1:51821
```

Si le port local est occupé, utilisez
`ssh -N -L 51822:127.0.0.1:51821 root@IP_SERVEUR`, puis ouvrez `http://localhost:51822`.

### Le VPN est activé, mais les sites ne s'ouvrent pas

Vérifiez l'IP publique dans wg-easy, le port UDP 51820 chez l'hébergeur, l'état du
client et le dernier handshake. Sur le serveur :

```bash
docker exec wg-easy wg show
```

L'absence de handshake récent indique généralement un port UDP inaccessible,
une adresse ou un port incorrect, ou une configuration erronée. S'il existe un
handshake, vérifiez le DNS, le routage et les journaux. Après un changement d'adresse
du serveur, récupérez une nouvelle configuration et importez-la de nouveau.

### Le bot ne répond pas

```bash
systemctl status wg-telegram --no-pager -l
journalctl -u wg-telegram -n 80 --no-pager -o cat
```

Vérifiez l'ID numérique `TELEGRAM_ADMIN_ID`, la conversation privée et l'accès sortant
à `api.telegram.org`. Un jeton doit être utilisé par une seule instance active.
L'installateur utilise le long polling et ne nécessite pas de webhook HTTPS.

### wg-easy renvoie HTTP 401

Essayez de vous reconnecter au panneau avec les mêmes identifiants. Vérifiez
`WG_EASY_USERNAME` et `WG_EASY_PASSWORD` : il faut le compte du panneau, pas `root`.
Tenez compte de la restriction liée à la 2FA pour Basic Auth. Redémarrez
`wg-telegram` après correction de `.env`.

### Échec de création ou d'envoi d'une configuration

Après un délai d'attente dépassé, vérifiez d'abord la liste : le client peut avoir
été créé. Utilisez « Конфиг + QR » pour recevoir le fichier de nouveau.
Les créations ne sont pas relancées automatiquement. Les mises à jour Telegram
sont marquées comme traitées avant toute modification du VPN pour éviter les
doublons après un plantage. Une réponse peut être perdue ; vérifiez la liste avant de réessayer.

### Gestion des services

```bash
systemctl restart wg-telegram
systemctl stop wg-telegram
systemctl start wg-telegram
systemctl is-enabled wg-telegram
```

Docker et le bot utilisent systemd. Le conteneur wg-easy utilise
`restart: unless-stopped`. Après un arrêt manuel, lancez `cd /opt/wg-easy`,
puis `docker compose up -d`. Le trafic affiché correspond aux compteurs actuels
WireGuard, pas à des statistiques mensuelles persistantes ; ils peuvent être
réinitialisés au redémarrage de l'interface.

## 12. Vérification et création des paquets

Python s'exécute dans un venv ; aucun binaire exécutable distinct n'est nécessaire
pour Ubuntu. Dans le projet téléchargé ou cloné :

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q bot.py configure.py build.py
bash -n install.sh
python3 build.py
bash -n dist/setup-wg-telegram.sh
```

Le dossier `dist/` contient un installateur autonome et une archive des sources.
Si les sources sont déjà sur le VPS, utilisez `sudo bash install.sh`.

GitHub Actions lance les vérifications et enregistre l'artefact
`wg-telegram-installers` dans [Actions](https://github.com/ECL1SSI/wg-telegram/actions).
Ouvrez une exécution réussie **Check and package**, puis téléchargez l'artefact en
bas de page. Une connexion à GitHub peut être nécessaire pour le télécharger.

Les tests unitaires utilisent des API simulées. Les jetons, `.env`, configurations
VPN, images et venvs sont exclus de Git. Le paquet contient ce bot et son
installateur, pas le code source de wg-easy.

## Sources officielles

- [Docker Engine sur Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [Documentation wg-easy](https://wg-easy.github.io/wg-easy/latest/)
- [Fichier Compose officiel wg-easy](https://github.com/wg-easy/wg-easy/blob/master/docker-compose.yml)
- [HTTP local sans reverse proxy](https://wg-easy.github.io/wg-easy/latest/examples/tutorials/reverse-proxyless/)
- [API wg-easy et limites de l'authentification](https://wg-easy.github.io/wg-easy/latest/advanced/api/)
- [Clients WireGuard](https://www.wireguard.com/install/)
