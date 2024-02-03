from typing import List

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from leads_bot.database import db


class Base(DeclarativeBase):
    pass


class Lead(Base):
    __tablename__ = 'leads'
    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[str]
    welcome_messages: Mapped[List['Message']] = relationship(
        back_populates='lead'
    )
    member_left_messages: Mapped[List['Message']] = relationship(
        back_populates='lead'
    )


class Message(Base):
    __tablename__ = 'messages'
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[str]
    lead: Mapped['Lead'] = relationship(back_populates='messages')
    lead_id: Mapped[int] = mapped_column(ForeignKey('leads.id'))


Base.metadata.create_all(db)
