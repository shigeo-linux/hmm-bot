import json
import os

CONFIG_DIR = os.path.expanduser('~/.config/hmm-bot')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')
LOG_FILE = os.path.join(CONFIG_DIR, 'hmm-bot.log')

DEFAULTS = {
    'telegram_token': '',
    'telegram_chat_id': '',
    'signal_hour': 9,
    'last_run': '',
    'last_status': '',
    'last_signal': '',
    'last_confidence': '',
}


class Config:
    def __init__(self):
        self._data = dict(DEFAULTS)
        self._load()

    def _load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    self._data.update(json.load(f))
            except (json.JSONDecodeError, OSError):
                pass

    def save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self._data, f, indent=2)

    def get(self, key, fallback=None):
        return self._data.get(key, fallback if fallback is not None else DEFAULTS.get(key))

    def set(self, key, value):
        self._data[key] = value

    @property
    def telegram_token(self):
        return self._data.get('telegram_token', '')

    @property
    def telegram_chat_id(self):
        return self._data.get('telegram_chat_id', '')

    @property
    def signal_hour(self):
        return int(self._data.get('signal_hour', 9))
