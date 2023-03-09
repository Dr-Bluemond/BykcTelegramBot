import datetime
import os

from sqlalchemy import String
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column


class Base(DeclarativeBase):
    pass


class Course(Base):
    __tablename__ = "course"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(1023))
    start_date: Mapped[datetime.datetime]
    end_date: Mapped[datetime.datetime]
    select_start_date: Mapped[datetime.datetime]
    select_end_date: Mapped[datetime.datetime]
    cancel_end_date: Mapped[datetime.datetime]
    status: Mapped[int] = mapped_column(index=True)
    notified: Mapped[bool] = mapped_column(default=False)

    STATUS_NOT_SELECTED = 0  # 未选择 not selected and not wanted
    STATUS_SELECTED = 1  # 已选上 selected
    STATUS_BOOKED = 2  # 预约抢选 wait for selection time and try to select
    STATUS_WAITING = 3  # 预约补选 monitor the capacity until successfully selected


engine = create_engine("sqlite:///data/db.sqlite3", echo=False)

if not os.path.exists("data/db.sqlite3"):
    Base.metadata.create_all(engine)
