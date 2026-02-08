import asyncio
import os
import logging
import aiohttp
from telethon import TelegramClient, events
from telethon.sessions import StringSession

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Из переменных окружения (для Railway)
API_ID = int(os.getenv('API_ID', '37160581'))
API_HASH = os.getenv('API_HASH', '227f2af5f922e552c0ac4dc31c2e20ad')
SESSION_STRING = os.getenv('SESSION_STRING', '1ApWapzMBuzHS5Wog54NKYyrnVKSWUMHvvRkIWC3zS00w_9nwCBECyc-Hz1QKi_CViAtjDbEK2NdnvKdjxwbGBxF8LA6jE9QvsrA8M0ZLYaMFFSfPdQbWEIGyXNB03WmtNi8yss8I94zlnVIGPjh2grC14WfZtGZ18tNjyMS4F4Y-_r36CRGXJv0XMzdVDDJxCz8Ha9vmoXvV6DnHICLm4CVZdnpahk7SUCa4XWuGx_-0Zm0I_IiXwR2IOV11cLK7J6dTPMjk8azM9P0culKvDnDKFD8GW3plOcLEH0NUyD42Bs1unraXV_lJlKSNE-JsmU7p0Fv70t_rS2kK86aIUDxAqAghoYk=')
N8N_WEBHOOK_URL = os.getenv('N8N_WEBHOOK_URL', 'https://antnomokonov.app.n8n.cloud/webhook/pattaya-realty')

# Чаты для мониторинга
MONITORED_CHATS = [
    'best_282',
    'PattayaNetworking',
    'pattaia_chatik',
    'russians_in_pattaya',
    'PattayaGirlsOnly',
    'russian_in_thailand',
    'pattaiay',
    'Pattayapar',
    'momclubpattaya'
]

# Ключевые слова
KEYWORDS_RENT = ['ищу', 'сниму', 'снять', 'аренд', 'нужн']
KEYWORDS_BUY = ['купить', 'куплю', 'покупк']
KEYWORDS_PROPERTY = ['квартир', 'кондо', 'студи', 'дом', 'вилл', 'комнат', 'спальн']

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

def check_keywords(text):
    text = text.lower()
    has_rent = any(k in text for k in KEYWORDS_RENT)
    has_buy = any(k in text for k in KEYWORDS_BUY)
    has_prop = any(k in text for k in KEYWORDS_PROPERTY)
    return has_prop and (has_rent or has_buy)

async def send_to_n8n(data):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(N8N_WEBHOOK_URL, json=data, timeout=30) as r:
                logger.info(f"Отправлено в n8n: {r.status}")
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")

@client.on(events.NewMessage(chats=MONITORED_CHATS))
async def handler(event):
    text = event.message.text or ''
    if len(text) < 20:
        return

    if not check_keywords(text):
        return

    chat = await event.get_chat()
    sender = await event.get_sender()

    data = {
        'text': text,
        'chat': {'title': getattr(chat, 'title', 'Unknown'), 'username': getattr(chat, 'username', None)},
        'sender': {
            'first_name': getattr(sender, 'first_name', None),
            'username': getattr(sender, 'username', None)
        },
        'message_link': f"https://t.me/{getattr(chat, 'username', '')}/{event.message.id}" if getattr(chat, 'username', None) else None
    }

    logger.info(f"НАЙДЕНА ЗАЯВКА в {chat.title}: {text[:50]}...")
    await send_to_n8n(data)

async def main():
    await client.start()
    logger.info("Монитор запущен!")
    logger.info(f"Слежу за чатами: {MONITORED_CHATS}")
    logger.info("Жду сообщения...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
