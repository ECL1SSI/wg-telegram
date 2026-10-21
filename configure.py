"""Interactive local setup; never prints credentials or sends them elsewhere."""
import getpass
import json
import os
import re
from pathlib import Path

from dotenv import dotenv_values
from bot import Bot


def configure():
    path = Path('/opt/wg-telegram/.env')
    cfg = dict(dotenv_values(path, interpolate=False)) if path.exists() else {}
    fields = [
        ('TELEGRAM_BOT_TOKEN', 'Токен от BotFather', True),
        ('TELEGRAM_ADMIN_ID', 'Твой числовой Telegram ID', False),
        ('WG_EASY_USERNAME', 'Логин веб-панели wg-easy', False),
        ('WG_EASY_PASSWORD', 'Пароль веб-панели wg-easy', True),
    ]
    for key, label, hidden in fields:
        if not cfg.get(key):
            value = getpass.getpass(label + ': ') if hidden else input(label + ': ').strip()
            if not value:
                raise SystemExit('Пустое значение: ' + key)
            cfg[key] = value
    if not re.fullmatch(r'\d+:[A-Za-z0-9_-]+', cfg['TELEGRAM_BOT_TOKEN']):
        raise SystemExit('Некорректный формат токена Telegram')
    if not cfg['TELEGRAM_ADMIN_ID'].isdigit() or int(cfg['TELEGRAM_ADMIN_ID']) <= 0:
        raise SystemExit('Telegram ID должен быть положительным числом')
    cfg.setdefault('WG_EASY_URL', 'http://127.0.0.1:51821')
    cfg.setdefault('PROTECT_CONTENT', 'false')
    # Keep comments and all unrelated existing settings untouched.
    lines = path.read_text().splitlines() if path.exists() else []
    lines = [line for line in lines if line.split('=', 1)[0] not in cfg]
    for key, value in cfg.items():
        if value is not None:
            lines.append(key + '=' + json.dumps(value, ensure_ascii=False))
    temp = path.with_suffix('.env.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as out:
        out.write('\n'.join(lines) + '\n')
    os.chmod(temp, 0o600)
    temp.replace(path)
    bot = Bot()
    clients = bot.clients()
    identity = bot.telegram('getMe')
    print('API wg-easy работает. Подключений:', len(clients))
    print('Telegram-бот:', '@' + identity.get('username', ''))


if __name__ == '__main__':
    from bot import BotError
    try:
        configure()
    except BotError as error:
        raise SystemExit(str(error))
