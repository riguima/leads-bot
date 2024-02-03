import re

from sqlalchemy import select
from telebot import TeleBot
from telebot.util import quick_markup

from leads_bot.config import config
from leads_bot.database import Session
from leads_bot.models import Lead

bot = TeleBot(config['bot_token'])


@bot.message_handler(commands=['start', 'help'])
def start(message):
    if message.chat.username == config['username']:
        bot.send_message(
            message.chat.id,
            'Escolha uma opção:',
            reply_markup=quick_markup(
                {
                    'Adicionar Lead': {'callback_data': 'add_lead'},
                    'Remover Lead': {'callback_data': 'remove_lead'},
                    'Listar Leads': {'callback_data': 'show_leads'},
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
        bot.register_next_step_handler(message, on_welcome_message)


def on_member_left_message(message):
    if message.text == '/pronto':
        bot.send_message(message.chat.id, 'Lead Adicionado!')
        start(message)
    else:
        bot.register_next_step_handler(message, on_welcome_message)


@bot.callback_query_handler(func=lambda c: c.data == 'remove_lead')
def remove_lead(callback_query):
    with Session() as session:
        reply_markup = {}
        for lead in session.scalars(select(Lead)).all():
            reply_markup[bot.get_chat(int(lead.chat_id)).title] = {
                'callback_data': f'remove_lead:{lead.id}'
            }
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
        start(callback_query.message)


@bot.callback_query_handler(func=lambda c: c.data == 'show_leads')
def show_leads(callback_query):
    with Session() as session:
        reply_markup = {}
        for lead in session.scalars(select(Lead)).all():
            reply_markup[bot.get_chat(int(lead.chat_id)).title] = {
                'callback_data': f'show_lead:{lead.id}'
            }
        bot.send_message(
            callback_query.message.chat.id,
            'Leads:',
            reply_markup=quick_markup(reply_markup, row_width=1),
        )


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'show_lead:\d+', c.data))
)
def show_lead_action(callback_query):
    with Session() as session:
        lead_id = int(callback_query.data.split(':')[-1])
        lead = session.get(Lead, lead_id)
        bot.send_message(
            callback_query.message.chat.id,
            bot.get_chat(int(lead.chat_id)).title,
            reply_markup=quick_markup(
                {
                    'Mensagem de Boas-Vindas': {
                        'callback_data': f'show_welcome_message:{lead.id}'
                    },
                    'Mensagem quando membro sair': {
                        'callback_data': f'show_member_left_message:{lead.id}'
                    },
                },
                row_width=1,
            ),
        )
        bot.send_message(
            callback_query.message.chat.id, callback_query.message
        )


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'show_welcome_message:\d+', c.data))
)
def show_welcome_message(callback_query):
    with Session() as session:
        lead_id = int(callback_query.data.split(':')[-1])
        lead = session.get(Lead, lead_id)
        for message in lead.welcome_messages:
            medias = {
                message.photo_id: bot.send_photo,
                message.audio_id: bot.send_audio,
                message.document_id: bot.send_document,
                message.video_id: bot.send_video,
            }
            if message.text:
                bot.send_message(message.chat.id, message.text)
            else:
                for media_id, function in medias.items():
                    if media_id:
                        file_info = bot.get_file(media_id)
                        content = bot.download_file(file_info.file_path)
                        function(message.chat.id, content, message.caption)


@bot.callback_query_handler(
    func=lambda c: bool(re.findall(r'show_member_left_message:\d+', c.data))
)
def show_member_left_message(callback_query):
    with Session() as session:
        lead_id = int(callback_query.data.split(':')[-1])
        lead = session.get(Lead, lead_id)
        for message in lead.member_left_messages:
            medias = {
                message.photo_id: bot.send_photo,
                message.audio_id: bot.send_audio,
                message.document_id: bot.send_document,
                message.video_id: bot.send_video,
            }
            if message.text:
                bot.send_message(message.chat.id, message.text)
            else:
                for media_id, function in medias.items():
                    if media_id:
                        file_info = bot.get_file(media_id)
                        content = bot.download_file(file_info.file_path)
                        function(message.chat.id, content, message.caption)


@bot.callback_query_handler(func=lambda c: c.data == 'show_chats_ids')
def show_chats_ids(callback_query):
    bot.send_message(
        callback_query.message.chat.id,
        'Vai começar a mostrar IDs de Canais/Grupos onde o Bot estiver adicionado, quando chegar mensagens, digite /pronto para parar',
    )
    bot.register_next_step_handler(callback_query.message, show_chat_id)


def show_chat_id(message):
    if message.text == '/pronto':
        bot.send_message(
            message.chat.id, 'Bot parou de enviar IDs de Canais/Grupos'
        )
        start(message)
    else:
        bot.send_message(
            message.chat.id, f'{message.chat.title} - {message.chat.id}'
        )
        bot.register_next_step_handler(message, show_chat_id)


if __name__ == '__main__':
    bot.infinity_polling()
