import asyncio
import re
from uuid import uuid4

from sqlalchemy import select
from telebot import TeleBot
from telebot.util import quick_markup, update_types
from telethon import TelegramClient
from telethon.errors import PhoneCodeInvalidError, SessionPasswordNeededError

from leads_bot.config import config
from leads_bot.database import Session
from leads_bot.models import (Account, ChatConfig, MemberLeftMessage,
                              WelcomeMessage)

bot = TeleBot(config['bot_token'])

showing_chats_ids = False
user_id = None
chat_config_id = None
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
welcome_messages = []
member_left_messages = []


@bot.message_handler(commands=['start', 'help'])
def start(message):
    with Session() as session:
        accounts_usernames = [
            a.username for a in session.scalars(select(Account)).all()
        ]
        if (
            message.chat.username == config['username']
            or message.chat.username in accounts_usernames
        ):
            bot.send_message(
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
def add_account(callback_query):
    bot.send_message(
        callback_query.message.chat.id,
        'Digite o número de telefone da conta nesse formato: +5511999999999',
    )
    bot.register_next_step_handler(callback_query.message, on_phone_number)


def on_phone_number(message):
    account_id = str(uuid4())
    try:
        client = loop.run_until_complete(
            send_code_request(message, account_id)
        )
    except PhoneCodeInvalidError:
        bot.send_message(
            message.chat.id,
            'Número de telefone inválido, conta não adicionada',
        )
        start(message)
    bot.send_message(
        message.chat.id, 'Digite o código enviado com esse formato: a79304'
    )
    bot.register_next_step_handler(
        message, lambda m: on_code(m, client, account_id, message.text)
    )


async def send_code_request(message, account_id):
    client = TelegramClient(account_id, config['api_id'], config['api_hash'])
    await client.connect()
    if not (await client.is_user_authorized()):
        await client.send_code_request(message.text)
        return client
    else:
        bot.send_message(message.chat.id, 'Conta adicionada')
        me = await client.get_me()
        with Session() as session:
            accounts_usernames = [
                a.username for a in session.scalars(select(Account)).all()
            ]
            if me.username not in accounts_usernames:
                session.add(
                    Account(account_id=account_id, username=me.username)
                )
                session.commit()
        start(message)


def on_code(message, client, account_id, phone_number):
    try:
        loop.run_until_complete(
            sign_in_client(client, account_id, phone_number, message.text[1:])
        )
    except SessionPasswordNeededError:
        bot.send_message(message.chat.id, 'Digite a senha')
        bot.register_next_step_handler(
            message,
            lambda m: on_password(
                m, client, account_id, phone_number, message.text
            ),
        )
    else:
        bot.send_message(message.chat.id, 'Conta adicionada')
        start(message)


def on_password(message, client, account_id, phone_number, code):
    try:
        loop.run_until_complete(
            sign_in_client(
                client, account_id, phone_number, code, message.text
            )
        )
    except SessionPasswordNeededError:
        bot.send_message(
            message.chat.id, 'Senha inválida, conta não foi adicionada'
        )
    else:
        bot.send_message(message.chat.id, 'Conta adicionada')
    start(message)


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
        if me.username not in accounts_usernames:
            session.add(Account(account_id=account_id, username=me.username))
            session.commit()


@bot.callback_query_handler(func=lambda c: c.data == 'remove_account')
def remove_account(callback_query):
    with Session() as session:
        reply_markup = {}
        for account in session.scalars(select(Account)).all():
            reply_markup[account.username] = {
                'callback_data': f'remove_account:{account.id}'
            }
        reply_markup['Voltar'] = {'callback_data': 'return_to_start'}
        bot.send_message(
            callback_query.message.chat.id,
            'Escolha uma conta para remover:',
            reply_markup=quick_markup(reply_markup, row_width=1),
        )


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'remove_account:\d+', c.data))
)
def remove_account_action(callback_query):
    with Session() as session:
        account_id = int(callback_query.data.split(':')[-1])
        account = session.get(Account, account_id)
        session.delete(account)
        session.commit()
        bot.send_message(callback_query.message.chat.id, 'Conta Removida!')
        start(callback_query.message)


@bot.callback_query_handler(func=lambda c: c.data == 'show_accounts')
def show_accounts(callback_query):
    with Session() as session:
        reply_markup = {}
        for account in session.scalars(select(Account)).all():
            reply_markup[account.username] = {
                'callback_data': f'show_account:{account.id}'
            }
        reply_markup['Voltar'] = {'callback_data': 'return_to_start'}
        bot.send_message(
            callback_query.message.chat.id,
            'Contas:',
            reply_markup=quick_markup(reply_markup, row_width=1),
        )


@bot.callback_query_handler(func=lambda c: c.data == 'add_chat')
def add_chat(callback_query):
    bot.send_message(
        callback_query.message.chat.id, 'Digite o ID do Canal/Grupo'
    )
    bot.register_next_step_handler(callback_query.message, on_chat_id)


def on_chat_id(message):
    global chat_config_id, welcome_messages, member_left_messages
    with Session() as session:
        chat_config = ChatConfig(chat_id=message.text)
        session.add(chat_config)
        session.commit()
        session.flush()
        chat_config_id = chat_config.id
    welcome_messages = []
    member_left_messages = []
    bot.send_message(
        message.chat.id,
        'Mande as mensagens que deseja enviar de boas-vindas, digite /pronto para finalizar',
    )
    bot.register_next_step_handler(message, on_welcome_message)


def on_welcome_message(message):
    if message.text == '/pronto':
        bot.send_message(
            message.chat.id,
            'Mande as mensagens que deseja enviar quando o membro sair do grupo, digite /pronto para finalizar',
        )
        bot.register_next_step_handler(message, on_member_left_message)
    else:
        welcome_message = add_message_model(message, WelcomeMessage)
        welcome_messages.append(welcome_message)
        bot.register_next_step_handler(message, on_welcome_message)


def on_member_left_message(message):
    if message.text == '/pronto':
        bot.send_message(message.chat.id, 'Canal/Grupo Configurado!')
        start(message)
    else:
        member_left_message = add_message_model(message, MemberLeftMessage)
        member_left_messages.append(member_left_message)
        bot.register_next_step_handler(message, on_member_left_message)


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
def remove_from_chat(callback_query):
    with Session() as session:
        reply_markup = {}
        for chat_config in session.scalars(select(ChatConfig)).all():
            reply_markup[bot.get_chat(int(chat_config.chat_id)).title] = {
                'callback_data': f'remove_from_chat:{chat_config.id}'
            }
        reply_markup['Voltar'] = {'callback_data': 'return_to_start'}
        bot.send_message(
            callback_query.message.chat.id,
            'Selecione um Canal/Grupo para remover:',
            reply_markup=quick_markup(reply_markup, row_width=1),
        )


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'remove_from_chat:\d+', c.data))
)
def remove_from_chat_action(callback_query):
    with Session() as session:
        chat_config_id = int(callback_query.data.split(':')[-1])
        chat_config = session.get(ChatConfig, chat_config_id)
        session.delete(chat_config)
        session.commit()
        bot.send_message(
            callback_query.message.chat.id, 'Removido de Canal/Grupo!'
        )
        start(callback_query.message)


@bot.callback_query_handler(func=lambda c: c.data == 'show_chats')
def show_chats(callback_query):
    with Session() as session:
        reply_markup = {}
        for chat_config in session.scalars(select(ChatConfig)).all():
            reply_markup[bot.get_chat(int(chat_config.chat_id)).title] = {
                'callback_data': f'show_chat:{chat_config.id}'
            }
        reply_markup['Voltar'] = {'callback_data': 'return_to_start'}
        bot.send_message(
            callback_query.message.chat.id,
            'Canais/Grupos:',
            reply_markup=quick_markup(reply_markup, row_width=1),
        )


@bot.callback_query_handler(func=lambda c: c.data == 'return_to_start')
def return_to_start(callback_query):
    start(callback_query.message)


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'show_chat:\d+', c.data))
)
def show_chat_action(callback_query):
    with Session() as session:
        chat_config_id = int(callback_query.data.split(':')[-1])
        chat_config = session.get(ChatConfig, chat_config_id)
        send_chat_options(callback_query.message, chat_config)


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'show_welcome_message:\d+', c.data))
)
def show_welcome_message(callback_query):
    with Session() as session:
        chat_config_id = int(callback_query.data.split(':')[-1])
        chat_config = session.get(ChatConfig, chat_config_id)
        for welcome_message in chat_config.welcome_messages:
            send_message_from_model(
                callback_query.message.chat.id, welcome_message
            )
        send_chat_options(callback_query.message, chat_config)


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'show_member_left_message:\d+', c.data))
)
def show_member_left_message(callback_query):
    with Session() as session:
        chat_config_id = int(callback_query.data.split(':')[-1])
        chat_config = session.get(ChatConfig, chat_config_id)
        for member_left_message in chat_config.member_left_messages:
            send_message_from_model(
                callback_query.message.chat.id, member_left_message
            )
        send_chat_options(callback_query.message, chat_config)


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'edit_welcome_message:\d+', c.data))
)
def edit_welcome_message(callback_query):
    with Session() as session:
        chat_config_id = int(callback_query.data.split(':')[-1])
        chat_config = session.get(ChatConfig, chat_config_id)
        for message in chat_config.welcome_messages:
            session.delete(message)
            session.commit()
        bot.send_message(
            callback_query.message.chat.id,
            'Mande as mensagens que deseja enviar de boas-vindas, digite /pronto para finalizar',
        )
        bot.register_next_step_handler(
            callback_query.message, on_edit_welcome_message
        )


def on_edit_welcome_message(message):
    with Session() as session:
        chat_config = session.get(ChatConfig, chat_config_id)
    if message.text == '/pronto':
        send_chat_options(message, chat_config)
    else:
        welcome_message = add_message_model(message, WelcomeMessage)
        welcome_messages.append(welcome_message)
        bot.register_next_step_handler(message, on_edit_welcome_message)


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'edit_member_left_message:\d+', c.data))
)
def edit_member_left_message(callback_query):
    with Session() as session:
        chat_config_id = int(callback_query.data.split(':')[-1])
        chat_config = session.get(ChatConfig, chat_config_id)
        for message in chat_config.member_left_messages:
            session.delete(message)
            session.commit()
        bot.send_message(
            callback_query.message.chat.id,
            'Mande as mensagens que deseja enviar quando o membro sair do grupo, digite /pronto para finalizar',
        )
        bot.register_next_step_handler(
            callback_query.message, on_edit_member_left_message
        )


def on_edit_member_left_message(message):
    with Session() as session:
        chat_config = session.get(ChatConfig, chat_config_id)
    if message.text == '/pronto':
        send_chat_options(message, chat_config)
    else:
        member_left_message = add_message_model(message, MemberLeftMessage)
        member_left_messages.append(member_left_message)
        bot.register_next_step_handler(message, on_edit_member_left_message)


def send_message_from_model(chat_id, model):
    medias = {
        model.photo_id: bot.send_photo,
        model.audio_id: bot.send_audio,
        model.document_id: bot.send_document,
        model.video_id: bot.send_video,
    }
    if model.text:
        bot.send_message(chat_id, model.text)
    else:
        for media_id, function in medias.items():
            if media_id:
                file_info = bot.get_file(media_id)
                content = bot.download_file(file_info.file_path)
                function(chat_id, content, model.caption)


def send_chat_options(message, chat_config):
    global chat_config_id
    chat_config_id = chat_config.id
    bot.send_message(
        message.chat.id,
        bot.get_chat(int(chat_config.chat_id)).title,
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
def show_chats_ids(callback_query):
    global showing_chats_ids, user_id
    user_id = callback_query.message.chat.id
    bot.send_message(
        callback_query.message.chat.id,
        'Vai começar a mostrar IDs de Canais/Grupos onde o Bot estiver adicionado, quando chegar mensagens, digite /parar_mostrar_ids para parar',
    )
    showing_chats_ids = True


@bot.message_handler(commands=['parar_mostrar_ids'])
def stop_show_chats_ids(message):
    global showing_chats_ids
    bot.send_message(message.chat.id, 'Parou de mostrar IDs de Canais/Grupos')
    start(message)
    showing_chats_ids = False


@bot.message_handler(content_types=['new_chat_members'])
def send_welcome_message(message):
    with Session() as session:
        for chat_config in session.scalars(select(ChatConfig)).all():
            if chat_config.chat_id == str(message.chat.id):
                for welcome_message in chat_config.welcome_messages:
                    send_message_from_model(
                        message.from_user.id, welcome_message
                    )


@bot.message_handler(content_types=['left_chat_member'])
def send_member_left_message(message):
    with Session() as session:
        for chat_config in session.scalars(select(ChatConfig)).all():
            if chat_config.chat_id == str(message.chat.id):
                for member_left_message in chat_config.member_left_messages:
                    send_message_from_model(
                        message.from_user.id, member_left_message
                    )


@bot.chat_member_handler()
def send_channel_member_message(update):
    with Session() as session:
        for chat_config in session.scalars(select(ChatConfig)).all():
            if chat_config.chat_id == str(update.chat.id):
                if update.new_chat_member.status == 'member':
                    for welcome_message in chat_config.welcome_messages:
                        send_message_from_model(
                            update.from_user.id, welcome_message
                        )
                elif update.new_chat_member.status == 'left':
                    for (
                        member_left_message
                    ) in chat_config.member_left_messages:
                        send_message_from_model(
                            update.from_user.id, member_left_message
                        )


@bot.message_handler()
def show_chat_id(message):
    if showing_chats_ids:
        bot.send_message(
            config['user_id'],
            f'{message.chat.title or message.chat.username} | {message.chat.id}',
        )


@bot.channel_post_handler()
def show_channel_id(message):
    if showing_chats_ids:
        bot.send_message(
            config['user_id'], f'{message.chat.title} | {message.chat.id}'
        )


if __name__ == '__main__':
    bot.infinity_polling(allowed_updates=update_types)
