import asyncio
from random import choice
from telethon.errors.rpcerrorlist import FloodWaitError, PeerFloodError

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
        for account in session.scalars(select(Account)).all():
            client = TelegramClient(
                account.account_id,
                config['api_id'],
                config['api_hash'],
            )
            await client.start()
            clients[account.account_id] = client
        while True:
            for message in session.scalars(select(Message)).all():
                clients_list = list(clients.values())
                client = choice(clients_list)
                clients_list.remove(client)
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
                if message.welcome_message_id:
                    print('Chat')
                    try:
                        chat = await client.get_entity(int(message.chat_id))
                    except:
                        print(f'Erro chat {message.chat_id}')
                        session.delete(message)
                        session.commit()
                        continue
                    members = await client.get_participants(entity=chat)
                    for member in members:
                        if member.id == int(message.user_id):
                            print('Member')
                            user = member
                            break
                else:
                    print('User')
                    while True:
                        if not user:
                            try:
                                user = await client.get_entity(int(message.user_id))
                                print(user)
                                break
                            except:
                                pass
                            try:
                                client = choice(clients_list)
                                clients_list.remove(client)
                            except IndexError:
                                session.delete(message)
                                session.commit()
                                print(message.user_id)
                                print('Saiu')
                                break
                try:
                    if user:
                        if model.text:
                            print('Sended message')
                            await client.send_message(user, model.text, parse_mode='md', link_preview=None)
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
                    session.delete(message)
                    session.commit()
                except Exception as error:
                    print(error)
                    continue


if __name__ == '__main__':
    asyncio.run(main())
