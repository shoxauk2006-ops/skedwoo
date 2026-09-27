import os
import json
import hmac
import io
import qrcode
import hashlib
import secrets
from datetime import date, time, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo
from contextvars import ContextVar
from urllib.parse import parse_qsl
from urllib import request as urllib_request
from urllib.error import URLError, HTTPError

from fastapi import (
    FastAPI,
    HTTPException,
    Header,
    Request,
    Response
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import (
    create_engine,
    String,
    Integer,
    BigInteger,
    Boolean,
    Float,
    Date,
    Time,
    DateTime,
    ForeignKey,
    Numeric,
    Text,
    inspect,
    text
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, '..', 'data', 'app.db')}")
os.makedirs(os.path.join(BASE_DIR, '..', 'data'), exist_ok=True)
engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
PRO_PRICE = 7.99

SERVICE_ADDONS = {
    20: 4.99,
    30: 7.99,
    50: 11.99,
    100: 19.99,
}

BOOKLY_REQUEST_LANGUAGE: ContextVar[Optional[str]] = ContextVar("BOOKLY_REQUEST_LANGUAGE", default=None)
BOOKLY_REQUEST_USER_ID: ContextVar[Optional[int]] = ContextVar("BOOKLY_REQUEST_USER_ID", default=None)

class Base(DeclarativeBase): pass
class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    # Подписка принадлежит конкретному бизнесу
    business_id: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        index=True
    )

    # Telegram ID владельца сохраняем для совместимости
    owner_telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True
    )

    # Текущий тариф
    plan: Mapped[str] = mapped_column(
        String(30),
        default="pro"
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=False
    )

    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True
    )

    cancel_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime,
    nullable=True
)

    status: Mapped[str] = mapped_column(
        String(30),
        default="inactive"
    )

    payment_provider: Mapped[str] = mapped_column(
        String(30),
        default=""
    )

    external_subscription_id: Mapped[str] = mapped_column(
        String(120),
        default=""
    )

    payment_method_url: Mapped[str] = mapped_column(
        String(1000),
        default=""
    )

    # Текущий лимит услуг
    current_services_limit: Mapped[int] = mapped_column(
        Integer,
        default=10
    )

    # Будущий лимит услуг.
    # None = изменение не запланировано.
    pending_services_limit: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )

    # Текущая ежемесячная цена
    current_price: Mapped[float] = mapped_column(
        Float,
        default=7.99
    )

    # Цена после следующего продления
    pending_price: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    # Время последнего применённого webhook-события Paddle.
    # Используется для защиты от событий, пришедших не по порядку.
    paddle_last_event_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True
    )
    
class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )
    
    account_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True
    )

    owner_telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True
    )

    name: Mapped[str] = mapped_column(
        String(120)
    )

    description: Mapped[str] = mapped_column(
        String(500),
        default=""
    )
       
    business_image: Mapped[str] = mapped_column(
        Text,
        default=""
    )

    address: Mapped[str] = mapped_column(
        String(255),
        default=""
    )

    phone: Mapped[str] = mapped_column(
        String(40),
        default=""
    )

    instagram_url: Mapped[str] = mapped_column(
        String(255),
        default=""
    )

    reviews_url: Mapped[str] = mapped_column(
        String(1000),
        default=""
    )

    latitude: Mapped[Optional[float]] = mapped_column(
        nullable=True
    )

    longitude: Mapped[Optional[float]] = mapped_column(
        nullable=True
    )
   
    timezone: Mapped[str] = mapped_column(
        String(64),
        default="Asia/Tashkent"
    )

    slug: Mapped[str] = mapped_column(
        String(80),
        unique=True,
        index=True
    )

    subscription_active: Mapped[bool] = mapped_column(
        Boolean,
        default=False
    )

    subscription_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True
    )

    subscription_status: Mapped[str] = mapped_column(
        String(30),
        default="inactive"
    )

    payment_provider: Mapped[str] = mapped_column(
        String(30),
        default=""
    )

    external_subscription_id: Mapped[str] = mapped_column(
        String(120),
        default=""
    )

    payment_method_url: Mapped[str] = mapped_column(
        String(1000),
        default=""
    )

class SavedBusiness(Base):
    __tablename__ = "saved_businesses"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True
    )

    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"),
        index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )
    
class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"),
        index=True
    )

    name: Mapped[str] = mapped_column(
        String(120)
    )

    description: Mapped[str] = mapped_column(
        String(500),
        default=""
    )

    price: Mapped[Decimal] = mapped_column(
        Numeric(18, 3),
        default=Decimal("0")
    )

    currency: Mapped[str] = mapped_column(
        String(8),
        default="UZS"
    )

    duration_min: Mapped[int] = mapped_column(
        Integer
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True
    )
class WorkingHour(Base):
    __tablename__ = "working_hours"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)
    start: Mapped[time] = mapped_column(Time)
    end: Mapped[time] = mapped_column(Time)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class BlockedSlot(Base):
    __tablename__ = "blocked_slots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    specialist_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("specialists.id"),
        nullable=True,
        index=True
    )
    day: Mapped[date] = mapped_column(Date)
    start: Mapped[time] = mapped_column(Time)
    end: Mapped[time] = mapped_column(Time)
    start_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    end_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    reason: Mapped[str] = mapped_column(String(255), default="")
    created_by: Mapped[str] = mapped_column(String(16), default="owner")

class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    specialist_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("specialists.id"),
        nullable=True,
        index=True
    )

    client_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    client_name: Mapped[str] = mapped_column(String(120))
    client_phone: Mapped[str] = mapped_column(String(40), default="")

    day: Mapped[date] = mapped_column(Date)
    start: Mapped[time] = mapped_column(Time)
    end: Mapped[time] = mapped_column(Time)
    start_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    end_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    client_timezone: Mapped[str] = mapped_column(String(64), default="UTC")

    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    reminder_24_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_2_sent: Mapped[bool] = mapped_column(Boolean, default=False)



class Specialist(Base):
    __tablename__ = "specialists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"),
        index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(String(500), default="")
    photo: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Optional Telegram identity for a real team member. Once connected,
    # the specialist receives booking notifications on their own account
    # and can open the staff workspace without using the owner's access.
    telegram_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        index=True
    )
    telegram_connected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True
    )
    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True
    )


class SpecialistService(Base):
    __tablename__ = "specialist_services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    specialist_id: Mapped[int] = mapped_column(
        ForeignKey("specialists.id"),
        index=True
    )
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id"),
        index=True
    )


class SpecialistWorkingHour(Base):
    __tablename__ = "specialist_working_hours"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    specialist_id: Mapped[int] = mapped_column(
        ForeignKey("specialists.id"),
        index=True
    )
    weekday: Mapped[int] = mapped_column(Integer)
    start: Mapped[time] = mapped_column(Time)
    end: Mapped[time] = mapped_column(Time)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class TelegramUserLanguage(Base):
    __tablename__ = "telegram_user_languages"
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    language: Mapped[str] = mapped_column(String(8), default="en")


def _bookly_normalize_language(value: str | None) -> str:
    value = (value or "").lower().replace("_", "-")
    if value.startswith("ru"): return "ru"
    if value.startswith("uz"): return "uz"
    if value.startswith("tr"): return "tr"
    if value.startswith("ar"): return "ar"
    return "en"


def _bookly_remember_language(user: dict, preferred_language: str | None = None) -> None:
    try:
        uid = int(user.get("id"))
    except (TypeError, ValueError):
        return

    explicit_language = bool(
        preferred_language and str(preferred_language).strip()
    )
    lang = _bookly_normalize_language(
        preferred_language
        if explicit_language
        else user.get("language_code")
    )

    try:
        with SessionLocal() as db:
            row = db.get(TelegramUserLanguage, uid)
            if row is None:
                row = TelegramUserLanguage(
                    telegram_user_id=uid,
                    language=lang,
                )
                db.add(row)
            elif explicit_language:
                # Requests without X-Bookly-Language (for example a Telegram
                # deep-link connection) must not overwrite the language the
                # user explicitly selected inside Skedwoo.
                row.language = lang
            db.commit()
    except Exception:
        pass


def _bookly_user_language(telegram_user_id: int) -> str:
    try:
        with SessionLocal() as db:
            row = db.get(TelegramUserLanguage, int(telegram_user_id))
            return _bookly_normalize_language(row.language if row else "en")
    except Exception:
        return "en"


_BOOKLY_NOTIFY_TEXT = {
  "ru": {
    "new": "Новая запись в Skedwoo",
    "phone_missing": "номер не передан",
    "cancelled_client": "Ваша запись отменена",
    "cancelled_business": "Ваша запись отменена",
    "client_booked": "Вы успешно записаны!",
    "contact_hint": "Пожалуйста, свяжитесь с бизнесом, если хотите выбрать другое время.",
    "waiting": "Ждём вас!",
    "client_cancelled": "Клиент отменил запись",
    "reminder24": "Напоминание о записи в Skedwoo",
    "reminder2": "Ваша запись сегодня в",
    "owner_reminder24": "Напоминание: запись",
  },

  "en": {
    "new": "New booking in Skedwoo",
    "phone_missing": "phone not provided",
    "cancelled_client": "Your booking has been cancelled",
    "cancelled_business": "Your booking has been cancelled",
    "client_booked": "You are successfully booked!",
    "contact_hint": "Please contact the business if you want to choose another time.",
    "waiting": "We look forward to seeing you!",
    "client_cancelled": "Client cancelled the booking",
    "reminder24": "Skedwoo booking reminder",
    "reminder2": "Your booking is today at",
    "owner_reminder24": "Reminder: booking",
  },

  "uz": {
    "new": "Skedwoo’da yangi bron",
    "phone_missing": "telefon berilmagan",
    "cancelled_client": "Broningiz bekor qilindi",
    "cancelled_business": "Broningiz bekor qilindi",
    "client_booked": "Siz muvaffaqiyatli bron qilindingiz!",
    "contact_hint": "Boshqa vaqt tanlamoqchi bo‘lsangiz, biznes bilan bog‘laning.",
    "waiting": "Sizni kutamiz!",
    "client_cancelled": "Mijoz bronni bekor qildi",
    "reminder24": "Skedwoo bron eslatmasi",
    "reminder2": "Bugungi broningiz vaqti",
    "owner_reminder24": "Eslatma: bron",
  },

  "tr": {
    "new": "Skedwoo’da yeni rezervasyon",
    "phone_missing": "telefon verilmedi",
    "cancelled_client": "Rezervasyonunuz iptal edildi",
    "cancelled_business": "Rezervasyonunuz iptal edildi",
    "client_booked": "Rezervasyonunuz başarıyla oluşturuldu!",
    "contact_hint": "Başka bir zaman seçmek istiyorsanız işletmeyle iletişime geçin.",
    "waiting": "Sizi bekliyoruz!",
    "client_cancelled": "Müşteri rezervasyonu iptal etti",
    "reminder24": "Skedwoo rezervasyon hatırlatması",
    "reminder2": "Bugünkü rezervasyon saatiniz",
    "owner_reminder24": "Hatırlatma: rezervasyon",
  },

  "ar": {
    "new": "حجز جديد في Skedwoo",
    "phone_missing": "رقم الهاتف غير متوفر",
    "cancelled_client": "تم إلغاء حجزك",
    "cancelled_business": "تم إلغاء حجزك",
    "client_booked": "تم حجز موعدك بنجاح!",
    "contact_hint": "يرجى التواصل مع النشاط إذا أردت اختيار وقت آخر.",
    "waiting": "ننتظركم!",
    "client_cancelled": "ألغى العميل الحجز",
    "reminder24": "تذكير بحجز Skedwoo",
    "reminder2": "موعد حجزك اليوم في",
    "owner_reminder24": "تذكير: الحجز",
  },
}


def _bookly_t(lang: str, key: str) -> str:
    return _BOOKLY_NOTIFY_TEXT[_bookly_normalize_language(lang)][key]


Base.metadata.create_all(engine)

def ensure_subscription_schema():
    """
    Создаёт/обновляет таблицу подписок.

    Подписка принадлежит конкретному бизнесу.
    Старые данные из businesses сохраняются.
    """
    with engine.begin() as conn:
        inspector = inspect(conn)
        tables = inspector.get_table_names()

        # ---------------------------------------------------------
        # Создание новой таблицы, если её ещё нет
        # ---------------------------------------------------------

        if "subscriptions" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE subscriptions (
                        id INTEGER PRIMARY KEY,
                        business_id INTEGER UNIQUE NOT NULL,
                        owner_telegram_id BIGINT NOT NULL,
                        plan VARCHAR(30) DEFAULT 'pro',
                        active BOOLEAN DEFAULT FALSE,
                        expires_at TIMESTAMP,
                        status VARCHAR(30) DEFAULT 'inactive',
                        payment_provider VARCHAR(30) DEFAULT '',
                        external_subscription_id VARCHAR(120) DEFAULT '',
                        payment_method_url VARCHAR(1000) DEFAULT '',
                        current_services_limit INTEGER DEFAULT 10,
                        pending_services_limit INTEGER,
                        current_price REAL DEFAULT 7.99,
                        pending_price REAL
                    )
                    """
                )
            )

            return

        # ---------------------------------------------------------
        # Получаем существующие колонки
        # ---------------------------------------------------------

        existing_columns = {
            column["name"]
            for column in inspect(conn).get_columns(
                "subscriptions"
            )
        }
        # ---------------------------------------------------------
        # Исправляем старый UNIQUE index на owner_telegram_id.
        #
        # Раньше подписка была привязана к владельцу,
        # поэтому owner_telegram_id был UNIQUE.
        #
        # Сейчас одна подписка принадлежит одному бизнесу,
        # поэтому у одного владельца может быть несколько подписок.
        # ---------------------------------------------------------

        conn.execute(
            text(
                """
                DROP INDEX IF EXISTS ix_subscriptions_owner_telegram_id
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_subscriptions_owner_telegram_id
                ON subscriptions (owner_telegram_id)
                """
            )
        )

        # ---------------------------------------------------------
        # Добавляем новые колонки в старую таблицу
        # ---------------------------------------------------------

        columns_to_add = {
    "business_id":
        "INTEGER",

    "current_services_limit":
        "INTEGER DEFAULT 10",

    "pending_services_limit":
        "INTEGER",

    "current_price":
        "REAL DEFAULT 7.99",

    "pending_price":
        "REAL",

    "paddle_last_event_at":
        "TIMESTAMP",

    "cancel_at":
        "TIMESTAMP",
}

        for column_name, column_definition in columns_to_add.items():

            if column_name not in existing_columns:

                conn.execute(
                    text(
                        f"""
                        ALTER TABLE subscriptions
                        ADD COLUMN {column_name}
                        {column_definition}
                        """
                    )
                )

        # ---------------------------------------------------------
        # Обновляем inspector после ALTER TABLE
        # ---------------------------------------------------------

        existing_columns = {
            column["name"]
            for column in inspect(conn).get_columns(
                "subscriptions"
            )
        }

        # ---------------------------------------------------------
        # Старые подписки были owner-level.
        #
        # Сейчас мы не можем автоматически безопасно определить,
        # какому из нескольких бизнесов владельца должна принадлежать
        # старая подписка.
        #
        # Поэтому переносим подписку только если у владельца
        # существует ровно один бизнес.
        # ---------------------------------------------------------

        if "businesses" not in inspect(conn).get_table_names():
            return

        owners = conn.execute(
            text(
                """
                SELECT
                    owner_telegram_id,
                    COUNT(*) AS business_count,
                    MIN(id) AS business_id
                FROM businesses
                GROUP BY owner_telegram_id
                """
            )
        ).mappings().all()

        for owner in owners:

            owner_id = owner["owner_telegram_id"]

            business_count = owner["business_count"]
            business_id = owner["business_id"]

            if business_count != 1:
                continue

            # Ищем старую подписку владельца
            subscription = conn.execute(
                text(
                    """
                    SELECT
                        id,
                        owner_telegram_id,
                        plan,
                        active,
                        expires_at,
                        status,
                        payment_provider,
                        external_subscription_id,
                        payment_method_url
                    FROM subscriptions
                    WHERE owner_telegram_id = :owner_id
                    ORDER BY id ASC
                    LIMIT 1
                    """
                ),
                {
                    "owner_id": owner_id
                }
            ).mappings().first()

            if not subscription:
                continue

            # Если бизнес уже указан — ничего не меняем
            if subscription.get("business_id"):
                continue

            conn.execute(
                text(
                    """
                    UPDATE subscriptions
                    SET
                        business_id = :business_id,
                        plan = CASE
                            WHEN plan = 'standard'
                            THEN 'pro'
                            ELSE plan
                        END,
                        current_services_limit = 10,
                        current_price = 7.99
                    WHERE id = :subscription_id
                    """
                ),
                {
                    "business_id": business_id,
                    "subscription_id": subscription["id"]
                }
            )

        # ---------------------------------------------------------
        # Для новых/существующих записей:
        # если лимит или цена NULL — устанавливаем базовые значения.
        # ---------------------------------------------------------

        conn.execute(
            text(
                """
                UPDATE subscriptions
                SET current_services_limit = 10
                WHERE current_services_limit IS NULL
                """
            )
        )

        conn.execute(
            text(
                """
                UPDATE subscriptions
                SET current_price = 7.99
                WHERE current_price IS NULL
                """
            )
        )




ensure_subscription_schema()
def ensure_specialist_schema():
    """Add specialist tables/booking column to an existing database."""
    with engine.begin() as conn:
        inspector = inspect(conn)
        tables = inspector.get_table_names()

        # Base.metadata.create_all() creates the three new specialist tables.
        # Existing bookings need an additive nullable column.
        if "bookings" in tables:
            existing = {c["name"] for c in inspector.get_columns("bookings")}
            if "specialist_id" not in existing:
                conn.execute(
                    text(
                        "ALTER TABLE bookings ADD COLUMN specialist_id INTEGER"
                    )
                )

        if "blocked_slots" in tables:
            existing_blocks = {
                c["name"]
                for c in inspector.get_columns("blocked_slots")
            }
            if "specialist_id" not in existing_blocks:
                conn.execute(
                    text(
                        "ALTER TABLE blocked_slots ADD COLUMN specialist_id INTEGER"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_blocked_slots_specialist_id "
                        "ON blocked_slots (specialist_id)"
                    )
                )
            if "created_by" not in existing_blocks:
                conn.execute(
                    text(
                        "ALTER TABLE blocked_slots ADD COLUMN created_by "
                        "VARCHAR(16) DEFAULT 'owner'"
                    )
                )
                conn.execute(
                    text(
                        "UPDATE blocked_slots SET created_by = 'owner' "
                        "WHERE created_by IS NULL OR created_by = ''"
                    )
                )

        if "specialists" in tables:
            existing = {c["name"] for c in inspector.get_columns("specialists")}
            if "telegram_user_id" not in existing:
                conn.execute(
                    text("ALTER TABLE specialists ADD COLUMN telegram_user_id BIGINT")
                )
                conn.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_specialists_telegram_user_id ON specialists (telegram_user_id)")
                )
            if "telegram_connected_at" not in existing:
                conn.execute(
                    text("ALTER TABLE specialists ADD COLUMN telegram_connected_at TIMESTAMP")
                )
            if "notifications_enabled" not in existing:
                conn.execute(
                    text(
                        "ALTER TABLE specialists ADD COLUMN notifications_enabled BOOLEAN DEFAULT TRUE"
                    )
                )


ensure_specialist_schema()


def ensure_business_schema():
    """
    Добавляет новые колонки в существующую БД,
    не удаляя существующие бизнесы.
    """
    with engine.begin() as conn:
        inspector = inspect(conn)

        if "businesses" not in inspector.get_table_names():
            return

        existing = {
            column["name"]
            for column in inspector.get_columns("businesses")
        }

        dialect = engine.dialect.name

        float_type = (
            "DOUBLE PRECISION"
            if dialect == "postgresql"
            else "REAL"
        )

        columns_to_add = {
            "description":
                "VARCHAR(500) DEFAULT ''",

            "business_image":
                "TEXT DEFAULT ''",

            "address":
                "VARCHAR(255) DEFAULT ''",

            "phone":
                "VARCHAR(40) DEFAULT ''",

            "instagram_url":
                "VARCHAR(255) DEFAULT ''",

            "reviews_url":
                "VARCHAR(1000) DEFAULT ''",

            "latitude":
                float_type,

            "longitude":
                float_type,

            "timezone":
                "VARCHAR(64) DEFAULT 'Asia/Tashkent'",

            "subscription_active":
                "BOOLEAN DEFAULT FALSE",

            "subscription_expires_at":
                "TIMESTAMP",

            "subscription_status":
                "VARCHAR(30) DEFAULT 'inactive'",

            "payment_provider":
                "VARCHAR(30) DEFAULT ''",

            "external_subscription_id":
                "VARCHAR(120) DEFAULT ''",

            "payment_method_url":
                "VARCHAR(1000) DEFAULT ''"
        }

        for column_name, column_definition in columns_to_add.items():

            if column_name not in existing:

                conn.execute(
                    text(
                        f"""
                        ALTER TABLE businesses
                        ADD COLUMN {column_name}
                        {column_definition}
                        """
                    )
                )


ensure_business_schema()


def _bookly_zone(name: str | None):
    try:
        return ZoneInfo(name or "Asia/Tashkent")
    except Exception:
        return ZoneInfo("Asia/Tashkent")


def _bookly_to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timezone-aware datetime required")
    return value.astimezone(timezone.utc).replace(tzinfo=None)

def _bookly_from_utc(
    value: datetime | None,
    zone: str
) -> datetime | None:
    if value is None:
        return None

    return value.replace(
        tzinfo=timezone.utc
    ).astimezone(
        _bookly_zone(zone)
    )


def ensure_timezone_schema():
    """Add UTC timestamp columns and backfill legacy local rows."""
    with engine.begin() as conn:
        inspector = inspect(conn)
        timestamp_type = "TIMESTAMP" if engine.dialect.name == "postgresql" else "DATETIME"

        if "bookings" in inspector.get_table_names():
            existing = {c["name"] for c in inspector.get_columns("bookings")}
            for name, definition in {
                "start_at_utc": timestamp_type,
                "end_at_utc": timestamp_type,
                "client_timezone": "VARCHAR(64) DEFAULT 'UTC'",
            }.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE bookings ADD COLUMN {name} {definition}"))

        if "blocked_slots" in inspector.get_table_names():
            existing = {c["name"] for c in inspector.get_columns("blocked_slots")}
            for name in ("start_at_utc", "end_at_utc"):
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE blocked_slots ADD COLUMN {name} {timestamp_type}"))

    with SessionLocal() as db:
        bookings = db.query(Booking).filter(Booking.start_at_utc.is_(None)).all()
        for booking in bookings:
            business = db.get(Business, booking.business_id)
            if not business:
                continue
            zone = _bookly_zone(business.timezone)
            booking.start_at_utc = _bookly_to_utc(
                datetime.combine(booking.day, booking.start, tzinfo=zone)
            )
            booking.end_at_utc = _bookly_to_utc(
                datetime.combine(booking.day, booking.end, tzinfo=zone)
            )
            booking.client_timezone = business.timezone or "Asia/Tashkent"

        blocks = db.query(BlockedSlot).filter(BlockedSlot.start_at_utc.is_(None)).all()
        for block in blocks:
            business = db.get(Business, block.business_id)
            if not business:
                continue
            zone = _bookly_zone(business.timezone)
            block.start_at_utc = _bookly_to_utc(
                datetime.combine(block.day, block.start, tzinfo=zone)
            )
            block.end_at_utc = _bookly_to_utc(
                datetime.combine(block.day, block.end, tzinfo=zone)
            )

        db.commit()


ensure_timezone_schema()

app = FastAPI(
    title="Skedwoo API",
    version="0.2.0"
)

app = FastAPI(title="Skedwoo API", version="0.2.0")
ACTIVE_BUSINESS_ID: ContextVar[Optional[int]] = ContextVar(
    "ACTIVE_BUSINESS_ID",
    default=None
)


@app.middleware("http")
async def capture_active_business(
    request: Request,
    call_next
):
    raw_business_id = request.headers.get(
        "X-Bookly-Business-Id"
    )
    raw_language = request.headers.get("X-Bookly-Language")
    language_token = BOOKLY_REQUEST_LANGUAGE.set(_bookly_normalize_language(raw_language) if raw_language else None)


    business_id = None

    if raw_business_id:
        try:
            business_id = int(
                raw_business_id
            )
        except ValueError:
            business_id = None

    token = ACTIVE_BUSINESS_ID.set(
        business_id
    )

    try:
        response = await call_next(
            request
        )
        return response
    finally:
        ACTIVE_BUSINESS_ID.reset(
            token
        )
        BOOKLY_REQUEST_LANGUAGE.reset(language_token)
        try:
            BOOKLY_REQUEST_USER_ID.set(None)
        except Exception:
            pass
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://boockly.vercel.app",
        "https://skedwoo.vercel.app",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ---------- Telegram Mini App authentication ----------
def validate_init_data(init_data: str) -> dict:
    if not BOT_TOKEN:
        raise HTTPException(500, "BOT_TOKEN is not configured")
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = pairs.pop("hash", None)
        if not received_hash:
            raise ValueError("hash missing")
        data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calculated, received_hash):
            raise ValueError("invalid hash")
        auth_date = int(pairs.get("auth_date", "0"))
        if abs(int(datetime.utcnow().timestamp()) - auth_date) > 86400:
            raise ValueError("init data expired")
        user = json.loads(pairs.get("user", "{}"))
        return user
    except Exception as exc:
        raise HTTPException(401, f"Invalid Telegram initData: {exc}")

def telegram_user(x_init_data: str) -> dict:
    user = validate_init_data(x_init_data)
    try:
        request_user_id_token = BOOKLY_REQUEST_USER_ID.set(int(user.get("id")))
    except (TypeError, ValueError):
        request_user_id_token = None
    _bookly_remember_language(user, BOOKLY_REQUEST_LANGUAGE.get())
    return user


def telegram_api(method: str, payload: dict):
    """Small synchronous Telegram Bot API helper; keeps the API service dependency-light."""
    if not BOT_TOKEN:
        return None
    data=json.dumps(payload).encode("utf-8")
    req=urllib_request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        data=data,
        headers={"Content-Type":"application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError):
        return None


def telegram_api_for_recipient(method: str, payload: dict):
    """Send using the recipient's stored Skedwoo language, not the current request language."""
    token = BOOKLY_REQUEST_LANGUAGE.set(None)
    try:
        return telegram_api(method, payload)
    finally:
        BOOKLY_REQUEST_LANGUAGE.reset(token)


def notify_owner_new_booking(
    db,
    booking,
    service,
    notify_specialist: bool = True,
):
    business = db.get(Business, booking.business_id)
    if not business:
        return

    specialist = None
    if getattr(booking, "specialist_id", None) is not None:
        specialist = db.get(Specialist, booking.specialist_id)

    lines = [
        "🔔 <b>Новая запись в Skedwoo</b>",
        "",
        f"👤 {booking.client_name}",
        f"📞 {booking.client_phone or 'номер не передан'}",
        f"💈 {service.name}",
    ]

    if specialist and specialist.name:
        lines.append(f"👨‍💼 Специалист: {specialist.name}")

    lines.extend([
        f"📅 {booking.day.isoformat()}",
        f"🕐 {booking.start.strftime('%H:%M')}–{booking.end.strftime('%H:%M')}",
        f"🆔 #{booking.id}",
    ])

    message = "\n".join(lines)

    # The owner still receives the business-level notification.
    if business.owner_telegram_id:
        telegram_api_for_recipient(
            "sendMessage",
            {
                "chat_id": business.owner_telegram_id,
                "text": message,
                "parse_mode": "HTML",
            },
        )

    # If the customer selected a connected specialist, notify that person
    # on their own Telegram account as well.
    if (
        notify_specialist
        and specialist
        and specialist.telegram_user_id
        and specialist.notifications_enabled
        and int(specialist.telegram_user_id) != int(business.owner_telegram_id or 0)
    ):
        telegram_api_for_recipient(
            "sendMessage",
            {
                "chat_id": specialist.telegram_user_id,
                "text": message,
                "parse_mode": "HTML",
            },
        )


def notify_specialist_booking_cancelled(
    db,
    booking,
    cancelled_by_business: bool = False,
):
    specialist_id = getattr(booking, "specialist_id", None)
    if specialist_id is None:
        return

    specialist = db.get(Specialist, specialist_id)
    if (
        not specialist
        or not specialist.telegram_user_id
        or not specialist.notifications_enabled
    ):
        return

    business = db.get(Business, booking.business_id)
    if (
        business
        and business.owner_telegram_id
        and int(specialist.telegram_user_id) == int(business.owner_telegram_id)
    ):
        return

    title = (
        "Ваша запись отменена бизнесом."
        if cancelled_by_business
        else "Клиент отменил запись"
    )

    telegram_api_for_recipient(
        "sendMessage",
        {
            "chat_id": specialist.telegram_user_id,
            "text": (
                f"❌ <b>{title}</b>\n\n"
                f"👤 {booking.client_name}\n"
                f"📞 {booking.client_phone or 'номер не передан'}\n"
                f"📅 {booking.day.isoformat()}\n"
                f"🕐 {booking.start.strftime('%H:%M')}–{booking.end.strftime('%H:%M')}\n"
                f"🆔 #{booking.id}"
            ),
            "parse_mode": "HTML",
        },
    )

_BOOKLY_FINAL_NOTIFICATION_WRAPPER = True

def _bookly_localize_outgoing_text(text: str, lang: str) -> str:
    d = {
        "ru": {
            "new": "Новая запись в Skedwoo", "booked": "Вы успешно записаны!", "cancel_client": "Ваша запись отменена",
            "cancel_business": "Ваша запись отменена бизнесом.", "cancel_owner": "Клиент отменил запись",
            "hint": "Пожалуйста, свяжитесь с бизнесом, если хотите выбрать другое время.", "waiting": "Ждём вас!",
            "phone": "номер не передан", "phone_label": "Ваш номер:", "contact_label": "Связаться:", "specialist_label": "Специалист:", "address": "Адрес не указан"
        },
        "en": {
            "new": "New booking in Skedwoo", "booked": "You are successfully booked!", "cancel_client": "Your booking has been cancelled",
            "cancel_business": "Your booking was cancelled by the business.", "cancel_owner": "Client cancelled the booking",
            "hint": "Please contact the business if you want to choose another time.", "waiting": "We look forward to seeing you!",
            "phone": "phone not provided", "phone_label": "Your number:", "contact_label": "Contact:", "specialist_label": "Specialist:", "address": "Address not provided"
        },
        "uz": {
            "new": "Skedwoo’da yangi bron", "booked": "Siz muvaffaqiyatli bron qilindingiz!", "cancel_client": "Broningiz bekor qilindi",
            "cancel_business": "Bron biznes tomonidan bekor qilindi.", "cancel_owner": "Mijoz bronni bekor qildi",
            "hint": "Boshqa vaqt tanlamoqchi bo‘lsangiz, biznes bilan bog‘laning.", "waiting": "Sizni kutamiz!",
            "phone": "telefon berilmagan", "phone_label": "Raqamingiz:", "contact_label": "Bog‘lanish:", "specialist_label": "Mutaxassis:", "address": "Manzil ko‘rsatilmagan"
        },
        "tr": {
            "new": "Skedwoo’da yeni rezervasyon", "booked": "Rezervasyonunuz başarıyla oluşturuldu!", "cancel_client": "Rezervasyonunuz iptal edildi",
            "cancel_business": "Rezervasyon işletme tarafından iptal edildi.", "cancel_owner": "Müşteri rezervasyonu iptal etti",
            "hint": "Başka bir zaman seçmek istiyorsanız işletmeyle iletişime geçin.", "waiting": "Sizi bekliyoruz!",
            "phone": "telefon verilmedi", "phone_label": "Numaranız:", "contact_label": "İletişim:", "specialist_label": "Uzman:", "address": "Adres belirtilmedi"
        },
        "ar": {
            "new": "حجز جديد في Skedwoo", "booked": "تم حجز موعدك بنجاح!", "cancel_client": "تم إلغاء حجزك",
            "cancel_business": "تم إلغاء الحجز من قبل النشاط.", "cancel_owner": "ألغى العميل الحجز",
            "hint": "يرجى التواصل مع النشاط إذا أردت اختيار وقت آخر.", "waiting": "ننتظركم!",
            "phone": "رقم الهاتف غير متوفر", "phone_label": "رقمك:", "contact_label": "للتواصل:", "specialist_label": "المختص:", "address": "العنوان غير متوفر"
        },
    }[_bookly_normalize_language(lang)]

    replacements = [
        ("Новая запись в Skedwoo", d["new"]),
        ("Вы успешно записаны!", d["booked"]),
        ("Ваша запись отменена бизнесом.", d["cancel_business"]),
        ("Ваша запись отменена", d["cancel_client"]),
        ("Клиент отменил запись", d["cancel_owner"]),
        ("Пожалуйста, свяжитесь с бизнесом, если хотите выбрать другое время.", d["hint"]),
        ("Ждём вас!", d["waiting"]),
        ("номер не передан", d["phone"]),
        ("номер не указан", d["phone"]),
        ("Ваш номер:", d["phone_label"]),
        ("Связаться:", d["contact_label"]),
        ("Специалист:", d["specialist_label"]),
        ("Адрес не указан", d["address"]),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text

_BOOKLY_RAW_TELEGRAM_API = telegram_api

def telegram_api(method: str, payload: dict):
    """Telegram Bot API helper using the language selected in Skedwoo."""
    if not BOT_TOKEN:
        return None

    if method == "sendMessage" and isinstance(payload, dict) and payload.get("chat_id"):
        payload = dict(payload)
        chat_id = int(payload["chat_id"])
        request_lang = BOOKLY_REQUEST_LANGUAGE.get()
        effective_lang = (
            _bookly_normalize_language(request_lang)
            if request_lang
            else _bookly_user_language(chat_id)
        )
        payload["text"] = _bookly_localize_outgoing_text(
            str(payload.get("text", "")),
            effective_lang
        )

    data = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=8) as response:
            body = response.read().decode("utf-8")
            result = json.loads(body)
            if not result.get("ok", True):
                print("TELEGRAM API ERROR:", result)
            return result
    except Exception as exc:
        print("TELEGRAM SEND ERROR:", repr(exc))
        return None

def owner_business(
    db,
    owner_id: int,
    business_id: Optional[int] = None
):
    selected_id = (
        business_id
        if business_id is not None
        else ACTIVE_BUSINESS_ID.get()
    )

    query = db.query(Business).filter(
        Business.owner_telegram_id ==
        owner_id
    )

    if selected_id is not None:
        return (
            query
            .filter(
                Business.id ==
                selected_id
            )
            .first()
        )

    return (
        query
        .order_by(
            Business.id.asc()
        )
        .first()
    )
def owner_subscription(db, business_id: int):
    return (
        db.query(Subscription)
        .filter(
            Subscription.business_id == business_id
        )
        .first()
    )


def subscription_limits(subscription):
    """
    Возвращает текущие возможности подписки
    конкретного бизнеса.
    """

    if not subscription or not subscription.active:
        return {
        "plan": "free",
        "max_services": 10,
        "current_price": 0.0,
        "pending_services": None,
        "pending_price": None
    }

    current_limit = int(
        subscription.current_services_limit
        or 10
    )

    pending_limit = (
        int(subscription.pending_services_limit)
        if subscription.pending_services_limit
        is not None
        else None
    )

    # Once a downgrade is scheduled, do not allow the active service
    # count to grow above the future lower limit. Otherwise the business
    # could reach renewal with more active services than its paid package.
    max_services = current_limit

    if (
        pending_limit is not None
        and pending_limit < current_limit
    ):
        max_services = pending_limit

    return {
        "plan": subscription.plan or "pro",

        "max_services": max_services,

        "current_price": (
            float(subscription.current_price)
            if subscription.current_price is not None
            else 7.99
        ),

        "pending_services": (
            subscription.pending_services_limit
        ),

        "pending_price": (
            float(subscription.pending_price)
            if subscription.pending_price is not None
            else None
        )
    }
def current_service_limit_for_business(
    db,
    business_id: int,
) -> int:
    subscription = owner_subscription(
        db,
        business_id,
    )

    if not subscription or not subscription.active:
        return 0

    return max(
        0,
        int(
            subscription.current_services_limit
            or 10
        ),
    )


def service_ids_available_under_plan(
    db,
    business_id: int,
) -> list[int]:
    limit = current_service_limit_for_business(
        db,
        business_id,
    )

    if limit <= 0:
        return []

    rows = (
        db.query(Service.id)
        .filter(
            Service.business_id == business_id,
            Service.active == True,
        )
        .order_by(Service.id.asc())
        .limit(limit)
        .all()
    )

    return [
        int(row[0])
        for row in rows
    ]


def service_available_under_plan(
    db,
    business_id: int,
    service_id: int,
) -> bool:
    return int(service_id) in set(
        service_ids_available_under_plan(
            db,
            business_id,
        )
    )


def calculate_subscription_price(services_limit: int) -> float:
    """
    Возвращает общую ежемесячную стоимость подписки.

    10 услуг включены в Pro за $7.99.
    Дополнительные лимиты оплачиваются отдельно.
    """

    if services_limit <= 10:
        return PRO_PRICE

    addon_price = SERVICE_ADDONS.get(
        services_limit
    )

    if addon_price is None:
        raise ValueError(
            f"Недопустимый лимит услуг: {services_limit}"
        )

    return round(
        PRO_PRICE + addon_price,
        2
    )
def ensure_owner(db, business_id: int, owner_id: int):
    b = db.get(Business, business_id)
    if not b or b.owner_telegram_id != owner_id:
        raise HTTPException(403, "Not your business")
    return b

# ---------- schemas ----------
class BusinessIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    business_image: str = ""
    description: str = ""
    address: str = ""
    phone: str = ""
    instagram_url: Optional[str] = Field(default=None, max_length=255)
    reviews_url: Optional[str] = Field(default=None, max_length=1000)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timezone: str = "Asia/Tashkent"

class ServiceIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    price: Decimal = Field(
    ge=Decimal("0"),
    decimal_places=3,
    max_digits=18
)
    currency: str = "UZS"
    duration_min: int = Field(gt=0, le=1440)
    active: bool = True

class SubscriptionLimitChangeIn(BaseModel):
    services_limit: int

class WorkingHourIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start: time
    end: time
    active: bool = True
    
class BusinessCreateIn(BusinessIn):
    hours: list[WorkingHourIn] = []

class BlockIn(BaseModel):
    day: date
    start: time
    end: time
    reason: str = ""
    specialist_id: Optional[int] = None

class BookingIn(BaseModel):
    business_id: int
    service_id: int
    specialist_id: Optional[int] = None
    client_telegram_id: int = 0
    client_name: str = "Telegram user"
    client_phone: str = ""
    day: date
    start: time
    client_timezone: str = "UTC"
    
class AdminBookingIn(BaseModel):
    service_id: int
    specialist_id: Optional[int] = None
    client_name: str = Field(min_length=1, max_length=120)
    client_phone: str = ""
    day: date
    start: time
# ---------- common ----------
@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "bookly",
        "release": "oauth-canonical-20260920",
    }

@app.get("/me")
def me(x_telegram_init_data: str = Header(default="")):
    user = telegram_user(x_telegram_init_data)
    with SessionLocal() as db:
        b = owner_business(db, int(user["id"]))
        return {"user": user, "business": b}

# ---------- admin ----------
@app.put("/admin/business")
def upsert_business(x: BusinessIn, x_telegram_init_data: str = Header(default="")):
    user = telegram_user(x_telegram_init_data)
    owner_id = int(user["id"])
    with SessionLocal() as db:
        b = owner_business(db, owner_id)
        if not b:
            slug = secrets.token_urlsafe(8).replace("-", "").replace("_", "").lower()
            payload = x.model_dump()
            payload["instagram_url"] = payload.get("instagram_url") or ""
            payload["reviews_url"] = payload.get("reviews_url") or ""
            b = Business(owner_telegram_id=owner_id, slug=slug, **payload)
            db.add(b)
        else:
            payload = x.model_dump(exclude_unset=True)
            payload.pop("timezone", None)
            for k, v in payload.items(): setattr(b, k, v)
        db.commit(); db.refresh(b)
        return b
@app.get("/admin/businesses")
def admin_businesses(
    x_telegram_init_data: str = Header(
        default=""
    )
):
    user = telegram_user(
        x_telegram_init_data
    )

    owner_id = int(
        user["id"]
    )

    with SessionLocal() as db:

        businesses = (
            db.query(Business)
            .filter(
                Business.owner_telegram_id ==
                owner_id
            )
            .order_by(
                Business.id.asc()
            )
            .all()
        )

        result = []

        for business in businesses:

            subscription = (
                db.query(Subscription)
                .filter(
                    Subscription.business_id ==
                    business.id
                )
                .first()
            )

            business_data = {
                column.name: getattr(
                    business,
                    column.name
                )
                for column
                in Business.__table__.columns
            }

            business_data["subscription_active"] = (
                bool(subscription.active)
                if subscription
                else False
            )

            business_data["subscription_status"] = (
                (subscription.status or "inactive")
                if subscription
                else "inactive"
            )

            business_data["subscription_expires_at"] = (
                subscription.expires_at
                if subscription
                else None
            )

            business_data["payment_provider"] = (
                subscription.payment_provider
                if subscription
                else ""
            )

            business_data["external_subscription_id"] = (
                subscription.external_subscription_id
                if subscription
                else ""
            )

            business_data["services_limit"] = (
                subscription.current_services_limit
                if subscription
                and subscription.active
                else 0
            )

            business_data["pending_services_limit"] = (
                subscription.pending_services_limit
                if subscription
                else None
            )

            business_data["current_price"] = (
                float(
                    subscription.current_price
                )
                if subscription
                and subscription.current_price is not None
                else 0.0
            )

            business_data["pending_price"] = (
                float(
                    subscription.pending_price
                )
                if subscription
                and subscription.pending_price is not None
                else None
            )

            result.append(
                business_data
            )

        return result
        


@app.post("/admin/businesses")
def admin_create_business(
    x: BusinessCreateIn,
    x_telegram_init_data: str = Header(
        default=""
    )
):
    user = telegram_user(
        x_telegram_init_data
    )

    owner_id = int(
        user["id"]
    )

    slug = (
        secrets.token_urlsafe(8)
        .replace("-", "")
        .replace("_", "")
        .lower()
    )

    with SessionLocal() as db:

        try:
            business_data = x.model_dump(
                exclude={"hours"}
            )
            business_data["instagram_url"] = business_data.get("instagram_url") or ""
            business_data["reviews_url"] = business_data.get("reviews_url") or ""

            business = Business(
                owner_telegram_id=owner_id,
                slug=slug,
                **business_data
            )

            db.add(business)

            db.flush()

            for hour in x.hours:

                if not hour.active:
                    continue

                if hour.start >= hour.end:
                    raise HTTPException(
                        400,
                        f"Некорректный график для дня {hour.weekday}"
                    )

                working_hour = WorkingHour(
                    business_id=business.id,
                    **hour.model_dump()
                )

                db.add(
                    working_hour
                )

            db.commit()

            db.refresh(
                business
            )

            return business

        except HTTPException:
            db.rollback()
            raise

        except Exception as exc:

            db.rollback()

            print(
                "CREATE BUSINESS ERROR:",
                repr(exc)
            )

            raise HTTPException(
                500,
                "Не удалось создать бизнес"
            )
@app.delete("/admin/business/{business_id}")
def admin_delete_business(
    business_id: int,
    x_telegram_init_data: str = Header(default="")
):
    user = telegram_user(
        x_telegram_init_data
    )

    owner_id = int(
        user["id"]
    )

    with SessionLocal() as db:

        business = db.query(Business).filter(
            Business.id == business_id,
            Business.owner_telegram_id == owner_id
        ).first()

        if not business:
            raise HTTPException(
                404,
                "Business not found"
            )

        # ---------------------------------------------------------
        # Удаляем подписку этого конкретного бизнеса
        # ---------------------------------------------------------

        db.query(Subscription).filter(
            Subscription.business_id == business.id
        ).delete(
            synchronize_session=False
        )

        # ---------------------------------------------------------
        # Удаляем связанные данные
        # ---------------------------------------------------------

        db.query(SavedBusiness).filter(
            SavedBusiness.business_id == business.id
        ).delete(
            synchronize_session=False
        )

        db.query(Booking).filter(
            Booking.business_id == business.id
        ).delete(
            synchronize_session=False
        )

        db.query(BlockedSlot).filter(
            BlockedSlot.business_id == business.id
        ).delete(
            synchronize_session=False
        )

        specialist_ids = [
            int(row[0])
            for row in (
                db.query(Specialist.id)
                .filter(
                    Specialist.business_id == business.id
                )
                .all()
            )
        ]

        if specialist_ids:
            db.query(SpecialistService).filter(
                SpecialistService.specialist_id.in_(specialist_ids)
            ).delete(
                synchronize_session=False
            )

            db.query(SpecialistWorkingHour).filter(
                SpecialistWorkingHour.specialist_id.in_(specialist_ids)
            ).delete(
                synchronize_session=False
            )

        # The invite-link model is registered in staff_routes after app.py
        # finishes importing, so clean it by table name when it exists.
        if "specialist_telegram_links" in inspect(engine).get_table_names():
            db.execute(
                text(
                    "DELETE FROM specialist_telegram_links "
                    "WHERE business_id = :business_id"
                ),
                {"business_id": business.id},
            )

        db.query(Specialist).filter(
            Specialist.business_id == business.id
        ).delete(
            synchronize_session=False
        )

        db.query(WorkingHour).filter(
            WorkingHour.business_id == business.id
        ).delete(
            synchronize_session=False
        )

        db.query(Service).filter(
            Service.business_id == business.id
        ).delete(
            synchronize_session=False
        )

        db.delete(
            business
        )

        db.commit()

        return {
            "ok": True
        }
@app.get("/admin/business")
def admin_business(
    x_telegram_init_data: str = Header(default="")
):
    user = telegram_user(
        x_telegram_init_data
    )

    owner_id = int(
        user["id"]
    )

    with SessionLocal() as db:

        b = owner_business(
            db,
            owner_id
        )

        if not b:
            return None

        # Подписка принадлежит именно этому бизнесу
        subscription = owner_subscription(
            db,
            b.id
        )

        result = {
            "id": b.id,
            "owner_telegram_id": b.owner_telegram_id,
            "name": b.name,
            "slug": b.slug,
            "description": b.description,
            "business_image": b.business_image,
            "address": b.address,
            "phone": b.phone,
            "instagram_url": b.instagram_url or "",
            "reviews_url": b.reviews_url or "",
            "latitude": b.latitude,
            "longitude": b.longitude,
            "timezone": b.timezone,

            "subscription_active": (
                bool(subscription.active)
                if subscription
                else False
            ),

            "subscription_status": (
                subscription.status
                if subscription
                else "inactive"
            ),

            "subscription_plan": (
                subscription.plan
                if subscription
                else "free"
            ),

            "subscription_expires_at": (
                subscription.expires_at
                if subscription
                else None
            ),

            "services_limit": (
                subscription.current_services_limit
                if subscription and subscription.active
                else 0
            ),

            "pending_services_limit": (
                subscription.pending_services_limit
                if subscription
                else None
            ),

            "current_price": (
                float(subscription.current_price)
                if subscription
                and subscription.current_price is not None
                else 0.0
            ),

            "pending_price": (
                float(subscription.pending_price)
                if subscription
                and subscription.pending_price is not None
                else None
            )
        }

        return result
@app.get("/admin/services")
def admin_services(
    x_telegram_init_data: str = Header(default="")
):
    user = telegram_user(
        x_telegram_init_data
    )

    owner_id = int(
        user["id"]
    )

    with SessionLocal() as db:

        b = owner_business(
            db,
            owner_id
        )

        if not b:
            return []

        services = (
            db.query(Service)
            .filter(
                Service.business_id == b.id,
                Service.active == True
            )
            .order_by(
                Service.id.desc()
            )
            .all()
        )

        allowed_ids = set(
            service_ids_available_under_plan(
                db,
                b.id,
            )
        )

        return [
            {
                **{
                    column.name: getattr(
                        service,
                        column.name
                    )
                    for column
                    in Service.__table__.columns
                },
                "available_under_plan":
                    service.id in allowed_ids,
            }
            for service in services
        ]


@app.post("/admin/services")
def admin_add_service(
    x: ServiceIn,
    x_telegram_init_data: str = Header(default="")
):
    user = telegram_user(
        x_telegram_init_data
    )

    owner_id = int(
        user["id"]
    )

    with SessionLocal() as db:

        b = owner_business(
            db,
            owner_id
        )

        if not b:
            raise HTTPException(
                400,
                "Create business first"
            )

        # ---------------------------------------------------------
        # Подписка принадлежит именно этому бизнесу
        # ---------------------------------------------------------

        subscription = owner_subscription(
            db,
            b.id
        )

        limits = subscription_limits(
            subscription
        )

        max_services = limits[
            "max_services"
        ]

        # ---------------------------------------------------------
        # Считаем только активные услуги
        # ---------------------------------------------------------

        services_count = (
            db.query(Service)
            .filter(
                Service.business_id == b.id,
                Service.active == True
            )
            .count()
        )

        
        # ---------------------------------------------------------
        # Проверяем текущий лимит
        # ---------------------------------------------------------

        if services_count >= max_services:
            raise HTTPException(
                403,
                (
                    f"Достигнут лимит услуг: "
                    f"{max_services}"
                )
            )

        # ---------------------------------------------------------
        # Создаём услугу
        # ---------------------------------------------------------

        s = Service(
            business_id=b.id,
            **x.model_dump()
        )

        db.add(s)

        db.commit()

        db.refresh(s)

        return s

@app.patch("/admin/services/{service_id}")
def admin_edit_service(service_id: int, x: ServiceIn, x_telegram_init_data: str = Header(default="")):
    user = telegram_user(x_telegram_init_data)
    with SessionLocal() as db:
        b = owner_business(db, int(user["id"])); s = db.get(Service, service_id)
        if not b or not s or s.business_id != b.id: raise HTTPException(404, "Service not found")

        if x.active and not s.active:
            subscription = owner_subscription(
                db,
                b.id
            )

            max_services = subscription_limits(
                subscription
            )["max_services"]

            services_count = (
                db.query(Service)
                .filter(
                    Service.business_id == b.id,
                    Service.active == True
                )
                .count()
            )

            if services_count >= max_services:
                raise HTTPException(
                    403,
                    f"Достигнут лимит услуг: {max_services}"
                )

        for k,v in x.model_dump().items(): setattr(s,k,v)
        db.commit(); db.refresh(s); return s

@app.delete("/admin/services/{service_id}")
def admin_delete_service(service_id: int, x_telegram_init_data: str = Header(default="")):
    user = telegram_user(x_telegram_init_data)
    with SessionLocal() as db:
        b=owner_business(db,int(user["id"])); s=db.get(Service,service_id)
        if not b or not s or s.business_id != b.id: raise HTTPException(404,"Service not found")
        s.active=False; db.commit(); return {"ok":True}

@app.get("/admin/hours")
def admin_hours(x_telegram_init_data: str = Header(default="")):
    user=telegram_user(x_telegram_init_data)
    with SessionLocal() as db:
        b=owner_business(db,int(user["id"]))
        if not b:return []
        return db.query(WorkingHour).filter_by(business_id=b.id).order_by(WorkingHour.weekday,WorkingHour.start).all()

@app.post("/admin/hours")
def admin_add_hour(
    x: WorkingHourIn,
    x_telegram_init_data: str = Header(default="")
):
    user = telegram_user(
        x_telegram_init_data
    )

    if x.start >= x.end:
        raise HTTPException(
            400,
            "Start must be before end"
        )

    with SessionLocal() as db:
        b = owner_business(
            db,
            int(user["id"])
        )

        if not b:
            raise HTTPException(
                400,
                "Create business first"
            )

        existing = (
            db.query(WorkingHour)
            .filter(
                WorkingHour.business_id == b.id,
                WorkingHour.weekday == x.weekday
            )
            .all()
        )

        for item in existing:
            db.delete(item)

        h = WorkingHour(
            business_id=b.id,
            **x.model_dump()
        )

        db.add(h)
        db.commit()
        db.refresh(h)

        return h

@app.delete("/admin/hours/{hour_id}")
def admin_delete_hour(hour_id:int,x_telegram_init_data:str=Header(default="")):
    user=telegram_user(x_telegram_init_data)
    with SessionLocal() as db:
        b=owner_business(db,int(user["id"]));h=db.get(WorkingHour,hour_id)
        if not b or not h or h.business_id!=b.id:raise HTTPException(404,"Hour not found")
        db.delete(h);db.commit();return {"ok":True}

@app.get("/admin/blocks")
def admin_blocks(
    day: Optional[date] = None,
    x_telegram_init_data: str = Header(default="")
):
    user = telegram_user(x_telegram_init_data)

    with SessionLocal() as db:
        b = owner_business(
            db,
            int(user["id"])
        )

        if not b:
            return []

        q = db.query(BlockedSlot).filter(
            BlockedSlot.business_id == b.id
        )

        if day:
            q = q.filter(BlockedSlot.day == day)

        rows = q.order_by(
            BlockedSlot.day,
            BlockedSlot.start
        ).all()

        specialist_ids = {
            int(row.specialist_id)
            for row in rows
            if row.specialist_id is not None
        }
        specialist_names = {
            item.id: item.name
            for item in (
                db.query(Specialist)
                .filter(Specialist.id.in_(specialist_ids))
                .all()
                if specialist_ids
                else []
            )
        }

        return [
            {
                "id": row.id,
                "business_id": row.business_id,
                "specialist_id": row.specialist_id,
                "specialist_name": (
                    specialist_names.get(row.specialist_id)
                    if row.specialist_id is not None
                    else None
                ),
                "day": row.day.isoformat(),
                "start": row.start.strftime("%H:%M"),
                "end": row.end.strftime("%H:%M"),
                "start_at_utc": (
                    row.start_at_utc.isoformat()
                    if row.start_at_utc
                    else None
                ),
                "end_at_utc": (
                    row.end_at_utc.isoformat()
                    if row.end_at_utc
                    else None
                ),
                "reason": row.reason or "",
                "created_by": row.created_by or "owner",
            }
            for row in rows
        ]


@app.post("/admin/blocks")
def admin_block(
    x: BlockIn,
    x_telegram_init_data: str = Header(default="")
):
    user = telegram_user(x_telegram_init_data)

    if x.start >= x.end:
        raise HTTPException(400, "Invalid time range")

    with SessionLocal() as db:
        b = owner_business(db, int(user["id"]))
        if not b:
            raise HTTPException(400, "Create business first")

        if x.specialist_id is not None:
            specialist = (
                db.query(Specialist)
                .filter(
                    Specialist.id == x.specialist_id,
                    Specialist.business_id == b.id,
                )
                .first()
            )
            if not specialist:
                raise HTTPException(404, "Specialist not found")

        business_zone = _bookly_zone(b.timezone)

        if not is_free(
            db,
            b.id,
            x.day,
            x.start,
            x.end,
            b.timezone,
            x.specialist_id,
        ):
            raise HTTPException(
                409,
                "Time overlaps an existing booking or block",
            )

        start_local = datetime.combine(
            x.day,
            x.start,
            tzinfo=business_zone,
        )
        end_local = datetime.combine(
            x.day,
            x.end,
            tzinfo=business_zone,
        )

        z = BlockedSlot(
            business_id=b.id,
            specialist_id=x.specialist_id,
            day=x.day,
            start=x.start,
            end=x.end,
            reason=x.reason,
            created_by="owner",
            start_at_utc=_bookly_to_utc(start_local),
            end_at_utc=_bookly_to_utc(end_local),
        )

        db.add(z)
        db.commit()
        db.refresh(z)
        return {
            "id": z.id,
            "business_id": z.business_id,
            "specialist_id": z.specialist_id,
            "day": z.day.isoformat(),
            "start": z.start.strftime("%H:%M"),
            "end": z.end.strftime("%H:%M"),
            "reason": z.reason or "",
            "created_by": z.created_by or "owner",
        }


@app.delete("/admin/blocks/{block_id}")
def admin_delete_block(
    block_id: int,
    x_telegram_init_data: str = Header(default="")
):
    user = telegram_user(x_telegram_init_data)

    with SessionLocal() as db:
        b = owner_business(db, int(user["id"]))
        z = db.get(BlockedSlot, block_id)

        if (
            not b
            or not z
            or z.business_id != b.id
        ):
            raise HTTPException(404, "Block not found")

        business_zone = _bookly_zone(b.timezone)
        block_end = datetime.combine(
            z.day,
            z.end,
            tzinfo=business_zone,
        )

        if block_end <= datetime.now(business_zone):
            raise HTTPException(
                409,
                "Historical blocks cannot be deleted",
            )

        db.delete(z)
        db.commit()
        return {"ok": True}


@app.get("/admin/bookings")
def admin_bookings(
    day: Optional[date] = None,
    specialist_id: Optional[int] = None,
    x_telegram_init_data: str = Header(default="")
):
    user = telegram_user(x_telegram_init_data)

    with SessionLocal() as db:
        b = owner_business(db, int(user["id"]))
        if not b:
            return []

        q = db.query(Booking).filter(
            Booking.business_id == b.id
        )

        if day:
            q = q.filter(Booking.day == day)

        if specialist_id is not None:
            q = q.filter(
                Booking.specialist_id == specialist_id
            )

        rows = q.order_by(
            Booking.day,
            Booking.start
        ).all()

        service_ids = {
            int(row.service_id)
            for row in rows
            if row.service_id is not None
        }
        specialist_ids = {
            int(row.specialist_id)
            for row in rows
            if row.specialist_id is not None
        }

        service_names = {
            item.id: item.name
            for item in (
                db.query(Service)
                .filter(Service.id.in_(service_ids))
                .all()
                if service_ids
                else []
            )
        }
        specialist_names = {
            item.id: item.name
            for item in (
                db.query(Specialist)
                .filter(Specialist.id.in_(specialist_ids))
                .all()
                if specialist_ids
                else []
            )
        }

        return [
            {
                "id": row.id,
                "business_id": row.business_id,
                "service_id": row.service_id,
                "service_name": service_names.get(row.service_id, ""),
                "specialist_id": row.specialist_id,
                "specialist_name": (
                    specialist_names.get(row.specialist_id, "")
                    if row.specialist_id is not None
                    else ""
                ),
                "client_telegram_id": row.client_telegram_id,
                "client_name": row.client_name,
                "client_phone": row.client_phone or "",
                "day": row.day.isoformat(),
                "start": row.start.strftime("%H:%M"),
                "end": row.end.strftime("%H:%M"),
                "start_at_utc": (
                    row.start_at_utc.isoformat()
                    if row.start_at_utc
                    else None
                ),
                "end_at_utc": (
                    row.end_at_utc.isoformat()
                    if row.end_at_utc
                    else None
                ),
                "client_timezone": row.client_timezone or "UTC",
                "status": row.status,
                "created_at": (
                    row.created_at.isoformat()
                    if row.created_at
                    else None
                ),
            }
            for row in rows
        ]


@app.get("/admin/statistics")
def admin_statistics(
    specialist_id: Optional[int] = None,
    x_telegram_init_data: str = Header(default="")
):
    user = telegram_user(x_telegram_init_data)
    owner_id = int(user["id"])

    with SessionLocal() as db:
        business = owner_business(
            db,
            owner_id
        )

        if not business:
            return {
                "today": {
                    "bookings": 0,
                    "revenue_by_currency": {}
                },
                "week": {
                    "bookings": 0,
                    "revenue_by_currency": {}
                },
                "month": {
                    "bookings": 0,
                    "revenue_by_currency": {}
                },
                "total": 0,
                "completed": 0,
                "cancelled": 0,
                "confirmed": 0,
                "daily": [],
                "top_services": []
            }

        bookings_query = (
            db.query(Booking)
            .filter(
                Booking.business_id == business.id
            )
        )

        selected_specialist = None
        if specialist_id is not None:
            selected_specialist = (
                db.query(Specialist)
                .filter(
                    Specialist.id == specialist_id,
                    Specialist.business_id == business.id,
                )
                .first()
            )
            if not selected_specialist:
                raise HTTPException(
                    404,
                    "Specialist not found",
                )

            bookings_query = bookings_query.filter(
                Booking.specialist_id == specialist_id
            )

        bookings = (
            bookings_query
            .order_by(
                Booking.day,
                Booking.start
            )
            .all()
        )

        services = {
            service.id: service
            for service in (
                db.query(Service)
                .filter(
                    Service.business_id ==
                    business.id
                )
                .all()
            )
        }

        business_zone = _bookly_zone(business.timezone)
        now = datetime.now(business_zone).replace(tzinfo=None)
        today = now.date()

        week_start = (
            today -
            timedelta(
                days=today.weekday()
            )
        )

        month_start = today.replace(
            day=1
        )

        today_bookings = 0
        week_bookings = 0
        month_bookings = 0

        today_revenue = {}
        week_revenue = {}
        month_revenue = {}

        completed = 0
        cancelled = 0
        confirmed = 0

        daily_map = {}

        for offset in range(30):
            current_day = (
                today -
                timedelta(
                    days=29 - offset
                )
            )

            daily_map[
                current_day.isoformat()
            ] = {
                "date":
                    current_day.isoformat(),
                "bookings": 0,
                "revenue_by_currency": {}
            }

        service_stats = {}

        def add_revenue(
            target: dict,
            currency: str,
            amount: Decimal
        ):
            currency = (
                str(currency or "UZS")
                .upper()
            )

            target[currency] = float(
                Decimal(
                    str(
                        target.get(
                            currency,
                            0
                        )
                    )
                ) + amount
            )

        for booking in bookings:
            booking_day = booking.day

            service = services.get(
                booking.service_id
            )

            currency = (
                service.currency
                if service and service.currency
                else "UZS"
            )

            try:
                price = Decimal(
                    str(
                        service.price
                        if service
                        else 0
                    )
                )
            except Exception:
                price = Decimal("0")

            if booking.status == "cancelled":
                cancelled += 1
                continue

            confirmed += 1

            if booking_day == today:
                today_bookings += 1

                add_revenue(
                    today_revenue,
                    currency,
                    price
                )

            if booking_day >= week_start:
                week_bookings += 1

                add_revenue(
                    week_revenue,
                    currency,
                    price
                )

            if booking_day >= month_start:
                month_bookings += 1

                add_revenue(
                    month_revenue,
                    currency,
                    price
                )

            day_key = booking_day.isoformat()

            if day_key in daily_map:
                daily_map[
                    day_key
                ]["bookings"] += 1

                add_revenue(
                    daily_map[
                        day_key
                    ][
                        "revenue_by_currency"
                    ],
                    currency,
                    price
                )

            booking_end = datetime.combine(
                booking.day,
                booking.end
            )

            if booking_end <= now:
                completed += 1

            service_id = booking.service_id

            if service_id not in service_stats:
                service_stats[service_id] = {
                    "id": service_id,
                    "name": (
                        service.name
                        if service
                        else "Unknown service"
                    ),
                    "bookings": 0,
                    "revenue_by_currency": {}
                }

            service_stats[
                service_id
            ]["bookings"] += 1

            add_revenue(
                service_stats[
                    service_id
                ]["revenue_by_currency"],
                currency,
                price
            )

        top_services = sorted(
            service_stats.values(),
            key=lambda item: (
                item["bookings"],
                sum(
                    item[
                        "revenue_by_currency"
                    ].values()
                )
            ),
            reverse=True
        )[:5]

        return {
            "specialist": (
                {
                    "id": selected_specialist.id,
                    "name": selected_specialist.name,
                    "position": selected_specialist.position or "",
                }
                if selected_specialist
                else None
            ),
            "today": {
                "bookings":
                    today_bookings,
                "revenue_by_currency":
                    today_revenue
            },
            "week": {
                "bookings":
                    week_bookings,
                "revenue_by_currency":
                    week_revenue
            },
            "month": {
                "bookings":
                    month_bookings,
                "revenue_by_currency":
                    month_revenue
            },
            "total":
                len(bookings),

            "completed":
                completed,

            "cancelled":
                cancelled,

            "confirmed":
                confirmed,

            "daily":
                list(
                    daily_map.values()
                ),

            "top_services":
                top_services
        }
@app.post("/admin/bookings/{booking_id}/cancel")
def admin_cancel_booking(
    booking_id: int,
    x_telegram_init_data: str = Header(default="")
):
    user = telegram_user(x_telegram_init_data)
    owner_id = int(user["id"])

    with SessionLocal() as db:
        business = owner_business(
            db,
            owner_id
        )

        booking = db.get(
            Booking,
            booking_id
        )

        if (
            not business
            or not booking
            or booking.business_id != business.id
        ):
            raise HTTPException(
                404,
                "Booking not found"
            )

        if booking.status == "cancelled":
            return {"ok": True}

        booking.status = "cancelled"
        db.commit()

        if booking.client_telegram_id:
            client_zone = _bookly_zone(booking.client_timezone)
            if booking.start_at_utc and booking.end_at_utc:
                client_start = _bookly_from_utc(booking.start_at_utc, booking.client_timezone or "UTC")
                client_end = _bookly_from_utc(booking.end_at_utc, booking.client_timezone or "UTC")
                display_day = client_start.date().isoformat() if client_start else booking.day.isoformat()
                display_start = client_start.strftime('%H:%M') if client_start else booking.start.strftime('%H:%M')
                display_end = client_end.strftime('%H:%M') if client_end else booking.end.strftime('%H:%M')
            else:
                display_day = booking.day.isoformat()
                display_start = booking.start.strftime('%H:%M')
                display_end = booking.end.strftime('%H:%M')
            telegram_api(
                "sendMessage",
                {
                    "chat_id": booking.client_telegram_id,
                    "text": (
                        "❌ <b>Ваша запись отменена бизнесом</b>\n\n"
                        f"📅 {display_day}\n"
                        f"🕐 {display_start}–"
                        f"{display_end}\n"
                        f"📞 {business.phone or 'Номер телефона не указан'}\n\n"
                        "Пожалуйста, свяжитесь с бизнесом, "
                        "если хотите выбрать другое время."
                    ),
                    "parse_mode": "HTML"
                }
            )

        notify_specialist_booking_cancelled(
            db,
            booking,
            cancelled_by_business=True,
        )

        return {
            "ok": True
        }
@app.post("/admin/bookings")
def admin_create_booking(
    x: AdminBookingIn,
    x_telegram_init_data: str = Header(default="")
):
    user = telegram_user(x_telegram_init_data)
    owner_id = int(user["id"])

    with SessionLocal() as db:
        business = owner_business(db, owner_id)

        if not business:
            raise HTTPException(
                400,
                "Create business first"
            )

        service = db.get(Service, x.service_id)

        if not service or service.business_id != business.id or not service.active:
            raise HTTPException(
                404,
                "Service not found"
            )

        specialist = None
        if x.specialist_id is not None:
            specialist = db.get(Specialist, x.specialist_id)
            assigned = db.query(SpecialistService).filter(
                SpecialistService.specialist_id == x.specialist_id,
                SpecialistService.service_id == x.service_id,
            ).first()

            if (
                not specialist
                or specialist.business_id != business.id
                or not specialist.active
                or not assigned
            ):
                raise HTTPException(
                    404,
                    "Specialist not found"
                )

        business_zone = _bookly_zone(business.timezone)
        now_business = datetime.now(business_zone).replace(tzinfo=None)

        start_dt = datetime.combine(
            x.day,
            x.start
        )

        end_dt = start_dt + timedelta(
            minutes=service.duration_min
        )

        if start_dt <= now_business:
            raise HTTPException(
                400,
                "Нельзя создать запись на прошедшее время"
            )

        if not is_free(
            db,
            business.id,
            x.day,
            x.start,
            end_dt.time(),
            business.timezone,
            x.specialist_id
        ):
            raise HTTPException(
                400,
                "Это время уже занято или заблокировано"
            )

        business_zone = _bookly_zone(business.timezone)
        start_local = datetime.combine(x.day, x.start, tzinfo=business_zone)
        end_local = start_local + timedelta(minutes=service.duration_min)

        booking = Booking(
            business_id=business.id,
            service_id=service.id,
            specialist_id=x.specialist_id,
            client_telegram_id=0,
            client_name=x.client_name.strip(),
            client_phone=x.client_phone.strip(),
            day=x.day,
            start=x.start,
            end=end_dt.time(),
            start_at_utc=_bookly_to_utc(start_local),
            end_at_utc=_bookly_to_utc(end_local),
            client_timezone=business.timezone or "Asia/Tashkent",
            status="confirmed"
        )

        db.add(booking)
        db.commit()
        db.refresh(booking)

        # Manual bookings created by the owner should follow the same
        # notification routing as customer-created bookings.
        if x.specialist_id is not None:
            notify_owner_new_booking(
                db,
                booking,
                service,
            )

        return booking

# ---------- client ----------
def get_work_windows(db, business_id:int, day:date, specialist_id: Optional[int] = None):
    if specialist_id is not None:
        specialist_hours = (
            db.query(SpecialistWorkingHour)
            .filter_by(specialist_id=specialist_id, weekday=day.weekday(), active=True)
            .order_by(SpecialistWorkingHour.start)
            .all()
        )
        if specialist_hours:
            return [(h.start, h.end) for h in specialist_hours]

    hours = (
        db.query(WorkingHour)
        .filter_by(business_id=business_id, weekday=day.weekday(), active=True)
        .order_by(WorkingHour.start)
        .all()
    )
    if hours:
        return [(h.start, h.end) for h in hours]
    return [(time(9,0),time(18,0))]

def is_free(
    db,
    business_id: int,
    day: date,
    st: time,
    en: time,
    timezone_name: str | None = None,
    specialist_id: Optional[int] = None
):
    zone = _bookly_zone(timezone_name or "Asia/Tashkent")
    start_at_utc = _bookly_to_utc(datetime.combine(day, st, tzinfo=zone))
    end_at_utc = _bookly_to_utc(datetime.combine(day, en, tzinfo=zone))

    booking_query = db.query(Booking).filter(
        Booking.business_id == business_id,
        Booking.status == "confirmed",
        Booking.start_at_utc.is_not(None),
        Booking.end_at_utc.is_not(None),
        Booking.start_at_utc < end_at_utc,
        Booking.end_at_utc > start_at_utc,
    )
    if specialist_id is not None:
        booking_query = booking_query.filter(
            (Booking.specialist_id == specialist_id) | Booking.specialist_id.is_(None)
        )
    if booking_query.first():
        return False

    blocked_query = db.query(BlockedSlot).filter(
        BlockedSlot.business_id == business_id,
        BlockedSlot.start_at_utc.is_not(None),
        BlockedSlot.end_at_utc.is_not(None),
        BlockedSlot.start_at_utc < end_at_utc,
        BlockedSlot.end_at_utc > start_at_utc,
    )
    if specialist_id is not None:
        blocked_query = blocked_query.filter(
            (BlockedSlot.specialist_id == specialist_id)
            | BlockedSlot.specialist_id.is_(None)
        )
    else:
        blocked_query = blocked_query.filter(
            BlockedSlot.specialist_id.is_(None)
        )

    if blocked_query.first():
        return False

    legacy_booking_query = db.query(Booking).filter(
        Booking.business_id == business_id,
        Booking.day == day,
        Booking.status == "confirmed",
        Booking.start_at_utc.is_(None),
        Booking.start < en,
        Booking.end > st,
    )
    if specialist_id is not None:
        legacy_booking_query = legacy_booking_query.filter(
            (Booking.specialist_id == specialist_id) | Booking.specialist_id.is_(None)
        )
    legacy_booking = legacy_booking_query.first()

    legacy_block_query = db.query(BlockedSlot).filter(
        BlockedSlot.business_id == business_id,
        BlockedSlot.day == day,
        BlockedSlot.start_at_utc.is_(None),
        BlockedSlot.start < en,
        BlockedSlot.end > st,
    )
    if specialist_id is not None:
        legacy_block_query = legacy_block_query.filter(
            (BlockedSlot.specialist_id == specialist_id)
            | BlockedSlot.specialist_id.is_(None)
        )
    else:
        legacy_block_query = legacy_block_query.filter(
            BlockedSlot.specialist_id.is_(None)
        )

    legacy_block = legacy_block_query.first()
    return not legacy_booking and not legacy_block

@app.get("/businesses/{business_id}/specialists")
def business_specialists(business_id: int, service_id: Optional[int] = None):
    with SessionLocal() as db:
        business = db.get(Business, business_id)
        if not business:
            raise HTTPException(404, "Not found")

        query = db.query(Specialist).filter(
            Specialist.business_id == business_id,
            Specialist.active == True
        )

        if service_id is not None:
            service = db.get(Service, service_id)
            if (
                not service
                or service.business_id != business_id
                or not service.active
                or not service_available_under_plan(
                    db,
                    business_id,
                    service_id,
                )
            ):
                raise HTTPException(404, "Not found")
            query = query.join(
                SpecialistService,
                SpecialistService.specialist_id == Specialist.id
            ).filter(SpecialistService.service_id == service_id)

        rows = query.order_by(Specialist.id.asc()).all()

        result = []
        for item in rows:
            service_ids = [
                int(row[0])
                for row in db.query(SpecialistService.service_id)
                .filter(SpecialistService.specialist_id == item.id)
                .all()
            ]
            result.append({
                "id": item.id,
                "name": item.name,
                "position": item.position or "",
                "description": item.description or "",
                "photo": item.photo or "",
                "service_ids": service_ids,
            })
        return result

@app.get("/businesses/{slug}")
def get_business(slug: str):
    with SessionLocal() as db:
        b = db.query(Business).filter_by(slug=slug).first()

        if not b:
            raise HTTPException(
                404,
                "Business not found"
            )

        if not b.subscription_active:
            raise HTTPException(
                403,
                "Business is not active"
            )

        allowed_service_ids = (
            service_ids_available_under_plan(
                db,
                b.id,
            )
        )

        services = (
            db.query(Service)
            .filter(
                Service.business_id == b.id,
                Service.active == True,
                Service.id.in_(
                    allowed_service_ids
                )
                if allowed_service_ids
                else False,
            )
            .order_by(Service.id.asc())
            .all()
        )

        return {
            "business": b,
            "services": services
        }


@app.get("/businesses/{slug}/qr.png")
def business_qr(
    slug: str,
    bot_username: str = "skedwoo_bot"
):
    with SessionLocal() as db:
        b = db.query(Business).filter_by(
            slug=slug
        ).first()

        if not b:
            raise HTTPException(
                404,
                "Business not found"
            )

        if not b.subscription_active:
            raise HTTPException(
                403,
                "Business is not active"
            )

    bot_username = bot_username.strip().lstrip("@")

    client_link = (
        f"https://t.me/"
        f"{bot_username}"
        f"?startapp={slug}"
    )

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4
    )

    qr.add_data(client_link)
    qr.make(fit=True)

    image = qr.make_image(
        fill_color="black",
        back_color="white"
    )

    buffer = io.BytesIO()
    image.save(
        buffer,
        format="PNG"
    )

    return Response(
        content=buffer.getvalue(),
        media_type="image/png",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{slug}-bookly-qr.png"'
            ),
            "Access-Control-Allow-Origin": "*"
        }
    )
@app.get("/businesses/{business_id}/availability")
def availability(
    business_id: int,
    service_id: int,
    day: date,
    time_zone: Optional[str] = None,
    specialist_id: Optional[int] = None
):
    with SessionLocal() as db:
        b = db.get(Business, business_id)
        s = db.get(Service, service_id)
        if (
            not b
            or not b.subscription_active
            or not s
            or s.business_id != business_id
            or not s.active
            or not service_available_under_plan(
                db,
                business_id,
                service_id,
            )
        ):
            raise HTTPException(404, "Not found")

        if specialist_id is not None:
            specialist = db.get(Specialist, specialist_id)
            assigned = db.query(SpecialistService).filter(
                SpecialistService.specialist_id == specialist_id,
                SpecialistService.service_id == service_id
            ).first()
            if not specialist or specialist.business_id != business_id or not specialist.active or not assigned:
                raise HTTPException(404, "Specialist not found")

        business_zone = _bookly_zone(b.timezone)
        client_zone = _bookly_zone(time_zone or b.timezone)
        now_business = datetime.now(business_zone)

        bookings = db.query(
            Booking.start_at_utc,
            Booking.end_at_utc,
            Booking.day,
            Booking.start,
            Booking.end,
            Booking.specialist_id
        ).filter(
            Booking.business_id == business_id,
            Booking.status == "confirmed"
        ).all()

        blocked_slots = db.query(
            BlockedSlot.start_at_utc,
            BlockedSlot.end_at_utc,
            BlockedSlot.day,
            BlockedSlot.start,
            BlockedSlot.end,
            BlockedSlot.specialist_id,
        ).filter(
            BlockedSlot.business_id == business_id
        ).all()

        slots = []
        slot_items_by_time = {}
        seen = set()
        for business_day in (day - timedelta(days=1), day, day + timedelta(days=1)):
            for win_start, win_end in get_work_windows(db, business_id, business_day, specialist_id):
                cursor = datetime.combine(business_day, win_start, tzinfo=business_zone)
                endday = datetime.combine(business_day, win_end, tzinfo=business_zone)
                while cursor + timedelta(minutes=s.duration_min) <= endday:
                    slot_end = cursor + timedelta(minutes=s.duration_min)
                    if business_day == now_business.date() and cursor <= now_business:
                        cursor += timedelta(minutes=s.duration_min)
                        continue

                    start_utc = _bookly_to_utc(cursor)
                    end_utc = _bookly_to_utc(slot_end)
                    occupied = False

                    for (
                        bs,
                        be,
                        legacy_day,
                        legacy_start,
                        legacy_end,
                        booking_specialist_id,
                    ) in bookings:
                        if (
                            specialist_id is not None
                            and booking_specialist_id not in (
                                None,
                                specialist_id,
                            )
                        ):
                            continue

                        if bs is not None and be is not None:
                            if bs < end_utc and be > start_utc:
                                occupied = True
                                break
                        elif (
                            legacy_day == business_day
                            and legacy_start < slot_end.time()
                            and legacy_end > cursor.time()
                        ):
                            occupied = True
                            break

                    if not occupied:
                        for (
                            bs,
                            be,
                            legacy_day,
                            legacy_start,
                            legacy_end,
                            block_specialist_id,
                        ) in blocked_slots:
                            # A business-wide block (specialist_id NULL)
                            # applies to everyone. A personal block applies
                            # only to that specialist.
                            if specialist_id is not None:
                                if block_specialist_id not in (
                                    None,
                                    specialist_id,
                                ):
                                    continue
                            elif block_specialist_id is not None:
                                continue

                            if bs is not None and be is not None:
                                if bs < end_utc and be > start_utc:
                                    occupied = True
                                    break
                            elif (
                                legacy_day == business_day
                                and legacy_start < slot_end.time()
                                and legacy_end > cursor.time()
                            ):
                                occupied = True
                                break

                    client_local = (
                        start_utc
                        .replace(tzinfo=timezone.utc)
                        .astimezone(client_zone)
                    )

                    if client_local.date() == day:
                        value = client_local.strftime("%H:%M")

                        previous = slot_items_by_time.get(value)
                        is_available = not occupied

                        # If timezone conversion ever produces the same
                        # displayed clock time twice, keep it available when
                        # at least one real slot is available.
                        if (
                            previous is None
                            or (
                                is_available
                                and not previous["available"]
                            )
                        ):
                            slot_items_by_time[value] = {
                                "time": value,
                                "available": is_available,
                            }

                        if is_available and value not in seen:
                            seen.add(value)
                            slots.append(value)

                    cursor += timedelta(minutes=s.duration_min)

        slots.sort()
        slot_items = sorted(
            slot_items_by_time.values(),
            key=lambda item: item["time"],
        )

        return {
            "slots": slots,
            "slot_items": slot_items,
        }

@app.post("/bookings")
def create_booking(
    x: BookingIn,
    x_telegram_init_data: str = Header(default="")
):
    user = telegram_user(x_telegram_init_data)

    # Client identity always comes from signed Telegram initData.
    x.client_telegram_id = int(user["id"])

    with SessionLocal() as db:
        b = db.get(Business, x.business_id)
        s = db.get(Service, x.service_id)

        if (
            not b
            or not s
            or s.business_id != x.business_id
            or not s.active
        ):
            raise HTTPException(404, "Not found")

        if not b.subscription_active:
            raise HTTPException(403, "Business inactive")

        if not service_available_under_plan(
            db,
            b.id,
            s.id,
        ):
            raise HTTPException(
                403,
                "Service is outside the current package limit"
            )

        if x.specialist_id is not None:
            specialist = db.get(Specialist, x.specialist_id)
            assigned = db.query(SpecialistService).filter(
                SpecialistService.specialist_id == x.specialist_id,
                SpecialistService.service_id == x.service_id
            ).first()
            if not specialist or specialist.business_id != x.business_id or not specialist.active or not assigned:
                raise HTTPException(404, "Specialist not found")

        client_zone = _bookly_zone(x.client_timezone)
        selected_local = datetime.combine(
            x.day,
            x.start,
            tzinfo=client_zone
        )
        start_at_utc = _bookly_to_utc(selected_local)
        end_at_utc = start_at_utc + timedelta(minutes=s.duration_min)

        business_zone = _bookly_zone(b.timezone)
        business_start = start_at_utc.replace(
            tzinfo=timezone.utc
        ).astimezone(business_zone)
        business_end = end_at_utc.replace(
            tzinfo=timezone.utc
        ).astimezone(business_zone)

        if not is_free(
            db,
            b.id,
            business_start.date(),
            business_start.time(),
            business_end.time(),
            b.timezone,
            x.specialist_id
        ):
            raise HTTPException(
                409,
                "This time is no longer available"
            )

        business_zone = _bookly_zone(b.timezone)
        start_local = datetime.combine(x.day, x.start, tzinfo=business_zone)
        end_local = start_local + timedelta(minutes=s.duration_min)

        booking = Booking(
            business_id=x.business_id,
            service_id=x.service_id,
            specialist_id=x.specialist_id,
            client_telegram_id=x.client_telegram_id,
            client_name=x.client_name,
            client_phone=x.client_phone,
            day=business_start.date(),
            start=business_start.time(),
            end=business_end.time(),
            start_at_utc=start_at_utc,
            end_at_utc=end_at_utc,
            client_timezone=x.client_timezone,
            status="confirmed"
        )

        db.add(booking)
        db.commit()
        db.refresh(booking)

        # Уведомление владельцу
        notify_owner_new_booking(
            db,
            booking,
            s
        )

                  # Уведомление клиенту: показываем дату и время в timezone клиента.
        if booking.start_at_utc and booking.end_at_utc:
            client_display_start = _bookly_from_utc(
                booking.start_at_utc,
                booking.client_timezone or "UTC"
            )
            client_display_end = _bookly_from_utc(
                booking.end_at_utc,
                booking.client_timezone or "UTC"
            )

            display_day = (
                client_display_start.date().isoformat()
                if client_display_start
                else booking.day.isoformat()
            )

            display_start = (
                client_display_start.strftime("%H:%M")
                if client_display_start
                else booking.start.strftime("%H:%M")
            )

            display_end = (
                client_display_end.strftime("%H:%M")
                if client_display_end
                else booking.end.strftime("%H:%M")
            )
        else:
            display_day = booking.day.isoformat()
            display_start = booking.start.strftime("%H:%M")
            display_end = booking.end.strftime("%H:%M")

        telegram_api(
            "sendMessage",
            {
                "chat_id": booking.client_telegram_id,
                "text": (
                    "✅ <b>Вы успешно записаны!</b>\n\n"
                    f"💈 {s.name}\n"
                    f"📅 {display_day}\n"
                    f"🕐 {display_start}–"
                    f"{display_end}\n"
                    f"📞 Ваш номер: {booking.client_phone}\n"
                    f"☎️ Связаться: {b.phone or 'номер не указан'}\n"
                    f"📍 {b.address or 'Адрес не указан'}\n\n"
                    "Ждём вас!"
                ),
                "parse_mode": "HTML"
            }
        )

        return booking
@app.post("/bookings/{booking_id}/cancel")
def cancel_booking(booking_id:int,x_telegram_init_data:str=Header(default="")):
    user=telegram_user(x_telegram_init_data);uid=int(user["id"])
    with SessionLocal() as db:
        x=db.get(Booking,booking_id)
        if not x:raise HTTPException(404,"Booking not found")
        if x.client_telegram_id!=uid:raise HTTPException(403,"Not your booking")
        x.status="cancelled";db.commit()
        b=db.get(Business,x.business_id)
        telegram_api("sendMessage", {"chat_id":b.owner_telegram_id,"text":f"❌ <b>Запись отменена</b>\n\n👤 {x.client_name}\n📅 {x.day.isoformat()}\n🕐 {x.start.strftime('%H:%M')}–{x.end.strftime('%H:%M')}\n🆔 #{x.id}","parse_mode":"HTML"}) if b else None
        notify_specialist_booking_cancelled(db, x)
        return {"ok":True}

@app.get("/my/saved-businesses")
def my_saved_businesses(
    x_telegram_init_data: str = Header(
        default=""
    )
):
    user = telegram_user(
        x_telegram_init_data
    )

    uid = int(
        user["id"]
    )

    with SessionLocal() as db:
        rows = (
            db.query(
                Business
            )
            .join(
                SavedBusiness,
                SavedBusiness.business_id ==
                Business.id
            )
            .filter(
                SavedBusiness.telegram_user_id ==
                uid
            )
            .filter(
                Business.subscription_active ==
                True
            )
            .order_by(
                SavedBusiness.created_at.desc()
            )
            .all()
        )

        return rows


@app.post("/my/saved-businesses/{business_id}")
def save_business(
    business_id: int,
    x_telegram_init_data: str = Header(
        default=""
    )
):
    user = telegram_user(
        x_telegram_init_data
    )

    uid = int(
        user["id"]
    )

    with SessionLocal() as db:
        business = db.get(
            Business,
            business_id
        )

        if not business:
            raise HTTPException(
                404,
                "Business not found"
            )

        if not business.subscription_active:
            raise HTTPException(
                403,
                "Business is inactive"
            )

        existing = (
            db.query(
                SavedBusiness
            )
            .filter(
                SavedBusiness.telegram_user_id ==
                uid
            )
            .filter(
                SavedBusiness.business_id ==
                business_id
            )
            .first()
        )

        if existing:
            return {
                "ok": True,
                "saved": True
            }

        saved = SavedBusiness(
            telegram_user_id=uid,
            business_id=business_id
        )

        db.add(saved)
        db.commit()

        return {
            "ok": True,
            "saved": True
        }


@app.delete("/my/saved-businesses/{business_id}")
def unsave_business(
    business_id: int,
    x_telegram_init_data: str = Header(
        default=""
    )
):
    user = telegram_user(
        x_telegram_init_data
    )

    uid = int(
        user["id"]
    )

    with SessionLocal() as db:
        saved = (
            db.query(
                SavedBusiness
            )
            .filter(
                SavedBusiness.telegram_user_id ==
                uid
            )
            .filter(
                SavedBusiness.business_id ==
                business_id
            )
            .first()
        )

        if saved:
            db.delete(saved)
            db.commit()

        return {
            "ok": True,
            "saved": False
        }

@app.get("/my/bookings")
def my_bookings(
    x_telegram_init_data: str = Header(default="")
):
    user = telegram_user(x_telegram_init_data)
    uid = int(user["id"])

    from zoneinfo import ZoneInfo

    with SessionLocal() as db:
        rows = (
            db.query(
                Booking,
                Business.name.label("business_name"),
                Business.timezone.label("business_timezone"),
                Service.name.label("service_name")
            )
            .join(
                Business,
                Business.id == Booking.business_id
            )
            .join(
                Service,
                Service.id == Booking.service_id
            )
            .filter(
                Booking.client_telegram_id == uid,
                Booking.status == "confirmed"
            )
            .order_by(
                Booking.day,
                Booking.start
            )
            .limit(50)
            .all()
        )

        result = []

        for (
            booking,
            business_name,
            business_timezone,
            service_name
        ) in rows:

            timezone_name = (
                business_timezone or
                "Asia/Tashkent"
            )

            now_business = datetime.now(
                ZoneInfo(timezone_name)
            ).replace(
                tzinfo=None
            )

            booking_datetime = datetime.combine(
                booking.day,
                booking.start
            )

            # Не показываем прошедшие записи
            if booking_datetime <= now_business:
                continue

            result.append({
                "id": booking.id,
                "business_id": booking.business_id,
                "service_id": booking.service_id,
                "business_name": business_name,
                "service_name": service_name,
                "client_name": booking.client_name,
                "client_phone": booking.client_phone,
                "day": booking.day.isoformat(),
                "start": booking.start.strftime("%H:%M"),
                "end": booking.end.strftime("%H:%M"),
                "start_at_utc": booking.start_at_utc.isoformat() if booking.start_at_utc else None,
                "end_at_utc": booking.end_at_utc.isoformat() if booking.end_at_utc else None,
                "client_timezone": booking.client_timezone or "UTC",
                "status": booking.status
            })

        return result
@app.post("/my/bookings/{booking_id}/cancel")
def my_cancel_booking(
    booking_id: int,
    x_telegram_init_data: str = Header(default="")
):
    user = telegram_user(x_telegram_init_data)
    uid = int(user["id"])

    with SessionLocal() as db:
        booking = db.get(Booking, booking_id)

        if not booking:
            raise HTTPException(
                404,
                "Booking not found"
            )

        if booking.client_telegram_id != uid:
            raise HTTPException(
                403,
                "Access denied"
            )

        if booking.status == "cancelled":
            return {"ok": True}

        booking.status = "cancelled"
        db.commit()

        business = db.get(
            Business,
            booking.business_id
        )

        if business and business.owner_telegram_id:
            telegram_api(
                "sendMessage",
                {
                    "chat_id": business.owner_telegram_id,
                    "text": (
                        "❌ <b>Клиент отменил запись</b>\n\n"
                        f"👤 {booking.client_name}\n"
                        f"📅 {booking.day.isoformat()}\n"
                        f"🕐 {booking.start.strftime('%H:%M')}–"
                        f"{booking.end.strftime('%H:%M')}"
                    ),
                    "parse_mode": "HTML"
                }
            )

        notify_specialist_booking_cancelled(db, booking)

        return {"ok": True}
# ---------- subscription management ----------

PADDLE_API_KEY = os.getenv(
    "PADDLE_API_KEY",
    ""
)


def _paddle_request(
    method: str,
    path: str,
    payload: Optional[dict] = None
):
    if not PADDLE_API_KEY:
        raise HTTPException(
            500,
            "Paddle API key is not configured"
        )

    body = (
        json.dumps(payload).encode("utf-8")
        if payload is not None
        else None
    )

    req = urllib_request.Request(
        f"{PADDLE_API_BASE}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {PADDLE_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Paddle-Version": "1"
        }
    )

    try:
        with urllib_request.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8")
        except Exception:
            raw = ""
        raise HTTPException(
            502,
            f"Paddle API error {exc.code}: {raw[:3000]}"
        )
    except URLError as exc:
        raise HTTPException(
            502,
            f"Paddle connection error: {exc.reason}"
        )


def _bookly_subscription_items(services_limit: int):
    if services_limit not in {10, 20, 30, 50, 100}:
        raise HTTPException(400, "Недопустимый лимит услуг")

    items = [
        {
            "price_id": PADDLE_BOOKLY_BASE_PRICE_ID,
            "quantity": 1
        }
    ]

    addon_price_id = PADDLE_SERVICE_ADDON_PRICE_IDS.get(
        services_limit
    )

    if addon_price_id:
        items.append(
            {
                "price_id": addon_price_id,
                "quantity": 1
            }
        )

    return items


def _bookly_detect_limit_from_items(items) -> Optional[int]:
    detected = 10

    for item in items or []:
        price_id = str(
            item.get("price_id")
            or (item.get("price") or {}).get("id")
            or ""
        )

        for limit, addon_id in PADDLE_SERVICE_ADDON_PRICE_IDS.items():
            if price_id == addon_id:
                detected = max(detected, limit)

    return detected


def _bookly_subscription_price(services_limit: int) -> float:
    return calculate_subscription_price(services_limit)


def _paddle_update_bookly_subscription(
    subscription_id: str,
    new_limit: int,
    proration_mode: str
):
    if not subscription_id.startswith("sub_"):
        raise HTTPException(
            400,
            "Paddle subscription ID is missing"
        )

    return _paddle_request(
        "PATCH",
        f"/subscriptions/{subscription_id}",
        {
            "items": _bookly_subscription_items(new_limit),
            "proration_billing_mode": proration_mode,
            "on_payment_failure": "prevent_change"
        }
    )


@app.post("/admin/subscription/preview-limit")
def preview_subscription_limit(
    x: SubscriptionLimitChangeIn,
    x_telegram_init_data: str = Header(default=""),
):
    _, _, business_id, subscription_id = _current_subscription(
        x_telegram_init_data
    )

    if x.services_limit not in LIMITS:
        raise HTTPException(
            400,
            "Недопустимый лимит услуг",
        )

    with SessionLocal() as db:
        subscription = owner_subscription(
            db,
            business_id,
        )

        if not subscription or not subscription.active:
            raise HTTPException(
                400,
                "Active subscription required",
            )

        current = (
            subscription.current_services_limit
            or 10
        )

    if x.services_limit == current:
        raise HTTPException(
            400,
            "Этот лимит уже установлен",
        )

    proration_mode = (
        "prorated_immediately"
        if x.services_limit > current
        else "prorated_next_billing_period"
    )

    return _paddle_request(
        "PATCH",
        f"/subscriptions/{subscription_id}/preview",
        {
            "items": _items_for_limit(
                x.services_limit
            ),
            "proration_billing_mode": proration_mode,
            "on_payment_failure": "prevent_change",
        },
    )


@app.post("/admin/subscription/change-limit")
def change_subscription_limit(
    x: SubscriptionLimitChangeIn,
    x_telegram_init_data: str = Header(default="")
):
    user = telegram_user(x_telegram_init_data)
    owner_id = int(user["id"])

    if x.services_limit not in {10, 20, 30, 50, 100}:
        raise HTTPException(400, "Недопустимый лимит услуг")

    with SessionLocal() as db:
        business = owner_business(db, owner_id)
        if not business:
            raise HTTPException(404, "Business not found")

        subscription = owner_subscription(db, business.id)
        if not subscription:
            raise HTTPException(400, "Subscription not found")

        if not subscription.active:
            raise HTTPException(400, "Active subscription required")

        current_limit = subscription.current_services_limit or 10
        pending_limit = subscription.pending_services_limit

        if x.services_limit == current_limit:
            if pending_limit == current_limit:
                subscription.pending_services_limit = None
                subscription.pending_price = None
                db.commit()

            return {
                "ok": True,
                "current_services_limit": current_limit,
                "current_price": float(subscription.current_price or 7.99),
                "pending_services_limit": subscription.pending_services_limit,
                "pending_price": subscription.pending_price
            }

        new_price = _bookly_subscription_price(x.services_limit)

        # Upgrade: change immediately and bill prorated amount now.
        if x.services_limit > current_limit:
            _paddle_update_bookly_subscription(
                subscription.external_subscription_id,
                x.services_limit,
                "prorated_immediately"
            )

            subscription.current_services_limit = x.services_limit
            subscription.current_price = new_price
            subscription.pending_services_limit = None
            subscription.pending_price = None
            db.commit()

            return {
                "ok": True,
                "current_services_limit": x.services_limit,
                "current_price": float(new_price),
                "pending_services_limit": None,
                "pending_price": None
            }

                # Downgrade / addon cancellation:
        # текущий пакет остаётся активным до конца периода,
        # а более низкий лимит становится действующим
        # только со следующего продления.

        # Если это изменение уже было запланировано,
        # второй раз в Paddle его не отправляем.
        if subscription.pending_services_limit == x.services_limit:
            return {
                "ok": True,
                "current_services_limit": current_limit,
                "current_price": float(
                    subscription.current_price or 7.99
                ),
                "pending_services_limit": (
                    subscription.pending_services_limit
                ),
                "pending_price": (
                    float(subscription.pending_price)
                    if subscription.pending_price is not None
                    else None
                )
            }

        # Если вся основная подписка уже отменена
        # на конец оплаченного периода, в Paddle ничего
        # дополнительно менять не нужно.
        if subscription.status in {
            "cancelled",
            "canceled"
        }:
            subscription.pending_services_limit = (
                x.services_limit
            )
            subscription.pending_price = new_price

            db.commit()

            return {
                "ok": True,
                "current_services_limit": current_limit,
                "current_price": float(
                    subscription.current_price or 7.99
                ),
                "pending_services_limit": (
                    x.services_limit
                ),
                "pending_price": float(
                    new_price
                )
            }

        # Обычная отмена пакета:
        # пакет остаётся активным сейчас,
        # изменение биллинга переносится на следующий период.
        _paddle_update_bookly_subscription(
            subscription.external_subscription_id,
            x.services_limit,
            "prorated_next_billing_period"
        )

        subscription.pending_services_limit = (
            x.services_limit
        )
        subscription.pending_price = new_price

        db.commit()

        return {
            "ok": True,
            "current_services_limit": current_limit,
            "current_price": float(
                subscription.current_price or 7.99
            ),
            "pending_services_limit": (
                x.services_limit
            ),
            "pending_price": float(
                new_price
            )
        }


@app.post("/admin/subscription/resume-package")
def resume_subscription_package(
    x_telegram_init_data: str = Header(default="")
):
    user = telegram_user(x_telegram_init_data)
    owner_id = int(user["id"])

    with SessionLocal() as db:
        business = owner_business(db, owner_id)
        if not business:
            raise HTTPException(404, "Business not found")

        subscription = owner_subscription(db, business.id)
        if not subscription:
            raise HTTPException(400, "Subscription not found")

        current_limit = subscription.current_services_limit or 10
        if current_limit <= 10 or subscription.pending_services_limit is None:
            return {
                "ok": True,
                "current_services_limit": current_limit,
                "pending_services_limit": None,
                "pending_price": None
            }

        if not subscription.external_subscription_id:
            raise HTTPException(
                400,
                "Paddle subscription ID is missing"
            )

        # Restore the currently active item set and cancel the
        # scheduled downgrade without creating a charge.
        _paddle_update_bookly_subscription(
            subscription.external_subscription_id,
            current_limit,
            "do_not_bill"
        )

        subscription.pending_services_limit = None
        subscription.pending_price = None
        db.commit()

        return {
            "ok": True,
            "current_services_limit": current_limit,
            "current_price": float(subscription.current_price or 7.99),
            "pending_services_limit": None,
            "pending_price": None
        }


@app.post("/admin/subscription/cancel")
def cancel_subscription(
    x_telegram_init_data: str = Header(default="")
):
    user = telegram_user(x_telegram_init_data)
    owner_id = int(user["id"])

    with SessionLocal() as db:
        business = owner_business(db, owner_id)
        if not business:
            raise HTTPException(404, "Business not found")

        subscription = owner_subscription(db, business.id)
        if not subscription:
            raise HTTPException(400, "Subscription not found")

        subscription_id = (
            subscription.external_subscription_id or ""
        ).strip()
        if not subscription_id.startswith("sub_"):
            raise HTTPException(400, "Invalid Paddle subscription ID")

        # Если ранее была запланирована отмена пакета,
        # сначала убираем scheduled change Paddle,
        # чтобы затем можно было запланировать отмену
        # всей подписки.
        if subscription.pending_services_limit is not None:

            _paddle_request(
                "PATCH",
                f"/subscriptions/{subscription_id}",
                {
                    "scheduled_change": None
                }
            )
        
        data = _paddle_request(
            "POST",
            f"/subscriptions/{subscription_id}/cancel",
            {"effective_from": "next_billing_period"}
        )

        paddle_data = data.get("data", {}) or {}
        scheduled_change = paddle_data.get("scheduled_change") or {}
        effective_at = scheduled_change.get("effective_at")

        subscription.status = "cancelled"
        subscription.active = True

        business.subscription_status = "cancelled"
        business.subscription_active = True

        if effective_at:
            try:
                expires_at = datetime.fromisoformat(
                    effective_at.replace("Z", "+00:00")
                ).replace(tzinfo=None)

                subscription.expires_at = expires_at
                business.subscription_expires_at = expires_at

            except ValueError:
                pass

        db.commit()

        return {
            "ok": True,
            "cancelled": True,
            "access_until": (
                subscription.expires_at.isoformat()
                if subscription.expires_at else None
            )
        }


@app.post("/admin/subscription/resume")
def resume_subscription(
    x_telegram_init_data: str = Header(default="")
):
    user = telegram_user(x_telegram_init_data)
    owner_id = int(user["id"])

    with SessionLocal() as db:
        business = owner_business(db, owner_id)
        if not business:
            raise HTTPException(404, "Business not found")

        subscription = owner_subscription(db, business.id)
        if not subscription:
            raise HTTPException(400, "Subscription not found")

        subscription_id = (
            subscription.external_subscription_id or ""
        ).strip()
        if not subscription_id.startswith("sub_"):
            raise HTTPException(400, "Invalid Paddle subscription ID")

        data = _paddle_request(
            "PATCH",
            f"/subscriptions/{subscription_id}",
            {"scheduled_change": None}
        )

        paddle_data = data.get("data", {}) or {}
        subscription.status = "active"
        subscription.active = True

        business.subscription_status = "active"
        business.subscription_active = True

        next_billed_at = paddle_data.get("next_billed_at")
        if next_billed_at:
            try:
                subscription.expires_at = datetime.fromisoformat(
                    next_billed_at.replace("Z", "+00:00")
                ).replace(tzinfo=None)
            except ValueError:
                pass

        db.commit()
        return {"ok": True, "resumed": True}


@app.post("/payments/checkout/{provider}")
def create_checkout(provider: str, x_telegram_init_data: str = Header(default="")):
    if provider not in {"uzum", "lemonsqueezy"}:
        raise HTTPException(400, "Unsupported provider")
    user = telegram_user(x_telegram_init_data)
    owner_id = int(user["id"])
    with SessionLocal() as db:
        b = owner_business(db, owner_id)
        if not b:
            raise HTTPException(400, "Create business first")
        if provider == "lemonsqueezy":
            url = lemonsqueezy_checkout(owner_id)
            if not url:
                return {"provider": provider, "amount": 7.99, "currency": "USD", "status": "not_configured"}
            b.payment_provider = "lemonsqueezy"
            db.commit()
            return {"provider": provider, "amount": 7.99, "currency": "USD", "status": "ready", "url": url}
        return {
            "provider": "uzum",
            "amount": 7.99,
            "currency": "USD",
            "status": "not_configured",
            "message": "Uzum merchant credentials are not configured yet."
        }


@app.post("/payments/webhook/paddle")
async def paddle_webhook(request: Request):
    raw = await request.body()
    signature_header = request.headers.get("Paddle-Signature", "")

    if not PADDLE_WEBHOOK_SECRET:
        raise HTTPException(500, "PADDLE_WEBHOOK_SECRET is not configured")

    parts = dict(
        p.split("=", 1)
        for p in signature_header.split(";")
        if "=" in p
    )
    ts = parts.get("ts", "")
    h1 = parts.get("h1", "")

    if not ts or not h1:
        raise HTTPException(401, "Invalid Paddle signature header")

    try:
        if abs(int(datetime.utcnow().timestamp()) - int(ts)) > 5:
            raise HTTPException(401, "Expired Paddle webhook")
    except ValueError:
        raise HTTPException(401, "Invalid Paddle timestamp")

    signed_payload = f"{ts}:{raw.decode()}".encode()
    expected_signature = hmac.new(
        PADDLE_WEBHOOK_SECRET.encode(),
        signed_payload,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, h1):
        raise HTTPException(401, "Invalid webhook signature")

    payload = json.loads(raw.decode() or "{}")
    event_type = payload.get("event_type", "")
    data = payload.get("data", {}) or {}
    custom = data.get("custom_data", {}) or {}

    owner_id = custom.get("telegram_user_id")
    business_id = custom.get("business_id")
    status = data.get("status", "")

    if event_type in {
        "subscription.created",
        "subscription.updated",
        "subscription.resumed",
        "subscription.paused",
        "subscription.canceled"
    }:
        subscription_id = str(data.get("id", "") or "")
    elif event_type.startswith("transaction."):
        subscription_id = str(data.get("subscription_id", "") or "")
    else:
        subscription_id = ""

    billing_period = data.get("current_billing_period", {}) or {}
    next_billed_at = (
        data.get("next_billed_at")
        or billing_period.get("ends_at")
    )

    print(
        "SKEDWOO PADDLE WEBHOOK DEBUG:",
        event_type,
        "business_id=",
        business_id,
        "owner_id=",
        owner_id,
        "subscription_id=",
        subscription_id,
        "status=",
        status,
    )
    with SessionLocal() as db:
        business = None

        if business_id:
            try:
                candidate = db.get(Business, int(business_id))
                if candidate and owner_id and candidate.owner_telegram_id == int(owner_id):
                    business = candidate
            except (TypeError, ValueError):
                business = None

        if not business and owner_id:
            business = owner_business(db, int(owner_id))

        if not business:
            return {"received": True}

        subscription = (
            db.query(Subscription)
            .filter(Subscription.business_id == business.id)
            .first()
        )

        if not subscription:
            subscription = Subscription(
                business_id=business.id,
                owner_telegram_id=business.owner_telegram_id,
                plan="pro",
                active=False,
                status="inactive",
                current_services_limit=10,
                current_price=7.99
            )
            db.add(subscription)
            db.flush()

        if subscription_id.startswith("sub_"):
            subscription.external_subscription_id = subscription_id

        subscription.payment_provider = "paddle"

        scheduled_change = data.get("scheduled_change") or {}
        scheduled_action = scheduled_change.get("action")
        scheduled_effective_at = scheduled_change.get("effective_at")

        # Scheduled cancellation of the whole subscription.
        if scheduled_action == "cancel":
            subscription.status = "cancelled"
            subscription.active = True
            if scheduled_effective_at:
                try:
                    subscription.expires_at = datetime.fromisoformat(
                        scheduled_effective_at.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                except ValueError:
                    pass

        elif event_type == "transaction.completed":
            if status:
                subscription.status = status

            subscription.active = status not in {"canceled", "cancelled", "paused"}

            if next_billed_at:
                try:
                    subscription.expires_at = datetime.fromisoformat(
                        next_billed_at.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                except ValueError:
                    pass

            # A completed recurring transaction is the point at which
            # a pending downgrade becomes the current entitlement.
            detected_limit = _bookly_detect_limit_from_items(
                data.get("items") or data.get("line_items")
            )

            if subscription.pending_services_limit is not None:
                detected_limit = subscription.pending_services_limit

            subscription.current_services_limit = detected_limit
            subscription.current_price = _bookly_subscription_price(detected_limit)
            subscription.pending_services_limit = None
            subscription.pending_price = None

        elif event_type == "subscription.created":
            if status:
                subscription.status = status
            subscription.active = status not in {"canceled", "cancelled", "paused"}

            detected_limit = _bookly_detect_limit_from_items(data.get("items"))
            subscription.current_services_limit = detected_limit
            subscription.current_price = _bookly_subscription_price(detected_limit)

            if next_billed_at:
                try:
                    subscription.expires_at = datetime.fromisoformat(
                        next_billed_at.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                except ValueError:
                    pass

        elif event_type == "subscription.resumed":
            subscription.status = "active"
            subscription.active = True
            if next_billed_at:
                try:
                    subscription.expires_at = datetime.fromisoformat(
                        next_billed_at.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                except ValueError:
                    pass

        elif event_type == "subscription.canceled":
            if (
                subscription.expires_at
                and subscription.expires_at > datetime.utcnow()
            ):
                subscription.active = True
                subscription.status = "cancelled"
            else:
                subscription.active = False
                subscription.status = "cancelled"

        elif event_type == "subscription.paused":
            subscription.active = False
            subscription.status = "paused"

        elif event_type == "transaction.payment_failed":
            if (
                subscription.expires_at
                and subscription.expires_at > datetime.utcnow()
            ):
                subscription.active = True
            else:
                subscription.active = False

        business.subscription_active = bool(subscription.active)
        business.subscription_expires_at = subscription.expires_at
        business.subscription_status = (
            "active"
            if subscription.active
            else (subscription.status or "inactive")
        )
        business.payment_provider = subscription.payment_provider or "paddle"
        business.external_subscription_id = subscription.external_subscription_id

        db.commit()

    return {"received": True}

# ---------------------------------------------------------
# Неуспешный платёж
# ---------------------------------------------------------

@app.post("/payments/webhook/{provider}")
def payment_webhook(
    provider: str,
    payload: dict
):
    if provider not in {
        "uzum"
    }:
        raise HTTPException(
            400,
            "Use the provider-specific webhook"
        )

    return {
        "received": True,
        "provider": provider,
        "status":
            "awaiting merchant callback mapping"
    }
@app.post("/payments/webhook/{provider}")
def payment_webhook(provider:str,payload:dict):
    if provider not in {"uzum"}:raise HTTPException(400,"Use the provider-specific webhook")
    return {"received":True,"provider":provider,"status":"awaiting merchant callback mapping"}
