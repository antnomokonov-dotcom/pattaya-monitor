#!/usr/bin/env python3
"""
Pattaya Realty Monitor v2.0
Облачная версия с динамической конфигурацией из Supabase
Хостинг: Railway
"""

import asyncio
import os
import logging
from datetime import datetime, timedelta

import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message
from supabase import create_client, Client as SupabaseClient

# Logging (только консоль для Railway)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Environment
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH', '')
SESSION_STRING = os.getenv('SESSION_STRING', '')
SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', '')
N8N_WEBHOOK = os.getenv('N8N_WEBHOOK', '')

# Supabase client
supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)

# Cache (обновляется каждые 5 минут)
CACHE = {
    'chats': [],
    'keywords': {'rent': [], 'buy': [], 'property': []},
    'settings': {},
    'last_update': None
}


async def refresh_cache():
    """Загрузить конфигурацию из Supabase"""
    try:
        # Загрузить активные чаты
        chats_resp = supabase.table('monitored_chats').select('username').eq('is_active', True).execute()
        CACHE['chats'] = [c['username'] for c in chats_resp.data]

        # Загрузить keywords
        kw_resp = supabase.table('keywords').select('word, category').eq('is_active', True).execute()
        CACHE['keywords'] = {'rent': [], 'buy': [], 'property': []}
        for kw in kw_resp.data:
            if kw['category'] in CACHE['keywords']:
                CACHE['keywords'][kw['category']].append(kw['word'].lower())

        # Загрузить настройки
        settings_resp = supabase.table('settings').select('key, value').execute()
        CACHE['settings'] = {s['key']: s['value'] for s in settings_resp.data}

        CACHE['last_update'] = datetime.now()
        logger.info(f"Cache refreshed: {len(CACHE['chats'])} chats, {sum(len(v) for v in CACHE['keywords'].values())} keywords")

    except Exception as e:
        logger.error(f"Failed to refresh cache: {e}")


async def cache_refresh_loop():
    """Фоновое обновление кэша каждые 5 минут"""
    while True:
        await refresh_cache()
        await asyncio.sleep(300)  # 5 минут


def contains_keywords(text: str) -> dict:
    """Проверка на ключевые слова"""
    text_lower = text.lower()

    found_rent = any(kw in text_lower for kw in CACHE['keywords']['rent'])
    found_buy = any(kw in text_lower for kw in CACHE['keywords']['buy'])
    found_property = any(kw in text_lower for kw in CACHE['keywords']['property'])

    is_relevant = found_property and (found_rent or found_buy)

    return {
        'is_relevant': is_relevant,
        'has_rent': found_rent,
        'has_buy': found_buy,
        'has_property': found_property
    }


async def is_duplicate(chat_username: str, message_id: int) -> bool:
    """Проверка на дубликат"""
    try:
        result = supabase.table('leads').select('id').eq('chat_username', chat_username).eq('message_id', message_id).execute()
        return len(result.data) > 0
    except Exception as e:
        logger.error(f"Duplicate check failed: {e}")
        return False


async def send_to_n8n(data: dict):
    """Отправка в n8n webhook"""
    if not N8N_WEBHOOK or N8N_WEBHOOK == 'placeholder':
        logger.warning("N8N_WEBHOOK not set, skipping send")
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(N8N_WEBHOOK, json=data, timeout=30) as resp:
                if resp.status == 200:
                    logger.info(f"Sent to n8n: {data.get('message_id')}")
                else:
                    logger.error(f"n8n error: {resp.status}")
    except Exception as e:
        logger.error(f"Failed to send to n8n: {e}")


# Pyrogram client
app = Client(
    "pattaya_monitor",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)


@app.on_message(filters.text)
async def handle_message(client: Client, message: Message):
    """Обработка входящих сообщений"""
    try:
        # Проверить, что чат мониторится
        chat = message.chat
        chat_username = chat.username

        if not chat_username or chat_username not in CACHE['chats']:
            return

        text = message.text or ""
        min_length = int(CACHE['settings'].get('min_message_length', 20))

        if len(text) < min_length:
            return

        # Проверка keywords
        kw_check = contains_keywords(text)
        if not kw_check['is_relevant']:
            return

        # Проверка дубликата
        if await is_duplicate(chat_username, message.id):
            logger.info(f"Duplicate skipped: {chat_username}/{message.id}")
            return

        # Собрать данные
        sender = message.from_user
        data = {
            'message_id': message.id,
            'text': text,
            'date': message.date.isoformat(),
            'chat': {
                'username': chat_username,
                'title': chat.title or chat_username
            },
            'sender': {
                'id': sender.id if sender else None,
                'first_name': sender.first_name if sender else None,
                'last_name': sender.last_name if sender else None,
                'username': sender.username if sender else None
            },
            'keyword_analysis': kw_check,
            'message_link': f"https://t.me/{chat_username}/{message.id}"
        }

        logger.info(f"Lead found in {chat_username}: {text[:50]}...")
        await send_to_n8n(data)

        # Обновить счётчик (если функция существует)
        try:
            supabase.rpc('increment_chat_leads', {'chat_name': chat_username}).execute()
        except:
            pass  # Функция может не существовать

    except Exception as e:
        logger.error(f"Error processing message: {e}")


async def main():
    logger.info("Starting Pattaya Monitor v2.0...")
    logger.info(f"API_ID: {API_ID}")
    logger.info(f"SUPABASE_URL: {SUPABASE_URL[:30]}...")
    logger.info(f"N8N_WEBHOOK: {N8N_WEBHOOK[:30] if N8N_WEBHOOK else 'NOT SET'}...")

    # Первичная загрузка кэша
    await refresh_cache()

    if not CACHE['chats']:
        logger.warning("No chats to monitor! Add chats to Supabase.")

    # Запустить фоновое обновление
    asyncio.create_task(cache_refresh_loop())

    # Подключиться к Telegram
    await app.start()
    logger.info(f"Connected to Telegram! Monitoring {len(CACHE['chats'])} chats")

    # Вывести список чатов
    for chat_id in CACHE['chats']:
        logger.info(f"  - @{chat_id}")

    # Держать соединение
    await asyncio.Event().wait()


if __name__ == '__main__':
    app.run(main())
