import re

from sqlalchemy import select
from telebot import TeleBot
from telebot.util import quick_markup, update_types

from leads_bot.config import config
from leads_bot.database import Session
from leads_bot.models import ChatConfig, MemberLeftMessage, WelcomeMessage

bot = TeleBot(config['bot_token'])


showing_chats_ids = False
user_id = None
chat_config_id = None
current_client = None
welcome_messages = []
member_left_messages = []


@bot.message_handler(commands=['start', 'help'])
def start(message):
    if message.chat.username in config['admins']:
        bot.send_message(
            message.chat.id,
            'Escolha uma opção:',
            reply_markup=quick_markup(
                {
                    'Configurar Canal/Grupo': {
                        'callback_data': 'configure_chat'
                    },
                    'Remover do Canal/Grupo': {
                        'callback_data': 'remove_from_chat'
                    },
                    'Canais/Grupos': {'callback_data': 'show_chats'},
                },
                row_width=1,
            ),
        )


@bot.callback_query_handler(func=lambda c: c.data == 'configure_chat')
def configure_chat(callback_query):
    bot.send_message(
        callback_query.message.chat.id, 'Digite o ID ou Título do Canal/Grupo'
    )
    bot.register_next_step_handler(callback_query.message, on_chat)


def on_chat(message):
    global chat_config_id, welcome_messages, member_left_messages
    with Session() as session:
        chat_config = ChatConfig(chat=message.text)
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
        text = message.text
        try:
            for entity in message.entities:
                if entity.type == 'text_link':
                    text_of_link = text[
                        entity.offset - 1 : entity.offset + entity.length
                    ]
                    text = text.replace(
                        text_of_link, f'[{text_of_link}]({entity.url})'
                    )
        except TypeError:
            pass
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
            text=text,
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
            if re.findall(r'^-\d+$', chat_config.chat):
                reply_markup[bot.get_chat(int(chat_config.chat)).title] = {
                    'callback_data': f'remove_from_chat:{chat_config.id}'
                }
            else:
                reply_markup[chat_config.chat] = {
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
            if re.findall(r'^-\d+$', chat_config.chat):
                reply_markup[bot.get_chat(int(chat_config.chat)).title] = {
                    'callback_data': f'show_chat:{chat_config.id}'
                }
            else:
                reply_markup[chat_config.chat] = {
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


@bot.message_handler(content_types=['new_chat_members'])
def send_welcome_message(message):
    with Session() as session:
        for chat_config in session.scalars(select(ChatConfig)).all():
            if chat_config.chat in [str(message.chat.id), message.chat.title]:
                for welcome_message in chat_config.welcome_messages:
                    send_message_from_model(
                        message.from_user.id, welcome_message
                    )
                break


@bot.message_handler(content_types=['left_chat_member'])
def send_member_left_message(message):
    with Session() as session:
        for chat_config in session.scalars(select(ChatConfig)).all():
            if chat_config.chat in [str(message.chat.id), message.chat.title]:
                for member_left_message in chat_config.member_left_messages:
                    send_message_from_model(
                        message.from_user.id, member_left_message
                    )
                break


@bot.chat_join_request_handler()
def on_chat_join_request(request):
    with Session() as session:
        for chat_config in session.scalars(select(ChatConfig)).all():
            if chat_config.chat in [str(request.chat.id), request.chat.title]:
                for welcome_message in chat_config.welcome_messages:
                    send_message_from_model(
                        request.user_chat_id, welcome_message
                    )
                break


@bot.chat_member_handler()
def send_channel_member_message(update):
    with Session() as session:
        for chat_config in session.scalars(select(ChatConfig)).all():
            if chat_config.chat in [str(update.chat.id), update.chat.title]:
                if update.new_chat_member.status == 'member':
                    for welcome_message in chat_config.welcome_messages:
                        send_message_from_model(
                            update.from_user.id, welcome_message
                        )
                    break
                elif update.new_chat_member.status == 'left':
                    for (
                        member_left_message
                    ) in chat_config.member_left_messages:
                        send_message_from_model(
                            update.from_user.id, member_left_message
                        )
                    break


def send_message_from_model(chat, model):
    medias = {
        model.photo_id: bot.send_photo,
        model.audio_id: bot.send_audio,
        model.document_id: bot.send_document,
        model.video_id: bot.send_video,
    }
    if model.text:
        bot.send_message(chat, model.text)
    else:
        for media_id, function in medias.items():
            if media_id:
                file_info = bot.get_file(media_id)
                content = bot.download_file(file_info.file_path)
                function(chat, content, model.caption)


def send_chat_options(message, chat_config):
    global chat_config_id
    chat_config_id = chat_config.id
    if re.findall(r'^-\d+$l', chat_config.chat):
        chat_title = bot.get_chat(int(chat_config.chat)).title
    else:
        chat_title = chat_config.chat
    bot.send_message(
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


if __name__ == '__main__':
    bot.infinity_polling(allowed_updates=update_types)
