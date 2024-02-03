from typing import List, Optional

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from leads_bot.database import db


class Base(DeclarativeBase):
    pass


class Lead(Base):
    __tablename__ = 'leads'
    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[str]
    welcome_messages: Mapped[List['WelcomeMessage']] = relationship(
        back_populates='lead',
        cascade='all, delete-orphan',
    )
    member_left_messages: Mapped[List['MemberLeftMessage']] = relationship(
        back_populates='lead',
        cascade='all, delete-orphan',
    )


class WelcomeMessage(Base):
    __tablename__ = 'welcome_messages'
    id: Mapped[int] = mapped_column(primary_key=True)
    lead: Mapped['Lead'] = relationship(back_populates='welcome_messages')
    lead_id: Mapped[int] = mapped_column(ForeignKey('leads.id'))
    photo_id: Mapped[Optional[str]]
    audio_id: Mapped[Optional[str]]
    document_id: Mapped[Optional[str]]
    video_id: Mapped[Optional[str]]
    text: Mapped[Optional[str]]
    caption: Mapped[Optional[str]]


class MemberLeftMessage(Base):
    __tablename__ = 'member_left_messages'
    id: Mapped[int] = mapped_column(primary_key=True)
    lead: Mapped['Lead'] = relationship(back_populates='member_left_messages')
    lead_id: Mapped[int] = mapped_column(ForeignKey('leads.id'))
    photo_id: Mapped[Optional[str]]
    audio_id: Mapped[Optional[str]]
    document_id: Mapped[Optional[str]]
    video_id: Mapped[Optional[str]]
    text: Mapped[Optional[str]]
    caption: Mapped[Optional[str]]


Base.metadata.create_all(db)
