import time
import unittest
from unittest.mock import Mock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot import Bot, BotError


class BotTests(unittest.TestCase):
    def setUp(self):
        self.bot = Bot.__new__(Bot)
        self.bot.admin = 123
        self.bot.wait_name = False
        self.bot.confirm = {}
        self.bot.protect = False
        self.bot.telegram = Mock()
        self.bot.send = Mock()
        self.bot.api = Mock()
        self.bot.clients = Mock(return_value=[{'id': 1, 'name': 'Phone', 'enabled': True}])

    def message(self, user=123, chat=123, kind='private'):
        return {'message': {'from': {'id': user}, 'chat': {'id': chat, 'type': kind},
                            'text': '/start'}}

    def test_reject_other_user(self):
        self.bot.handle(self.message(user=999, chat=999))
        self.bot.send.assert_not_called()
        self.bot.api.assert_not_called()

    def test_reject_admin_in_group(self):
        self.bot.handle(self.message(chat=-55, kind='group'))
        self.bot.send.assert_not_called()

    def test_private_admin_menu(self):
        self.bot.handle(self.message())
        self.bot.send.assert_called_once()

    def test_callback_reject_other_user(self):
        update = self.message(user=999, chat=999)
        self.bot.handle({'callback_query': {'id': 'a', 'from': {'id': 999},
                         'message': update['message'], 'data': 'disable:1'}})
        self.bot.api.assert_not_called()

    def test_duplicate_name(self):
        self.bot.wait_name = True
        self.bot.message({'text': 'Phone'})
        self.bot.api.assert_not_called()

    def test_create_and_download(self):
        self.bot.wait_name = True
        self.bot.api.return_value.json.return_value = {'success': True, 'clientId': 2}
        self.bot.download = Mock()
        self.bot.detail = Mock()
        self.bot.message({'text': 'Laptop'})
        self.bot.api.assert_called_once_with('POST', 'client', {'name': 'Laptop', 'expiresAt': None})
        self.bot.download.assert_called_once_with('2')

    def test_create_timeout_never_retries(self):
        self.bot.wait_name = True
        self.bot.api.side_effect = BotError('timeout')
        with self.assertRaises(BotError):
            self.bot.message({'text': 'Laptop'})
        self.assertFalse(self.bot.wait_name)
        self.bot.api.assert_called_once()

    def test_delete_requires_confirmation(self):
        self.bot.callback({'id': 'x', 'data': 'delete:1'})
        self.bot.api.assert_not_called()
        self.assertEqual(len(self.bot.confirm), 1)

    def test_expired_confirmation(self):
        self.bot.confirm = {'token': ('1', time.monotonic() - 1)}
        self.bot.callback({'id': 'x', 'data': 'confirm:token'})
        self.bot.api.assert_not_called()

    def test_delete_confirmation_single_use(self):
        self.bot.confirm = {'token': ('1', time.monotonic() + 60)}
        self.bot.listing = Mock()
        self.bot.callback({'id': 'x', 'data': 'confirm:token'})
        self.bot.callback({'id': 'x', 'data': 'confirm:token'})
        self.bot.api.assert_called_once_with('DELETE', 'client/1')

    def test_download_and_qr_allow_forwarding(self):
        self.bot.api.return_value.content = b'[Interface]\nPrivateKey = test\n[Peer]\nPublicKey = test\n'
        self.bot.download('1')
        self.assertEqual(self.bot.telegram.call_count, 2)
        for call in self.bot.telegram.call_args_list:
            self.assertEqual(call.args[1]['protect_content'], 'false')

    def test_reject_invalid_config(self):
        self.bot.api.return_value.content = b'<html>Error</html>'
        with self.assertRaises(BotError):
            self.bot.download('1')
        self.bot.telegram.assert_not_called()


if __name__ == '__main__':
    unittest.main()
