#!/usr/bin/env python3
"""
Pattaya Real Estate Chat Monitor for Railway
"""

import asyncio
import json
import logging
import os

import aiohttp
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, User

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment variables
API_ID = int(os.environ.get('API_ID', 0))
API_HASH = os.environ.get('API_HASH', '')
SESSION_STRING = os.environ.get('SESSION_STRING', '')
N8N_WEBHOOK_URL = os.environ.get('N8N_WEBHOOK_URL', '')

# Chats to monitor
MONITORED_CHATS = [
    'pattayaa_test_bot',
    'pattaya_nedvizhimost',
    'pattaya_arenda',
    'pattaya_property',
    'pattayarent',
    'pattaya_chat',
    'pattayalife',
    'pattaya_ru',
    'jomtien_chat',
    'pattaya_market'
]

# Keywords
KEYWORDS_RENT = ['ищу аренд', 'сниму', 'снять', 'нужна аренда', 'хочу снять', 'ищу квартиру', 'ищу кондо', 'на месяц', 'долгосрок', 'looking for rent', 'want to rent', 'need apartment']
KEYWORDS_BUY = ['хочу купить', 'куплю', 'покупка', 'бюджет на покупку', 'инвестиц', 'want to buy', 'looking to buy']
KEYWORDS_PROPERTY = ['квартир', 'кондо', 'condo', 'студи', 'studio', 'дом', 'house', 'вилл', 'villa', 'комнат', 'room', 'апартамент', 'недвижимост', 'спальн', 'bedroom']

# Create client
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)


def contains_keywords(text):
    text_lower = text.lower()
    found_rent = any(kw in text_lower for kw in KEYWORDS_RENT)
    found_buy = any(kw in text_lower for kw in KEYWORDS_BUY)
    found_property = any(kw in text_lower for kw in KEYWORDS_PROPERTY)
    is_relevant = found_property and (found_rent or found_buy)
    return {
        'is_relevant': is_relevant,
        'has_rent_intent': found_rent,
        'has_buy_intent': found_buy
    }


async def send_to_n8n(data):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(N8N_WEBHOOK_URL, json=data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    logger.info(f"Sent to n8n: {data.get('message_id')}")
                else:
                    logger.error(f"n8n error: {resp.status}")
    except Exception as e:
        logger.error(f"Failed to send: {e}")


async def get_chat_info(chat):
    if isinstance(chat, Channel):
        return {'title': chat.title, 'username': chat.username, 'type': 'channel' if chat.broadcast else 'supergroup'}
    elif isinstance(chat, Chat):
        return {'title': chat.title, 'username': None, 'type': 'group'}
    return {'title': str(chat), 'username': None, 'type': 'unknown'}


async def get_sender_info(sender):
    if isinstance(sender, User):
        return {
            'first_name': sender.first_name,
            'last_name': sender.last_name,
            'username': sender.username
        }
    return {'first_name': None, 'last_name': None, 'username': None}


@client.on(events.NewMessage(chats=MONITORED_CHATS))
async def handle_message(event):
    try:
        text = event.message.text or ''
        if len(text) < 15:
            return

        kw = contains_keywords(text)
        if not kw['is_relevant']:
            return

        chat = await event.get_chat()
        sender = await event.get_sender()
        chat_info = await get_chat_info(chat)
        sender_info = await get_sender_info(sender)

        data = {
            'message_id': event.message.id,
            'text': text,
            'date': event.message.date.isoformat(),
            'chat': chat_info,
            'sender': sender_info,
            'keyword_analysis': kw,
            'message_link': f"https://t.me/{chat_info['username']}/{event.message.id}" if chat_info['username'] else None
        }

        logger.info(f"Lead found in {chat_info['title']}: {text[:50]}...")
        await send_to_n8n(data)

    except Exception as e:
        logger.error(f"Error: {e}")


async def main():
    logger.info("Starting Pattaya Monitor...")

    if not all([API_ID, API_HASH, SESSION_STRING, N8N_WEBHOOK_URL]):
        logger.error("Missing environment variables!")
        return

    await client.start()
    logger.info("Connected to Telegram")

    logger.info(f"Monitoring {len(MONITORED_CHATS)} chats")
    for chat_id in MONITORED_CHATS:
        try:
            entity = await client.get_entity(chat_id)
            info = await get_chat_info(entity)
            logger.info(f"  - {info['title']}")
        except Exception as e:
            logger.warning(f"  - Cannot find {chat_id}: {e}")

    logger.info("Monitor running...")
    await client.run_until_disconnected()


if __name__ == '__main__':
    asyncio.run(main())
