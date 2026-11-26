import os
import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ================== НАСТРОЙКИ ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_NAME = "skill_exchange.db"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ================== СОСТОЯНИЯ ==================
class Registration(StatesGroup):
    name = State()
    age = State()
    can_do = State()
    looking_for = State()
    about = State()
    contact = State()
    photo = State()

class Search(StatesGroup):
    waiting_query = State()
    browsing = State()

# ================== БАЗА ДАННЫХ ==================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                age INTEGER,
                can_do TEXT,
                looking_for TEXT,
                about TEXT,
                contact TEXT,
                photo_id TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS likes (
                from_id INTEGER,
                to_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (from_id, to_id)
            )
        """)
        await db.commit()

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "user_id": row[0], "name": row[1], "age": row[2],
                    "can_do": row[3], "looking_for": row[4], "about": row[5],
                    "contact": row[6], "photo_id": row[7], "is_active": row[8]
                }
            return None

async def save_user(data: dict):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT OR REPLACE INTO users 
            (user_id, name, age, can_do, looking_for, about, contact, photo_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["user_id"], data["name"], data["age"],
            data["can_do"], data["looking_for"], data["about"],
            data["contact"], data.get("photo_id")
        ))
        await db.commit()

async def add_like(from_id: int, to_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO likes (from_id, to_id) VALUES (?, ?)",
            (from_id, to_id)
        )
        await db.commit()

async def check_mutual_like(user1: int, user2: int) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT 1 FROM likes WHERE from_id = ? AND to_id = ?",
            (user2, user1)
        ) as cursor:
            return await cursor.fetchone() is not None

async def search_users(query: str, exclude_id: int, limit: int = 20):
    async with aiosqlite.connect(DB_NAME) as db:
        query = f"%{query.lower()}%"
        async with db.execute("""
            SELECT * FROM users 
            WHERE is_active = 1 
              AND user_id != ?
              AND (
                  lower(can_do) LIKE ? 
                  OR lower(looking_for) LIKE ?
                  OR lower(about) LIKE ?
                  OR lower(name) LIKE ?
              )
            ORDER BY created_at DESC
            LIMIT ?
        """, (exclude_id, query, query, query, query, limit)) as cursor:
            rows = await cursor.fetchall()
            return [{
                "user_id": r[0], "name": r[1], "age": r[2],
                "can_do": r[3], "looking_for": r[4], "about": r[5],
                "contact": r[6], "photo_id": r[7]
            } for r in rows]

async def get_random_users(exclude_id: int, limit: int = 15):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("""
            SELECT * FROM users 
            WHERE is_active = 1 AND user_id != ?
            ORDER BY RANDOM()
            LIMIT ?
        """, (exclude_id, limit)) as cursor:
            rows = await cursor.fetchall()
            return [{
                "user_id": r[0], "name": r[1], "age": r[2],
                "can_do": r[3], "looking_for": r[4], "about": r[5],
                "contact": r[6], "photo_id": r[7]
            } for r in rows]

# ================== КЛАВИАТУРЫ ==================
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Искать людей"), KeyboardButton(text="👤 Моя анкета")],
            [KeyboardButton(text="❤️ Кого я лайкнул"), KeyboardButton(text="✏️ Редактировать анкету")]
        ],
        resize_keyboard=True
    )

def skip_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пропустить ➡️")]],
        resize_keyboard=True
    )

def like_keyboard(target_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="❤️ Лайк", callback_data=f"like:{target_id}")
    builder.button(text="➡️ Дальше", callback_data="next")
    builder.button(text="🔍 Новый поиск", callback_data="new_search")
    builder.adjust(2)
    return builder.as_markup()

# ================== ХЭЛПЕРЫ ==================
def format_profile(user: dict, show_contact: bool = False) -> str:
    text = (
        f"👤 <b>{user['name']}</b>, {user['age']}\n\n"
        f"✨ <b>Умею:</b>\n{user['can_do']}\n\n"
        f"🔍 <b>Ищу:</b>\n{user['looking_for']}\n\n"
        f"📝 <b>О себе:</b>\n{user['about']}"
    )
    if show_contact:
        text += f"\n\n📞 <b>Контакт:</b> {user['contact']}"
    return text

# ================== СТАРТ ==================
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user = await get_user(message.from_user.id)

    if user:
        await message.answer(
            f"С возвращением, {user['name']}! 👋\n\n"
            "Что хочешь сделать?",
            reply_markup=main_menu()
        )
    else:
        await message.answer(
            "Привет! 👋\n\n"
            "Это закрытый клуб обмена навыками.\n"
            "Здесь люди помогают друг другу без денег:\n"
            "«Я тебе — математику, ты мне — монтаж видео».\n\n"
            "Чтобы начать, нужно создать анкету.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="📝 Создать анкету")]],
                resize_keyboard=True
            )
        )

# ================== РЕГИСТРАЦИЯ ==================
@dp.message(F.text == "📝 Создать анкету")
@dp.message(F.text == "✏️ Редактировать анкету")
async def start_registration(message: types.Message, state: FSMContext):
    await state.set_state(Registration.name)
    await message.answer(
        "Отлично! Давай создадим твою анкету ✨\n\n"
        "Как тебя зовут? (имя или ник)",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(Registration.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(Registration.age)
    await message.answer("Сколько тебе лет?")

@dp.message(Registration.age)
async def process_age(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or not (10 <= int(message.text) <= 100):
        await message.answer("Пожалуйста, введи возраст цифрами (от 10 до 100)")
        return
    await state.update_data(age=int(message.text))
    await state.set_state(Registration.can_do)
    await message.answer(
        "Что ты умеешь и чем можешь помочь другим?\n"
        "(Можно писать свободно, например: «Математика 10-11 класс, Python, монтаж в Premiere»)"
    )

@dp.message(Registration.can_do)
async def process_can_do(message: types.Message, state: FSMContext):
    await state.update_data(can_do=message.text.strip())
    await state.set_state(Registration.looking_for)
    await message.answer(
        "Что ты сам ищешь? Какие навыки хочешь получить?\n"
        "(Например: «Нужен монтаж видео, помощь с английским, научиться рисовать»)"
    )

@dp.message(Registration.looking_for)
async def process_looking_for(message: types.Message, state: FSMContext):
    await state.update_data(looking_for=message.text.strip())
    await state.set_state(Registration.about)
    await message.answer(
        "Расскажи немного о себе (по желанию):\n"
        "Чем занимаешься, какие интересы, почему хочешь обмениваться навыками."
    )

@dp.message(Registration.about)
async def process_about(message: types.Message, state: FSMContext):
    await state.update_data(about=message.text.strip())
    await state.set_state(Registration.contact)
    await message.answer(
        "Укажи свой контакт (Telegram-username или телефон).\n"
        "Он будет виден только при взаимном лайке ❤️"
    )

@dp.message(Registration.contact)
async def process_contact(message: types.Message, state: FSMContext):
    await state.update_data(contact=message.text.strip())
    await state.set_state(Registration.photo)
    await message.answer(
        "Хочешь добавить фото к анкете?\n"
        "Отправь фото или нажми «Пропустить»",
        reply_markup=skip_keyboard()
    )

@dp.message(Registration.photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    data = await state.get_data()
    data["user_id"] = message.from_user.id
    data["photo_id"] = photo_id
    await save_user(data)
    await state.clear()

    await message.answer(
        "✅ Анкета успешно создана!\n\n"
        "Теперь ты можешь искать людей и ставить лайки.",
        reply_markup=main_menu()
    )
    user = await get_user(message.from_user.id)
    await show_own_profile(message, user)

@dp.message(Registration.photo, F.text == "Пропустить ➡️")
async def skip_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    data["user_id"] = message.from_user.id
    data["photo_id"] = None
    await save_user(data)
    await state.clear()

    await message.answer(
        "✅ Анкета успешно создана!\n\n"
        "Теперь ты можешь искать людей и ставить лайки.",
        reply_markup=main_menu()
    )
    user = await get_user(message.from_user.id)
    await show_own_profile(message, user)

async def show_own_profile(message: types.Message, user: dict):
    text = "📄 <b>Твоя анкета:</b>\n\n" + format_profile(user, show_contact=True)
    if user.get("photo_id"):
        await message.answer_photo(user["photo_id"], caption=text, parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")

# ================== МОЯ АНКЕТА ==================
@dp.message(F.text == "👤 Моя анкета")
async def my_profile(message: types.Message):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("У тебя ещё нет анкеты. Создай её!", reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📝 Создать анкету")]], resize_keyboard=True
        ))
        return
    await show_own_profile(message, user)

# ================== ПОИСК ==================
@dp.message(F.text == "🔍 Искать людей")
async def start_search(message: types.Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала создай анкету!")
        return

    await state.set_state(Search.waiting_query)
    await message.answer(
        "Введи ключевые слова для поиска\n"
        "(например: «математика», «монтаж», «английский», «python»)\n\n"
        "Или напиши «все», чтобы просто смотреть анкеты.",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(Search.waiting_query)
async def process_search_query(message: types.Message, state: FSMContext):
    query = message.text.strip().lower()

    if query in ["все", "всё", "all"]:
        users = await get_random_users(message.from_user.id)
    else:
        users = await search_users(query, message.from_user.id)

    if not users:
        await message.answer(
            "Никого не нашлось 😔\nПопробуй другие слова или напиши «все».",
            reply_markup=main_menu()
        )
        await state.clear()
        return

    await state.update_data(search_results=users, current_index=0)
    await state.set_state(Search.browsing)
    await show_next_profile(message, state)

async def show_next_profile(message: types.Message, state: FSMContext):
    data = await state.get_data()
    users = data.get("search_results", [])
    index = data.get("current_index", 0)

    if index >= len(users):
        await message.answer(
            "Анкеты закончились 📭\nМожешь начать новый поиск.",
            reply_markup=main_menu()
        )
        await state.clear()
        return

    user = users[index]
    text = format_profile(user)

    if user.get("photo_id"):
        await message.answer_photo(
            user["photo_id"],
            caption=text,
            parse_mode="HTML",
            reply_markup=like_keyboard(user["user_id"])
        )
    else:
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=like_keyboard(user["user_id"])
        )

@dp.callback_query(F.data == "next")
async def next_profile(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    index = data.get("current_index", 0) + 1
    await state.update_data(current_index=index)
    await callback.message.delete()
    await show_next_profile(callback.message, state)
    await callback.answer()

@dp.callback_query(F.data == "new_search")
async def new_search(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await start_search(callback.message, state)
    await callback.answer()

# ================== ЛАЙКИ ==================
@dp.callback_query(F.data.startswith("like:"))
async def process_like(callback: types.CallbackQuery, state: FSMContext):
    from_id = callback.from_user.id
    to_id = int(callback.data.split(":")[1])

    if from_id == to_id:
        await callback.answer("Нельзя лайкнуть самого себя 😅", show_alert=True)
        return

    await add_like(from_id, to_id)

    is_mutual = await check_mutual_like(from_id, to_id)

    if is_mutual:
        me = await get_user(from_id)
        other = await get_user(to_id)

        await bot.send_message(
            from_id,
            f"🎉 <b>Взаимный лайк!</b>\n\n"
            f"Вы понравились друг другу с <b>{other['name']}</b>!\n\n"
            + format_profile(other, show_contact=True),
            parse_mode="HTML"
        )
        if other.get("photo_id"):
            await bot.send_photo(from_id, other["photo_id"])

        await bot.send_message(
            to_id,
            f"🎉 <b>Взаимный лайк!</b>\n\n"
            f"Вы понравились друг другу с <b>{me['name']}</b>!\n\n"
            + format_profile(me, show_contact=True),
            parse_mode="HTML"
        )
        if me.get("photo_id"):
            await bot.send_photo(to_id, me["photo_id"])

        await callback.answer("🎉 Это взаимный лайк!", show_alert=True)
    else:
        me = await get_user(from_id)
        text = (
            f"❤️ Тебе поставили лайк!\n\n"
            f"Вот анкета человека:\n\n"
            + format_profile(me)
        )
        try:
            if me.get("photo_id"):
                await bot.send_photo(
                    to_id,
                    me["photo_id"],
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❤️ Лайкнуть в ответ", callback_data=f"like:{from_id}")]
                    ])
                )
            else:
                await bot.send_message(
                    to_id,
                    text,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❤️ Лайкнуть в ответ", callback_data=f"like:{from_id}")]
                    ])
                )
        except Exception:
            pass

        await callback.answer("Лайк отправлен! ❤️")

    data = await state.get_data()
    index = data.get("current_index", 0) + 1
    await state.update_data(current_index=index)
    await callback.message.delete()
    await show_next_profile(callback.message, state)

# ================== КОГО Я ЛАЙКНУЛ ==================
@dp.message(F.text == "❤️ Кого я лайкнул")
async def my_likes(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("""
            SELECT u.* FROM likes l
            JOIN users u ON u.user_id = l.to_id
            WHERE l.from_id = ?
            ORDER BY l.created_at DESC
            LIMIT 20
        """, (message.from_user.id,)) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await message.answer("Ты ещё никого не лайкнул 😊")
        return

    await message.answer(f"Ты лайкнул {len(rows)} человек(а):")
    for r in rows:
        user = {
            "user_id": r[0], "name": r[1], "age": r[2],
            "can_do": r[3], "looking_for": r[4], "about": r[5],
            "contact": r[6], "photo_id": r[7]
        }
        text = format_profile(user)
        if user.get("photo_id"):
            await message.answer_photo(user["photo_id"], caption=text, parse_mode="HTML")
        else:
            await message.answer(text, parse_mode="HTML")

# ================== ЗАПУСК ==================
async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
