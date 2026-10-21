#!/usr/bin/env bash
set -euo pipefail
umask 077
if [ "$(id -u)" -ne 0 ]; then
  echo 'Запусти: sudo bash install.sh'
  exit 1
fi
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
install_dir=/opt/wg-telegram
for file in bot.py configure.py requirements.txt wg-telegram.service; do
  test -f "$source_dir/$file" || { echo "Отсутствует $file"; exit 1; }
done
apt-get update
apt-get install -y python3-venv
if ! id wg-telegram >/dev/null 2>&1; then
  useradd --system --user-group --home-dir /var/lib/wg-telegram --shell /usr/sbin/nologin wg-telegram
fi
install -d -o root -g wg-telegram -m 0750 "$install_dir"
for file in bot.py configure.py requirements.txt; do
  if [ "$source_dir" != "$install_dir" ]; then
    if [ -f "$install_dir/$file" ]; then
      cp -p "$install_dir/$file" "$install_dir/$file.backup-$(date +%s)"
    fi
    install -o root -g root -m 0644 "$source_dir/$file" "$install_dir/$file"
  fi
done
umask 022
python3 -m venv "$install_dir/venv"
"$install_dir/venv/bin/pip" install -r "$install_dir/requirements.txt"
"$install_dir/venv/bin/python" -m py_compile "$install_dir/bot.py" "$install_dir/configure.py"
# Explicit terminal input: works even when the installer is invoked from a pipe.
"$install_dir/venv/bin/python" "$install_dir/configure.py" </dev/tty
chown root:wg-telegram "$install_dir/.env"
chmod 0640 "$install_dir/.env"
install -o root -g root -m 0644 "$source_dir/wg-telegram.service" /etc/systemd/system/wg-telegram.service
systemctl daemon-reload
systemctl enable wg-telegram
systemctl restart wg-telegram
systemctl status wg-telegram --no-pager -l || true
echo 'Установка завершена. Отправь своему боту /start.'
echo 'Логи: journalctl -u wg-telegram -n 50 --no-pager -o cat'
