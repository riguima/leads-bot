from typing import List, Optional

from sqlalchemy import Column, ForeignKey, Table
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from leads_bot.database import db


class Base(DeclarativeBase):
    pass


chat_config_account_table = Table(
    'chat_config_account_association_table',
    Base.metadata,
    Column('chat_config_id', ForeignKey('chats_configs.id')),
    Column('account_id', ForeignKey('accounts.id')),
)


class ChatConfig(Base):
    __tablename__ = 'chats_configs'
    id: Mapped[int] = mapped_column(primary_key=True)
    chat: Mapped[str]
    accounts: Mapped[List['Account']] = relationship(
        secondary=chat_config_account_table
    )
    welcome_messages: Mapped[List['WelcomeMessage']] = relationship(
        back_populates='chat_config',
        cascade='all, delete-orphan',
    )
    member_left_messages: Mapped[List['MemberLeftMessage']] = relationship(
        back_populates='chat_config',
        cascade='all, delete-orphan',
    )


class WelcomeMessage(Base):
    __tablename__ = 'welcome_messages'
    id: Mapped[int] = mapped_column(primary_key=True)
    chat_config: Mapped['ChatConfig'] = relationship(
        back_populates='welcome_messages'
    )
    chat_config_id: Mapped[int] = mapped_column(ForeignKey('chats_configs.id'))
    photo_id: Mapped[Optional[str]]
    audio_id: Mapped[Optional[str]]
    document_id: Mapped[Optional[str]]
    video_id: Mapped[Optional[str]]
    text: Mapped[Optional[str]]
    caption: Mapped[Optional[str]]


class MemberLeftMessage(Base):
    __tablename__ = 'member_left_messages'
    id: Mapped[int] = mapped_column(primary_key=True)
    chat_config: Mapped['ChatConfig'] = relationship(
        back_populates='member_left_messages'
    )
    chat_config_id: Mapped[int] = mapped_column(ForeignKey('chats_configs.id'))
    photo_id: Mapped[Optional[str]]
    audio_id: Mapped[Optional[str]]
    document_id: Mapped[Optional[str]]
    video_id: Mapped[Optional[str]]
    text: Mapped[Optional[str]]
    caption: Mapped[Optional[str]]


class Account(Base):
    __tablename__ = 'accounts'
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[str]
    username: Mapped[str]


class Message(Base):
    __tablename__ = 'messages'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str]
    chat_id: Mapped[int]
    welcome_message_id: Mapped[Optional[int]]
    member_left_message_id: Mapped[Optional[int]]


Base.metadata.create_all(db)
