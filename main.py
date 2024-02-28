import asyncio
import re
from random import choice
from uuid import uuid4

from sqlalchemy import select
from telebot import asyncio_filters
from telebot.async_telebot import AsyncTeleBot
from telebot.asyncio_handler_backends import State, StatesGroup
from telebot.asyncio_storage import StateMemoryStorage
from telebot.util import quick_markup, update_types
from telethon import TelegramClient
from telethon.errors import PhoneCodeInvalidError, SessionPasswordNeededError

from leads_bot.config import config
from leads_bot.database import Session
from leads_bot.models import (Account, ChatConfig, MemberLeftMessage,
                              WelcomeMessage)

bot = AsyncTeleBot(config['bot_token'], state_storage=StateMemoryStorage())


class MyStates(StatesGroup):
    phone_number = State()
    code = State()
    password = State()
    chat = State()
    welcome_message = State()
    member_left_message = State()
    edit_welcome_message = State()
    edit_member_left_message = State()


showing_chats_ids = False
user_id = None
chat_config_id = None
current_client = None
accounts = []
welcome_messages = []
member_left_messages = []
accounts_session = Session()
users = {}


@bot.message_handler(commands=['start', 'help'])
async def start(message):
    with Session() as session:
        accounts_usernames = [
            a.username for a in session.scalars(select(Account)).all()
        ]
        if (
            message.chat.username == config['username']
            or message.chat.username in accounts_usernames
        ):
            await bot.send_message(
                message.chat.id,
                'Escolha uma opção:',
                reply_markup=quick_markup(
                    {
                        'Adicionar Conta': {'callback_data': 'add_account'},
                        'Remover Conta': {'callback_data': 'remove_account'},
                        'Contas': {'callback_data': 'show_accounts'},
                        'Configurar Canal/Grupo': {
                            'callback_data': 'configure_chat'
                        },
                        'Remover do Canal/Grupo': {
                            'callback_data': 'remove_from_chat'
                        },
                        'Canais/Grupos': {'callback_data': 'show_chats'},
                        'Mostrar IDs': {'callback_data': 'show_chats_ids'},
                    },
                    row_width=1,
                ),
            )


@bot.callback_query_handler(func=lambda c: c.data == 'add_account')
async def add_account(callback_query):
    await bot.send_message(
        callback_query.message.chat.id,
        'Digite o número de telefone da conta nesse formato: +5511999999999',
    )
    await bot.set_state(
        callback_query.message.chat.id,
        MyStates.phone_number,
        callback_query.message.chat.id,
    )


@bot.message_handler(state=MyStates.phone_number)
async def on_phone_number(message):
    global current_client
    account_id = str(uuid4())
    try:
        client = await send_code_request(message, account_id)
        current_client = client
        async with bot.retrieve_data(
            message.from_user.id, message.chat.id
        ) as data:
            data['account_id'] = account_id
            data['phone_number'] = message.text
    except PhoneCodeInvalidError:
        await bot.send_message(
            message.chat.id,
            'Número de telefone inválido, conta não adicionada',
        )
        await start(message)
    await bot.send_message(
        message.chat.id, 'Digite o código enviado com esse formato: a79304'
    )
    await bot.set_state(message.chat.id, MyStates.code, message.chat.id)


async def send_code_request(message, account_id):
    client = TelegramClient(account_id, config['api_id'], config['api_hash'])
    await client.connect()
    if not (await client.is_user_authorized()):
        await client.send_code_request(message.text)
        return client
    else:
        await bot.send_message(message.chat.id, 'Conta adicionada')
        me = await client.get_me()
        with Session() as session:
            accounts_usernames = [
                a.username for a in session.scalars(select(Account)).all()
            ]
            username = (
                me.username
                or f'{me.first_name}{" " + me.last_name if me.last_name else ""}'
            )
            if username not in accounts_usernames:
                session.add(Account(account_id=account_id, username=username))
                session.commit()
        await start(message)


@bot.message_handler(state=MyStates.code)
async def on_code(message):
    global current_client
    async with bot.retrieve_data(
        message.from_user.id, message.chat.id
    ) as data:
        try:
            await sign_in_client(
                current_client,
                data['account_id'],
                data['phone_number'],
                message.text[1:],
            )
        except SessionPasswordNeededError:
            data['code'] = message.text
            await bot.send_message(message.chat.id, 'Digite a senha')
            await bot.set_state(
                message.chat.id, MyStates.password, message.chat.id
            )
        else:
            await bot.send_message(message.chat.id, 'Conta adicionada')
            await start(message)


@bot.message_handler(state=MyStates.password)
async def on_password(message):
    global current_client
    async with bot.retrieve_data(
        message.from_user.id, message.chat.id
    ) as data:
        try:
            await sign_in_client(
                current_client,
                data['account_id'],
                data['phone_number'],
                data['code'],
                message.text,
            )
        except SessionPasswordNeededError:
            await bot.send_message(
                message.chat.id, 'Senha inválida, conta não foi adicionada'
            )
        else:
            await bot.send_message(message.chat.id, 'Conta adicionada')
        await start(message)


async def sign_in_client(
    client, account_id, phone_number, code, password=None
):
    if password:
        await client.sign_in(password=password)
    else:
        await client.sign_in(phone_number, code)
    me = await client.get_me()
    with Session() as session:
        accounts_usernames = [
            a.username for a in session.scalars(select(Account)).all()
        ]
        username = (
            me.username
            or f'{me.first_name}{" " + me.last_name if me.last_name else ""}'
        )
        if username not in accounts_usernames:
            session.add(Account(account_id=account_id, username=username))
            session.commit()


@bot.callback_query_handler(func=lambda c: c.data == 'remove_account')
async def remove_account(callback_query):
    with Session() as session:
        reply_markup = {}
        for account in session.scalars(select(Account)).all():
            reply_markup[account.username] = {
                'callback_data': f'remove_account:{account.id}'
            }
        reply_markup['Voltar'] = {'callback_data': 'return_to_start'}
        await bot.send_message(
            callback_query.message.chat.id,
            'Escolha uma conta para remover:',
            reply_markup=quick_markup(reply_markup, row_width=1),
        )


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'remove_account:\d+', c.data))
)
async def remove_account_action(callback_query):
    with Session() as session:
        account_id = int(callback_query.data.split(':')[-1])
        account = session.get(Account, account_id)
        session.delete(account)
        session.commit()
        await bot.send_message(
            callback_query.message.chat.id, 'Conta Removida!'
        )
        await start(callback_query.message)


@bot.callback_query_handler(func=lambda c: c.data == 'show_accounts')
async def show_accounts(callback_query):
    with Session() as session:
        reply_markup = {}
        for account in session.scalars(select(Account)).all():
            reply_markup[account.username] = {
                'callback_data': f'show_account:{account.id}'
            }
        reply_markup['Voltar'] = {'callback_data': 'return_to_start'}
        await bot.send_message(
            callback_query.message.chat.id,
            'Contas:',
            reply_markup=quick_markup(reply_markup, row_width=1),
        )


@bot.callback_query_handler(func=lambda c: c.data == 'configure_chat')
async def configure_chat(callback_query):
    global accounts
    accounts = []
    with Session() as session:
        reply_markup = {}
        for account in session.scalars(select(Account)).all():
            reply_markup[account.username] = {
                'callback_data': f'on_account:{account.id}'
            }
        reply_markup['Finalizar'] = {'callback_data': 'on_account:0'}
        reply_markup['Voltar'] = {'callback_data': 'return_to_start'}
        await bot.send_message(
            callback_query.message.chat.id,
            'Escolha uma conta:',
            reply_markup=quick_markup(reply_markup, row_width=1),
        )


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'on_account:\d+', c.data))
)
async def on_account(callback_query):
    account_id = int(callback_query.data.split(':')[-1])
    reply_markup = {}
    if account_id:
        account = accounts_session.get(Account, account_id)
        accounts.append(account)
        for account in accounts_session.scalars(select(Account)).all():
            if account not in accounts:
                reply_markup[account.username] = {
                    'callback_data': f'on_account:{account.id}'
                }
    if account_id and reply_markup:
        reply_markup['Finalizar'] = {'callback_data': 'on_account:0'}
        reply_markup['Voltar'] = {'callback_data': 'return_to_start'}
        await bot.send_message(
            callback_query.message.chat.id,
            'Escolha uma conta:',
            reply_markup=quick_markup(reply_markup, row_width=1),
        )
    else:
        await bot.send_message(
            callback_query.message.chat.id,
            'Digite o ID ou Título do Canal/Grupo',
        )
        await bot.set_state(
            callback_query.message.chat.id,
            MyStates.chat,
            callback_query.message.chat.id,
        )


@bot.message_handler(state=MyStates.chat)
async def on_chat(message):
    global chat_config_id, welcome_messages, member_left_messages
    chat_config = ChatConfig(chat=message.text, accounts=accounts)
    accounts_session.add(chat_config)
    accounts_session.commit()
    accounts_session.flush()
    chat_config_id = chat_config.id
    welcome_messages = []
    member_left_messages = []
    await bot.send_message(
        message.chat.id,
        'Mande as mensagens que deseja enviar de boas-vindas, digite /pronto para finalizar',
    )
    await bot.set_state(
        message.chat.id, MyStates.welcome_message, message.chat.id
    )


@bot.message_handler(state=MyStates.welcome_message)
async def on_welcome_message(message):
    if message.text == '/pronto':
        await bot.send_message(
            message.chat.id,
            'Mande as mensagens que deseja enviar quando o membro sair do grupo, digite /pronto para finalizar',
        )
        await bot.set_state(
            message.chat.id, MyStates.member_left_message, message.chat.id
        )
    else:
        welcome_message = add_message_model(message, WelcomeMessage)
        welcome_messages.append(welcome_message)
        await bot.set_state(
            message.chat.id, MyStates.welcome_message, message.chat.id
        )


@bot.message_handler(state=MyStates.member_left_message)
async def on_member_left_message(message):
    if message.text == '/pronto':
        await bot.send_message(message.chat.id, 'Canal/Grupo Configurado!')
        await start(message)
    else:
        member_left_message = add_message_model(message, MemberLeftMessage)
        member_left_messages.append(member_left_message)
        await bot.set_state(
            message.chat.id, MyStates.member_left_message, message.chat.id
        )


def add_message_model(message, model_class):
    with Session() as session:
        message_model = model_class(
            chat_config_id=chat_config_id,
            photo_id=None
            if message.photo is None
            else message.photo[-1].file_id,
            audio_id=None
            if message.audio is None
            else message.audio[-1].file_id,
            document_id=None
            if message.document is None
            else message.document.file_id,
            video_id=None
            if message.video is None
            else message.video[-1].file_id,
            text=message.text,
            caption=message.caption,
        )
        session.add(message_model)
        session.commit()
        session.flush()
        return message_model


@bot.callback_query_handler(func=lambda c: c.data == 'remove_from_chat')
async def remove_from_chat(callback_query):
    with Session() as session:
        reply_markup = {}
        for chat_config in session.scalars(select(ChatConfig)).all():
            if re.findall(r'^-\d+$', chat_config.chat):
                reply_markup[bot.get_chat(int(chat_config.chat)).title] = {
                    'callback_data': f'remove_from_chat:{chat_config.id}'
                }
            else:
                reply_markup[chat_config.chat] = {
                    'callback_data': f'remove_from_chat:{chat_config.id}'
                }
        reply_markup['Voltar'] = {'callback_data': 'return_to_start'}
        await bot.send_message(
            callback_query.message.chat.id,
            'Selecione um Canal/Grupo para remover:',
            reply_markup=quick_markup(reply_markup, row_width=1),
        )


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'remove_from_chat:\d+', c.data))
)
async def remove_from_chat_action(callback_query):
    with Session() as session:
        chat_config_id = int(callback_query.data.split(':')[-1])
        chat_config = session.get(ChatConfig, chat_config_id)
        session.delete(chat_config)
        session.commit()
        await bot.send_message(
            callback_query.message.chat.id, 'Removido de Canal/Grupo!'
        )
        await start(callback_query.message)


@bot.callback_query_handler(func=lambda c: c.data == 'show_chats')
async def show_chats(callback_query):
    with Session() as session:
        reply_markup = {}
        for chat_config in session.scalars(select(ChatConfig)).all():
            if re.findall(r'^-\d+$', chat_config.chat):
                reply_markup[bot.get_chat(int(chat_config.chat)).title] = {
                    'callback_data': f'show_chat:{chat_config.id}'
                }
            else:
                reply_markup[chat_config.chat] = {
                    'callback_data': f'show_chat:{chat_config.id}'
                }
        reply_markup['Voltar'] = {'callback_data': 'return_to_start'}
        await bot.send_message(
            callback_query.message.chat.id,
            'Canais/Grupos:',
            reply_markup=quick_markup(reply_markup, row_width=1),
        )


@bot.callback_query_handler(func=lambda c: c.data == 'return_to_start')
async def return_to_start(callback_query):
    await start(callback_query.message)


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'show_chat:\d+', c.data))
)
async def show_chat_action(callback_query):
    with Session() as session:
        chat_config_id = int(callback_query.data.split(':')[-1])
        chat_config = session.get(ChatConfig, chat_config_id)
        await send_chat_options(callback_query.message, chat_config)


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'show_welcome_message:\d+', c.data))
)
async def show_welcome_message(callback_query):
    with Session() as session:
        chat_config_id = int(callback_query.data.split(':')[-1])
        chat_config = session.get(ChatConfig, chat_config_id)
        for welcome_message in chat_config.welcome_messages:
            await send_message_from_model(
                callback_query.message.chat.id, welcome_message
            )
        await send_chat_options(callback_query.message, chat_config)


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'show_member_left_message:\d+', c.data))
)
async def show_member_left_message(callback_query):
    with Session() as session:
        chat_config_id = int(callback_query.data.split(':')[-1])
        chat_config = session.get(ChatConfig, chat_config_id)
        for member_left_message in chat_config.member_left_messages:
            await send_message_from_model(
                callback_query.message.chat.id, member_left_message
            )
        await send_chat_options(callback_query.message, chat_config)


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'edit_welcome_message:\d+', c.data))
)
async def edit_welcome_message(callback_query):
    with Session() as session:
        chat_config_id = int(callback_query.data.split(':')[-1])
        chat_config = session.get(ChatConfig, chat_config_id)
        for message in chat_config.welcome_messages:
            session.delete(message)
            session.commit()
        await bot.send_message(
            callback_query.message.chat.id,
            'Mande as mensagens que deseja enviar de boas-vindas, digite /pronto para finalizar',
        )
        await bot.set_state(
            callback_query.message.chat.id,
            MyStates.edit_welcome_message,
            callback_query.message.chat.id,
        )


@bot.message_handler(state=MyStates.edit_welcome_message)
async def on_edit_welcome_message(message):
    with Session() as session:
        chat_config = session.get(ChatConfig, chat_config_id)
    if message.text == '/pronto':
        await send_chat_options(message, chat_config)
    else:
        welcome_message = add_message_model(message, WelcomeMessage)
        welcome_messages.append(welcome_message)
        await bot.set_state(
            message.chat.id, MyStates.edit_welcome_message, message.chat.id
        )


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'edit_member_left_message:\d+', c.data))
)
async def edit_member_left_message(callback_query):
    with Session() as session:
        chat_config_id = int(callback_query.data.split(':')[-1])
        chat_config = session.get(ChatConfig, chat_config_id)
        for message in chat_config.member_left_messages:
            session.delete(message)
            session.commit()
        await bot.send_message(
            callback_query.message.chat.id,
            'Mande as mensagens que deseja enviar quando o membro sair do grupo, digite /pronto para finalizar',
        )
        await bot.set_state(
            callback_query.message.chat.id,
            MyStates.edit_member_left_message,
            callback_query.message.chat.id,
        )


@bot.message_handler(state=MyStates.edit_member_left_message)
async def on_edit_member_left_message(message):
    with Session() as session:
        chat_config = session.get(ChatConfig, chat_config_id)
    if message.text == '/pronto':
        await send_chat_options(message, chat_config)
    else:
        member_left_message = add_message_model(message, MemberLeftMessage)
        member_left_messages.append(member_left_message)
        await bot.set_state(
            message.chat.id, MyStates.edit_member_left_message, message.chat.id
        )


async def send_message_from_model(chat, model):
    medias = {
        model.photo_id: bot.send_photo,
        model.audio_id: bot.send_audio,
        model.document_id: bot.send_document,
        model.video_id: bot.send_video,
    }
    if model.text:
        await bot.send_message(chat, model.text)
    else:
        for media_id, function in medias.items():
            if media_id:
                file_info = await bot.get_file(media_id)
                content = await bot.download_file(file_info.file_path)
                function(chat, content, model.caption)


async def send_message_from_model_with_client(
    user_id, model, account_id, chat=None
):
    global users
    medias = [
        model.photo_id,
        model.audio_id,
        model.document_id,
        model.video_id,
    ]
    if user_id in users:
        account_id = users[user_id]
    async with TelegramClient(
        account_id, config['api_id'], config['api_hash']
    ) as client:
        users[user_id] = account_id
        user = None
        member_in_chat = False
        if chat:
            while not member_in_chat:
                members = await client.get_participants(entity=chat)
                for member in members:
                    if member.id == user_id:
                        user = member
                        member_in_chat = True
                break
        if not chat or not member_in_chat:
            user = await client.get_entity(user_id)
        if user:
            if model.text:
                await client.send_message(user, model.text)
            else:
                for media_id in medias:
                    if media_id:
                        file_info = await bot.get_file(media_id)
                        content = await bot.download_file(file_info.file_path)
                        with open(file_info.file_path, 'wb') as f:
                            f.write(content)
                        await client.send_file(
                            user, file_info.file_path, caption=model.caption
                        )


async def send_chat_options(message, chat_config):
    global chat_config_id
    chat_config_id = chat_config.id
    if re.findall(r'^-\d+$l', chat_config.chat):
        chat_title = await bot.get_chat(int(chat_config.chat)).title
    else:
        chat_title = chat_config.chat
    await bot.send_message(
        message.chat.id,
        chat_title,
        reply_markup=quick_markup(
            {
                'Ver - Mensagem de Boas-Vindas': {
                    'callback_data': f'show_welcome_message:{chat_config.id}'
                },
                'Ver - Mensagem ao sair': {
                    'callback_data': f'show_member_left_message:{chat_config.id}'
                },
                'Editar - Mensagem de Boas-Vindas': {
                    'callback_data': f'edit_welcome_message:{chat_config.id}'
                },
                'Editar - Mensagem ao sair': {
                    'callback_data': f'edit_member_left_message:{chat_config.id}'
                },
                'Voltar': {'callback_data': 'show_chats'},
            },
            row_width=1,
        ),
    )


@bot.callback_query_handler(func=lambda c: c.data == 'show_chats_ids')
async def show_chats_ids(callback_query):
    global showing_chats_ids, user_id
    user_id = callback_query.message.chat.id
    await bot.send_message(
        callback_query.message.chat.id,
        'Vai começar a mostrar IDs de Canais/Grupos onde o Bot estiver adicionado, quando chegar mensagens, digite /parar_mostrar_ids para parar',
    )
    showing_chats_ids = True


@bot.message_handler(commands=['parar_mostrar_ids'])
async def stop_show_chats_ids(message):
    global showing_chats_ids
    await bot.send_message(
        message.chat.id, 'Parou de mostrar IDs de Canais/Grupos'
    )
    await start(message)
    showing_chats_ids = False


@bot.message_handler(content_types=['new_chat_members'])
async def send_welcome_message(message):
    with Session() as session:
        for chat_config in session.scalars(select(ChatConfig)).all():
            if chat_config.chat in [str(message.chat.id), message.chat.title]:
                account_id = choice(chat_config.accounts).account_id
                for welcome_message in chat_config.welcome_messages:
                    try:
                        await send_message_from_model_with_client(
                            message.from_user.id,
                            welcome_message,
                            account_id,
                            chat=message.chat.id,
                        )
                    except RuntimeError:
                        await asyncio.sleep(3)
                        await send_welcome_message(message)
                break


@bot.message_handler(content_types=['left_chat_member'])
async def send_member_left_message(message):
    with Session() as session:
        for chat_config in session.scalars(select(ChatConfig)).all():
            if chat_config.chat in [str(message.chat.id), message.chat.title]:
                account_id = choice(chat_config.accounts).account_id
                for member_left_message in chat_config.member_left_messages:
                    try:
                        await send_message_from_model_with_client(
                            message.from_user.id,
                            member_left_message,
                            account_id,
                        )
                    except RuntimeError:
                        await asyncio.sleep(3)
                        await send_member_left_message(message)
                break


@bot.chat_join_request_handler()
async def on_chat_join_request(request):
    with Session() as session:
        for chat_config in session.scalars(select(ChatConfig)).all():
            if chat_config.chat in [str(request.chat.id), request.chat.title]:
                account_id = choice(chat_config.accounts).account_id
                for welcome_message in chat_config.welcome_messages:
                    try:
                        await send_message_from_model_with_client(
                            request.user_chat_id,
                            welcome_message,
                            account_id,
                            chat=request.chat.id,
                        )
                    except RuntimeError:
                        await asyncio.sleep(3)
                        await on_chat_join_request(request)
                break


@bot.chat_member_handler()
async def send_channel_member_message(update):
    with Session() as session:
        for chat_config in session.scalars(select(ChatConfig)).all():
            if chat_config.chat in [str(update.chat.id), update.chat.title]:
                if update.new_chat_member.status == 'member':
                    account_id = choice(chat_config.accounts).account_id
                    for welcome_message in chat_config.welcome_messages:
                        try:
                            await send_message_from_model_with_client(
                                update.from_user.id,
                                welcome_message,
                                account_id,
                                chat=update.chat.id,
                            )
                        except RuntimeError:
                            await asyncio.sleep(3)
                            await send_channel_member_message(update)
                    break
                elif update.new_chat_member.status == 'left':
                    account_id = choice(chat_config.accounts).account_id
                    for (
                        member_left_message
                    ) in chat_config.member_left_messages:
                        try:
                            await send_message_from_model_with_client(
                                update.from_user.id,
                                member_left_message,
                                account_id,
                            )
                        except RuntimeError:
                            await asyncio.sleep(3)
                            await send_channel_member_message(update)
                    break


@bot.message_handler()
async def show_chat_id(message):
    if showing_chats_ids:
        await bot.send_message(
            user_id,
            f'{message.chat.title or message.chat.username} | {message.chat.id}',
        )


@bot.channel_post_handler()
async def show_channel_id(message):
    if showing_chats_ids:
        await bot.send_message(
            user_id, f'{message.chat.title} | {message.chat.id}'
        )


if __name__ == '__main__':
    bot.add_custom_filter(asyncio_filters.StateFilter(bot))
    asyncio.run(bot.polling(allowed_updates=update_types))
