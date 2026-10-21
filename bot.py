import io
import json
import logging
import os
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlparse

import qrcode
import requests
from dotenv import dotenv_values

LOG = logging.getLogger('wg-telegram')
STATE = Path('/var/lib/wg-telegram/offset')


class BotError(Exception):
    pass


def keyboard(rows):
    return {'inline_keyboard': [[{'text': label, 'callback_data': data}
                                for label, data in row] for row in rows]}


class Bot:
    def __init__(self):
        cfg = dotenv_values('/opt/wg-telegram/.env', interpolate=False)
        for key in ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_ADMIN_ID',
                    'WG_EASY_USERNAME', 'WG_EASY_PASSWORD'):
            if not cfg.get(key):
                raise BotError('Не заполнено поле ' + key + ' в .env')
        self.admin = int(cfg['TELEGRAM_ADMIN_ID'])
        if self.admin <= 0:
            raise BotError('TELEGRAM_ADMIN_ID должен быть положительным числом')
        self.tg_url = 'https://api.telegram.org/bot' + cfg['TELEGRAM_BOT_TOKEN']
        self.base = cfg.get('WG_EASY_URL', 'http://127.0.0.1:51821').rstrip('/')
        url = urlparse(self.base)
        if url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise BotError('WG_EASY_URL должен указывать на локальную HTTP-панель')
        self.wg = requests.Session()
        self.wg.trust_env = False
        self.wg.auth = (cfg['WG_EASY_USERNAME'], cfg['WG_EASY_PASSWORD'])
        self.tg = requests.Session()
        self.tg.trust_env = False
        self.protect = str(cfg.get('PROTECT_CONTENT', 'false')).lower() == 'true'
        self.wait_name = False
        self.confirm = {}

    def api(self, method, path, payload=None):
        try:
            r = self.wg.request(method, self.base + '/api/' + path,
                                json=payload, timeout=(10, 25), allow_redirects=False)
        except requests.RequestException:
            raise BotError('Нет ответа от wg-easy. Если выполнялась операция, проверь список перед повтором.') from None
        if not r.ok or r.is_redirect:
            if r.status_code == 401:
                raise BotError('wg-easy отклонил логин/пароль (401). Проверь .env.')
            raise BotError('Ошибка wg-easy HTTP ' + str(r.status_code))
        return r

    def telegram(self, method, payload=None, files=None):
        try:
            r = self.tg.post(self.tg_url + '/' + method,
                             data=payload if files else None,
                             json=payload if not files else None,
                             files=files, timeout=(10, 65))
            data = r.json()
            if not data.get('ok'):
                raise BotError('Ошибка Telegram HTTP ' + str(r.status_code))
            return data['result']
        except (requests.RequestException, ValueError):
            raise BotError('Нет ответа от Telegram') from None

    def send(self, text, rows=None):
        payload = {'chat_id': self.admin, 'text': text}
        if rows:
            payload['reply_markup'] = keyboard(rows)
        return self.telegram('sendMessage', payload)

    def clients(self):
        try:
            data = self.api('GET', 'client').json()
        except ValueError:
            raise BotError('Неожиданный ответ wg-easy') from None
        if not isinstance(data, list):
            raise BotError('Неожиданный формат списка клиентов')
        return data

    @staticmethod
    def cid(client):
        return str(int(client.get('id', client.get('clientId'))))

    def find(self, cid):
        for client in self.clients():
            if self.cid(client) == cid:
                return client
        raise BotError('Подключение уже удалено. Обнови список.')

    def menu(self):
        self.wait_name = False
        self.send('Управление WireGuard', [
            [('➕ Создать подключение', 'new')],
            [('📋 Подключения', 'list:0'), ('📊 Статистика', 'stats')]])

    def listing(self, page):
        clients = self.clients()
        page = max(0, min(page, max(0, (len(clients) - 1) // 8)))
        rows = []
        for client in clients[page * 8:page * 8 + 8]:
            name = str(client.get('name', 'Без имени'))[:40]
            status = '🟢' if client.get('enabled') else '⏸'
            rows.append([(status + ' ' + name, 'view:' + self.cid(client))])
        nav = []
        if page > 0:
            nav.append(('←', 'list:' + str(page - 1)))
        if (page + 1) * 8 < len(clients):
            nav.append(('→', 'list:' + str(page + 1)))
        if nav:
            rows.append(nav)
        rows.append([('➕ Создать', 'new'), ('🏠 Меню', 'home')])
        self.send(f'Подключений: {len(clients)}. Страница {page + 1}.', rows)

    def detail(self, cid):
        client = self.find(cid)
        enabled = client.get('enabled', False)
        text = (str(client.get('name', cid)) + '\n'
                + ('Включено' if enabled else 'Отключено') + '\n'
                + 'IP: ' + str(client.get('ipv4Address', '—')) + '\n'
                + 'Последний handshake: ' + str(client.get('latestHandshakeAt') or 'ещё не было'))
        self.send(text, [
            [('📄 Конфиг + QR', 'download:' + cid)],
            [(('⏸ Отключить' if enabled else '▶️ Включить'),
              ('disable:' if enabled else 'enable:') + cid)],
            [('🗑 Удалить', 'delete:' + cid)],
            [('📋 Список', 'list:0'), ('🏠 Меню', 'home')]])

    def download(self, cid):
        client = self.find(cid)
        config = self.api('GET', f'client/{cid}/configuration').content
        if b'[Interface]' not in config or b'[Peer]' not in config:
            raise BotError('wg-easy вернул неожиданный формат конфигурации')
        name = re.sub(r'[^a-zA-Z0-9_-]', '-', str(client.get('name', ''))).strip('-')[:24]
        name = (name or 'client') + '-' + cid
        self.telegram('sendDocument',
                      {'chat_id': self.admin, 'protect_content': str(self.protect).lower(),
                       'caption': 'Конфигурация ' + str(client.get('name', cid))},
                      {'document': (name + '.conf', config, 'application/octet-stream')})
        try:
            image = qrcode.make(config.decode('utf-8'))
            buf = io.BytesIO()
            image.save(buf, format='PNG')
        except Exception:
            self.send('Файл отправлен. QR-код не удалось сформировать; импортируй .conf.')
            return
        self.telegram('sendPhoto',
                      {'chat_id': self.admin, 'protect_content': str(self.protect).lower(),
                       'caption': 'QR для WireGuard. Содержит приватный ключ.'},
                      {'photo': ('wireguard.png', buf.getvalue(), 'image/png')})

    def message(self, message):
        text = str(message.get('text', '')).strip()
        if text.split('@')[0] in ('/start', '/menu', '/cancel'):
            self.menu()
        elif self.wait_name and text:
            if len(text) > 48 or any(ord(ch) < 32 for ch in text) or text.startswith('/'):
                self.send('Название: от 1 до 48 символов, в одну строку. /cancel — отмена.')
                return
            if any(str(c.get('name')) == text for c in self.clients()):
                self.send('Такое имя уже существует. Введи другое или нажми /cancel.')
                return
            # Never automatically retry a create request after a timeout.
            self.wait_name = False
            result = self.api('POST', 'client', {'name': text, 'expiresAt': None}).json()
            cid = result.get('clientId')
            self.send('Подключение создано.')
            if cid is not None:
                cid = str(int(cid))
                self.download(cid)
                self.detail(cid)
            else:
                self.listing(0)
        else:
            self.menu()

    def callback(self, query):
        self.telegram('answerCallbackQuery', {'callback_query_id': query['id']})
        data = query.get('data', '')
        if data == 'home':
            self.menu()
            return
        if data == 'new':
            self.wait_name = True
            self.send('Введи имя устройства, например «Телефон-2». /cancel — отмена.',
                      [[('Отмена', 'home')]])
            return
        self.wait_name = False
        if data == 'stats':
            clients = self.clients()
            rx = sum(int(c.get('transferRx') or 0) for c in clients)
            tx = sum(int(c.get('transferTx') or 0) for c in clients)
            self.send(f'Устройств: {len(clients)}\nВключено: '
                      f'{sum(bool(c.get("enabled")) for c in clients)}\n'
                      f'Принято сервером: {rx / 1048576:.1f} МиБ\n'
                      f'Отправлено сервером: {tx / 1048576:.1f} МиБ\n'
                      'Трафик текущих счётчиков WireGuard; после перезапуска может обнулиться.',
                      [[('🏠 Меню', 'home')]])
            return
        if data.startswith('confirm:'):
            item = self.confirm.pop(data[8:], None)
            if not item or item[1] < time.monotonic():
                self.send('Подтверждение истекло. Открой устройство заново.')
                return
            self.api('DELETE', f'client/{item[0]}')
            self.send('Подключение удалено.')
            self.listing(0)
            return
        action, _, value = data.partition(':')
        if not value.isdigit():
            return
        if action == 'list':
            self.listing(int(value))
        elif action == 'view':
            self.detail(value)
        elif action == 'download':
            self.download(value)
        elif action in ('enable', 'disable'):
            self.api('POST', f'client/{value}/{action}')
            self.detail(value)
        elif action == 'delete':
            client = self.find(value)
            token = secrets.token_hex(8)
            self.confirm = {token: (value, time.monotonic() + 120)}
            self.send('Удалить «' + str(client.get('name', value)) + '»? '
                      'Старый конфиг перестанет работать.',
                      [[('Да, удалить', 'confirm:' + token), ('Отмена', 'view:' + value)]])

    def handle(self, update):
        query = update.get('callback_query')
        message = query.get('message', {}) if query else update.get('message', {})
        user = query.get('from', {}) if query else message.get('from', {})
        chat = message.get('chat', {})
        # Check both sender and private destination, including every callback.
        if user.get('id') != self.admin or chat.get('id') != self.admin or chat.get('type') != 'private':
            if query:
                self.telegram('answerCallbackQuery', {'callback_query_id': query['id'],
                                                     'text': 'Доступ закрыт'})
            return
        try:
            self.callback(query) if query else self.message(message)
        except BotError as error:
            self.send(str(error) + '\n/start — открыть меню.')
        except Exception as error:
            LOG.error('Ошибка обработки: %s', type(error).__name__)
            self.send('Не удалось завершить операцию. Проверь список перед повтором. /start')

    def run(self):
        self.telegram('deleteWebhook', {'drop_pending_updates': False})
        self.clients()
        offset = int(STATE.read_text()) if STATE.exists() else 0
        LOG.info('Бот запущен; API wg-easy доступен')
        while True:
            try:
                updates = self.telegram('getUpdates', {'offset': offset, 'timeout': 45,
                                                       'allowed_updates': ['message', 'callback_query']})
                for update in updates:
                    # Persist before mutations so a crash cannot replay a create/delete.
                    offset = update['update_id'] + 1
                    temp = STATE.with_suffix('.tmp')
                    temp.write_text(str(offset))
                    temp.replace(STATE)
                    self.handle(update)
            except BotError as error:
                LOG.warning('%s', error)
                time.sleep(5)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    try:
        Bot().run()
    except BotError as error:
        LOG.error('%s', error)
        raise SystemExit(1)
