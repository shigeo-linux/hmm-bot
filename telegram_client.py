import requests


class TelegramError(Exception):
    pass


def send_message(token, chat_id, text):
    if not token or not chat_id:
        raise TelegramError("Telegram token or chat ID not configured.")

    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]

    for chunk in chunks:
        url = f'https://api.telegram.org/bot{token}/sendMessage'
        resp = requests.post(url, json={
            'chat_id': chat_id,
            'text': chunk,
            'parse_mode': 'HTML',
        }, timeout=30)

        if not resp.ok:
            try:
                detail = resp.json().get('description', resp.text)
            except Exception:
                detail = resp.text
            raise TelegramError(f"Telegram API error: {detail}")


def test_connection(token, chat_id):
    send_message(token, chat_id, '✅ <b>HMM Bot</b> connected successfully!')
