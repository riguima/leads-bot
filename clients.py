import asyncio
from random import choice

from sqlalchemy import select
from telethon import TelegramClient

from leads_bot.config import config
from leads_bot.database import Session
from leads_bot.models import (Account, MemberLeftMessage, Message,
                              WelcomeMessage)
from main import bot


async def main():
    clients = {}
    with Session() as session:
        while True:
            for account in session.scalars(select(Account)).all():
                if account.account_id not in clients:
                    client = TelegramClient(
                        account.account_id,
                        config['api_id'],
                        config['api_hash'],
                    )
                    await client.start()
                    clients[account.account_id] = client
            for message in session.scalars(select(Message)).all():
                client = choice(list(clients.values()))
                if message.welcome_message_id:
                    model = session.get(
                        WelcomeMessage, message.welcome_message_id
                    )
                else:
                    model = session.get(
                        MemberLeftMessage, message.member_left_message_id
                    )
                medias = [
                    model.photo_id,
                    model.audio_id,
                    model.document_id,
                    model.video_id,
                ]
                user = None
                try:
                    user = await client.get_entity(int(message.user_id))
                except:
                    chat = await client.get_entity(int(message.chat_id))
                    members = await client.get_participants(entity=chat)
                    for member in members:
                        if member.id == int(message.user_id):
                            user = member
                            break
                if user:
                    if model.text:
                        await client.send_message(user, model.text)
                    else:
                        for media_id in medias:
                            if media_id:
                                file_info = await bot.get_file(media_id)
                                content = await bot.download_file(
                                    file_info.file_path
                                )
                                with open(file_info.file_path, 'wb') as f:
                                    f.write(content)
                                await client.send_file(
                                    user,
                                    file_info.file_path,
                                    caption=model.caption,
                                )


if __name__ == '__main__':
    asyncio.run(main())
