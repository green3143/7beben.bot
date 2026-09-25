
import asyncio
import random
import re
import sqlite3
from aiogram import Bot, Dispatcher, F, html
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

TOKEN = "8848424471:AAGx7ouTZZPGrC_18q1WTxJ9ipbf1Uubqxo"  # Токен
ADMIN_ID = 6446656281  # адйдишник
REKVIZITY = (
    "СБП / ЮMoney: +79991234567"  #это для оплаты розыгрыша
)

bot = Bot(token=TOKEN)
dp = Dispatcher()

BREAD_MODE = False

START_SWEAR_WORDS = [
    "хуй",
    "пизда",
    "ебать",
    "хуета",
    "блять",
    "сука",
    "пидорас",
    "заебал",
    "охуеть",
    "похуй",
]

#бд
conn = sqlite3.connect("brain.db")
cursor = conn.cursor()
cursor.execute(
    """CREATE TABLE IF NOT EXISTS Markov 
                  (word1 TEXT, word2 TEXT, next_word TEXT)"""
)

cursor.execute(
    """CREATE TABLE IF NOT EXISTS Participants 
                  (user_id INTEGER, username TEXT, status TEXT)"""
)
conn.commit()


# Первичная заправка базы матом, если она пустая
def seed_database():
    cursor.execute("SELECT COUNT(*) FROM Markov")
    if cursor.fetchone()[0] == 0:
        for _ in range(50):
            w1 = random.choice(START_SWEAR_WORDS)
            w2 = random.choice(START_SWEAR_WORDS)
            w3 = random.choice(START_SWEAR_WORDS)
            cursor.execute("INSERT INTO Markov VALUES (?, ?, ?)", (w1, w2, w3))
        conn.commit()


seed_database()


class GiveawayStates(StatesGroup):
    waiting_for_prize = State()
    waiting_for_conditions = State()
    waiting_for_type = State()



def learn_text(text):
    words = re.findall(r"\b\w+\b", text.lower())
    if len(words) < 3:
        return
    for i in range(len(words) - 2):
        cursor.execute(
            "INSERT INTO Markov VALUES (?, ?, ?)",
            (words[i], words[i + 1], words[i + 2]),
        )
    conn.commit()


def generate_reply(text):
    words = re.findall(r"\b\w+\b", text.lower())
    seed_word = random.choice(words) if words else None

    if seed_word:
        cursor.execute(
            "SELECT word1, word2 FROM Markov WHERE word1=? OR word2=? ORDER BY RANDOM() LIMIT 1",
            (seed_word, seed_word),
        )
        res = cursor.fetchone()
    else:
        res = None

    if not res:
        cursor.execute(
            "SELECT word1, word2 FROM Markov ORDER BY RANDOM() LIMIT 1"
        )
        res = cursor.fetchone()

    if not res:
        return "Хули молчите, научите сначала говорить пидораса!"

    w1, w2 = res
    sentence = [w1, w2]

    for _ in range(12):
        cursor.execute(
            "SELECT next_word FROM Markov WHERE word1=? AND word2=? ORDER BY RANDOM() LIMIT 1",
            (w1, w2),
        )
        next_res = cursor.fetchone()
        if not next_res:
            break
        next_word = next_res[0]
        sentence.append(next_word)
        w1, w2 = w2, next_word

    # С шансом 40% добавляем случайный мат в конец или начало для сочности
    if random.random() < 0.4:
        sentence.append(random.choice(START_SWEAR_WORDS))

    return " ".join(sentence).capitalize()


# --- КОМАНДЫ АДМИНА ---


@dp.message(Command("bread"))
async def toggle_bread(message: Message):
    global BREAD_MODE
    if message.from_user.id != ADMIN_ID:
        return
    BREAD_MODE = not BREAD_MODE
    await message.reply(
        f"Режим бреда {'ВКЛЮЧЕН 🤪 Самое время просраться матом.' if BREAD_MODE else 'ВЫКЛЮЧЕН 🤫'}"
    )


# Запуск конструктора розыгрыша
@dp.message(Command("giveaway"))
async def start_giveaway_setup(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await message.reply("🎁 Начинаем настройку розыгрыша. Что разыгрываем?")
    await state.set_state(GiveawayStates.waiting_for_prize)


@dp.message(GiveawayStates.waiting_for_prize)
async def get_prize(message: Message, state: FSMContext):
    await state.update_data(prize=message.text)
    await message.reply("📝 Напишите условия (например: 'Подписка на канал и 100 рублей')")
    await state.set_state(GiveawayStates.waiting_for_conditions)


@dp.message(GiveawayStates.waiting_for_conditions)
async def get_conditions(message: Message, state: FSMContext):
    await state.update_data(conditions=message.text)

    # Выбор типа участия кнопки
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Бесплатное", callback_query_data="type_free"),
                InlineKeyboardButton(text="Платное 💰", callback_query_data="type_paid"),
            ]
        ]
    )
    await message.reply("💰 Какое будет участие?", reply_markup=kb)
    await state.set_state(GiveawayStates.waiting_for_type)


# --- ОБРАБОТКА ВЫБОРА ТИПА И ПУБЛИКАЦИЯ ---


@dp.callback_query(F.data.startswith("type_"), GiveawayStates.waiting_for_type)
async def publish_giveaway(callback: CallbackQuery, state: FSMContext):
    g_type = "paid" if callback.data == "type_paid" else "free"
    data = await state.get_data()
    await state.clear()

    # Сброс старых участников
    cursor.execute("DELETE FROM Participants")
    conn.commit()

    text = (
        f"🎉 **НОВЫЙ РОЗЫГРЫШ!** 🎉\n\n"
        f"🏆 **Приз:** {data['prize']}\n"
        f"📋 **Условия:** {data['conditions']}\n"
        f"💵 **Тип:** {'Платное участие' if g_type == 'paid' else 'Бесплатно для всех'}\n\n"
        f"Нажимайте кнопку ниже, чтобы ворваться!"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Участвовать! 🚀", callback_query_data=f"join_{g_type}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚡ Итоги (Только Админ)", callback_query_data="finish_giveaway"
                )
            ],
        ]
    )

    await callback.message.delete()
    await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")


# --- ОБРАБОТКА НАЖАТИЯ КНОПОК ПОЛЬЗОВАТЕЛЯМИ ---


@dp.callback_query(F.data.startswith("join_"))
async def join_giveaway(callback: CallbackQuery):
    user_id = callback.from_user.id
    username = (
        f"@{callback.from_user.username}"
        if callback.from_user.username
        else callback.from_user.first_name
    )
    g_type = callback.data.split("_")[1]

    # Проверка, участвует ли уже
    cursor.execute("SELECT status FROM Participants WHERE user_id=?", (user_id,))
    existing = cursor.fetchone()

    if existing:
        if existing[0] == "approved":
            await callback.answer("Ты уже в игре, расслабь булки! ✅", show_alert=True)
        else:
            await callback.answer(
                "Твоя заявка на проверке у админа. Жди ⏳", show_alert=True
            )
        return

    if g_type == "free":
        cursor.execute(
            "INSERT INTO Participants VALUES (?, ?, 'approved')",
            (user_id, username),
        )
        conn.commit()
        await callback.answer("Успешно! Ты зарегистрирован! 🎉", show_alert=True)
    else:
        # Для платного участия отправляем реквизиты в ЛС или алертом
        cursor.execute(
            "INSERT INTO Participants VALUES (?, ?, 'pending')", (user_id, username)
        )
        conn.commit()

        # Кнопка для админа на подтверждение
        admin_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Одобрить", callback_query_data=f"pay_yes_{user_id}"
                    ),
                    InlineKeyboardButton(
                        text="❌ Отклонить", callback_query_data=f"pay_no_{user_id}"
                    ),
                ]
            ]
        )

        # Пишем админу
        await bot.send_message(
            ADMIN_ID,
            f"💰 Юзер {username} хочет зайти в платный конкурс. Проверь оплату!",
            reply_markup=admin_kb,
        )

        await callback.answer(
            f"Инструкция: переведи деньги по реквизитам:\n{REKVIZITY}\n\nПосле этого админ подтвердит твое участие!",
            show_alert=True,
        )



@dp.callback_query(F.data.startswith("pay_"))
async def moderate_payment(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    _, action, user_id = callback.data.split("_")

    if action == "yes":
        cursor.execute(
            "UPDATE Participants SET status='approved' WHERE user_id=?", (user_id,)
        )
        conn.commit()
        await callback.message.edit_text("✅ Участие одобрено!")
        try:
            await bot.send_message(
                int(user_id), "🎉 Админ подтвердил оплату! Ты в деле!"
            )
        except:
            pass
    else:
        cursor.execute("DELETE FROM Participants WHERE user_id=?", (user_id,))
        conn.commit()
        await callback.message.edit_text("❌ Заявка отклонена.")
        try:
            await bot.send_message(
                int(user_id), "❌ Твоя заявка отклонена. Деньги не пришли или мало перевел."
            )
        except:
            pass


# ПОДВЕДЕНИЕ ИТОГОВ
@dp.callback_query(F.data == "finish_giveaway")
async def finish_giveaway(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Куда свои культяпки сунешь? Это только для админа! 😡", show_alert=True)
        return

    cursor.execute("SELECT username FROM Participants WHERE status='approved'")
    lucky_ones = cursor.fetchall()

    if not lucky_ones:
        await callback.answer("Никто не записался, разыгрывать не среди кого! 🤷‍♂️", show_alert=True)
