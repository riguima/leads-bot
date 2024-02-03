import re

import toml
from sqlalchemy import select
from telebot import TeleBot
from telebot.util import quick_markup, update_types

from leads_bot.config import config
from leads_bot.database import Session
from leads_bot.models import Lead, MemberLeftMessage, WelcomeMessage

bot = TeleBot(config['bot_token'])

showing_chats_ids = False
lead_id = None
welcome_messages = []
member_left_messages = []


@bot.message_handler(commands=['start', 'help'])
def start(message):
    if message.chat.username == config['username']:
        if config.get('user_id') is None:
            config['user_id'] = message.chat.id
            toml.dump(config, open('.config.toml', 'w'))
        bot.send_message(
            message.chat.id,
            'Escolha uma opção:',
            reply_markup=quick_markup(
                {
                    'Adicionar Lead': {'callback_data': 'add_lead'},
                    'Remover Lead': {'callback_data': 'remove_lead'},
                    'Leads': {'callback_data': 'show_leads'},
                    'Mostrar IDs': {'callback_data': 'show_chats_ids'},
                },
                row_width=1,
            ),
        )


@bot.callback_query_handler(func=lambda c: c.data == 'add_lead')
def add_lead(callback_query):
    bot.send_message(
        callback_query.message.chat.id, 'Digite o ID do Canal/Grupo'
    )
    bot.register_next_step_handler(callback_query.message, on_chat_id)


def on_chat_id(message):
    global lead_id, welcome_messages, member_left_messages
    with Session() as session:
        lead = Lead(chat_id=message.text)
        session.add(lead)
        session.commit()
        session.flush()
        lead_id = lead.id
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
        bot.send_message(message.chat.id, 'Lead Adicionado!')
        start(message)
    else:
        member_left_message = add_message_model(message, MemberLeftMessage)
        member_left_messages.append(member_left_message)
        bot.register_next_step_handler(message, on_member_left_message)


def add_message_model(message, model_class):
    with Session() as session:
        message_model = model_class(
            lead_id=lead_id,
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


@bot.callback_query_handler(func=lambda c: c.data == 'remove_lead')
def remove_lead(callback_query):
    with Session() as session:
        reply_markup = {}
        for lead in session.scalars(select(Lead)).all():
            reply_markup[bot.get_chat(int(lead.chat_id)).title] = {
                'callback_data': f'remove_lead:{lead.id}'
            }
        reply_markup['Voltar'] = {'callback_data': 'return_to_start'}
        bot.send_message(
            callback_query.message.chat.id,
            'Selecione um Lead para remover:',
            reply_markup=quick_markup(reply_markup, row_width=1),
        )


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'remove_lead:\d+', c.data))
)
def remove_lead_action(callback_query):
    with Session() as session:
        lead_id = int(callback_query.data.split(':')[-1])
        lead = session.get(Lead, lead_id)
        session.delete(lead)
        session.commit()
        bot.send_message(callback_query.message.chat.id, 'Lead Removido!')
        start(callback_query.message)


@bot.callback_query_handler(func=lambda c: c.data == 'show_leads')
def show_leads(callback_query):
    with Session() as session:
        reply_markup = {}
        for lead in session.scalars(select(Lead)).all():
            reply_markup[bot.get_chat(int(lead.chat_id)).title] = {
                'callback_data': f'show_lead:{lead.id}'
            }
        reply_markup['Voltar'] = {'callback_data': 'return_to_start'}
        bot.send_message(
            callback_query.message.chat.id,
            'Leads:',
            reply_markup=quick_markup(reply_markup, row_width=1),
        )


@bot.callback_query_handler(func=lambda c: c.data == 'return_to_start')
def return_to_start(callback_query):
    start(callback_query.message)


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'show_lead:\d+', c.data))
)
def show_lead_action(callback_query):
    with Session() as session:
        lead_id = int(callback_query.data.split(':')[-1])
        lead = session.get(Lead, lead_id)
        send_lead_options(callback_query.message, lead)


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'show_welcome_message:\d+', c.data))
)
def show_welcome_message(callback_query):
    with Session() as session:
        lead_id = int(callback_query.data.split(':')[-1])
        lead = session.get(Lead, lead_id)
        for welcome_message in lead.welcome_messages:
            send_message_from_model(
                callback_query.message.chat.id, welcome_message
            )
        send_lead_options(callback_query.message, lead)


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'show_member_left_message:\d+', c.data))
)
def show_member_left_message(callback_query):
    with Session() as session:
        lead_id = int(callback_query.data.split(':')[-1])
        lead = session.get(Lead, lead_id)
        for member_left_message in lead.member_left_messages:
            send_message_from_model(
                callback_query.message.chat.id, member_left_message
            )
        send_lead_options(callback_query.message, lead)


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'edit_welcome_message:\d+', c.data))
)
def edit_welcome_message(callback_query):
    with Session() as session:
        lead_id = int(callback_query.data.split(':')[-1])
        lead = session.get(Lead, lead_id)
        for message in lead.welcome_messages:
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
        lead = session.get(Lead, lead_id)
    if message.text == '/pronto':
        send_lead_options(message, lead)
    else:
        welcome_message = add_message_model(message, WelcomeMessage)
        welcome_messages.append(welcome_message)
        bot.register_next_step_handler(message, on_edit_welcome_message)


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'edit_member_left_message:\d+', c.data))
)
def edit_member_left_message(callback_query):
    with Session() as session:
        lead_id = int(callback_query.data.split(':')[-1])
        lead = session.get(Lead, lead_id)
        for message in lead.member_left_messages:
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
        lead = session.get(Lead, lead_id)
    if message.text == '/pronto':
        send_lead_options(message, lead)
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


def send_lead_options(message, lead):
    global lead_id
    lead_id = lead.id
    bot.send_message(
        message.chat.id,
        bot.get_chat(int(lead.chat_id)).title,
        reply_markup=quick_markup(
            {
                'Ver - Mensagem de Boas-Vindas': {
                    'callback_data': f'show_welcome_message:{lead.id}'
                },
                'Ver - Mensagem ao sair': {
                    'callback_data': f'show_member_left_message:{lead.id}'
                },
                'Editar - Mensagem de Boas-Vindas': {
                    'callback_data': f'edit_welcome_message:{lead.id}'
                },
                'Editar - Mensagem ao sair': {
                    'callback_data': f'edit_member_left_message:{lead.id}'
                },
                'Voltar': {'callback_data': 'show_leads'},
            },
            row_width=1,
        ),
    )


@bot.callback_query_handler(func=lambda c: c.data == 'show_chats_ids')
def show_chats_ids(callback_query):
    global showing_chats_ids
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
        for lead in session.scalars(select(Lead)).all():
            if lead.chat_id == str(message.chat.id):
                for welcome_message in lead.welcome_messages:
                    send_message_from_model(
                        message.from_user.id, welcome_message
                    )


@bot.message_handler(content_types=['left_chat_member'])
def send_member_left_message(message):
    with Session() as session:
        for lead in session.scalars(select(Lead)).all():
            if lead.chat_id == str(message.chat.id):
                for member_left_message in lead.member_left_messages:
                    send_message_from_model(
                        message.from_user.id, member_left_message
                    )


@bot.chat_member_handler()
def send_channel_member_message(update):
    with Session() as session:
        for lead in session.scalars(select(Lead)).all():
            if lead.chat_id == str(update.chat.id):
                if update.new_chat_member.status == 'member':
                    for welcome_message in lead.welcome_messages:
                        send_message_from_model(
                            update.from_user.id, welcome_message
                        )
                elif update.new_chat_member.status == 'left':
                    for member_left_message in lead.member_left_messages:
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
