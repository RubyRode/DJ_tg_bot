import logging
from aiogram import Bot, Dispatcher, types, executor
import json
import sqlite3
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.types.message import ContentType

from States import States


menu_commands = ["/start", "/book", "/comment"]
admin_commands = ["/get_queue", "/drop_queue", "/drop_users"]
keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True).add(*menu_commands)

logging.basicConfig(level=logging.DEBUG,
                    format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                    # filename="debug.log",
                    )

with open("config.json", "r", encoding="utf-8") as config:
    data = json.load(config)
    messages = data["MESSAGES"]

conn = sqlite3.connect("dj_bot.db", check_same_thread=False)
curs = conn.cursor()

admin_chat_id = curs.execute("SELECT Admin_id FROM Admin").fetchone()[0]
provider_token = curs.execute("SELECT Sber_key FROM Payments").fetchone()[0]
TOKEN = curs.execute("SELECT bot_key FROM Admin").fetchone()[0]

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


def db_table_val(user_id: int, user_name: str, num_songs: int):
    curs.execute('INSERT INTO Users (User_id, User_name, first_free_three) VALUES (?, ?, ?)',
                 (user_id, user_name, num_songs))
    conn.commit()


@dp.message_handler(state=States.AWAITING, commands=["comment"])
async def comment_to_dj(message: types.Message):
    await bot.send_message(message.chat.id, f"Напиши комментарий")
    await States.COMMENT.set()


@dp.message_handler(state=States.COMMENT)
async def comment_handler(message: types.Message):
    us_id = message.from_user.username
    await bot.send_message(admin_chat_id, f"Комментарий от {us_id}: {message.text}")
    curs.execute("INSERT INTO Comments (User_id, Comment) VALUES (?, ?)", (us_id, message.text,))
    conn.commit()
    await States.AWAITING.set()


@dp.message_handler(state=States.AWAITING, commands=["book"])
async def get_trackname(message: types.Message):
    us_id = message.from_user.username
    left_use = curs.execute("SELECT first_free_three FROM Users WHERE User_id = ?", (us_id,))
    left_use = tuple(left_use.fetchone())
    if left_use[0] != 0:
        await bot.send_message(chat_id=message.chat.id, text=f"У тебя осталось еще {left_use[0]} БЕСПЛАТНЫХ "
                                                             f"заказа! Скорее пиши название песни!.")
    else:
        await bot.send_message(chat_id=message.chat.id, text=messages["track_request"])
    await States.TRACK_CHOSEN.set()


@dp.message_handler(state=States.TRACK_CHOSEN)
async def send_invoice(message: types.Message):
    track_names = message.text.split('\n')
    track_list_size = len(track_names)
    us_id = message.from_user.username
    left_use = curs.execute("SELECT first_free_three FROM Users WHERE User_id = ?", (us_id,)).fetchone()[0]
    to_be_payed = track_list_size - left_use
    if to_be_payed > 0:
        await bot.send_invoice(chat_id=message.chat.id, title=message.text,
                               description="Заказ песни/трека",
                               currency="RUB",
                               prices=[types.LabeledPrice(label="track", amount=5000 * to_be_payed)],
                               provider_token=provider_token,
                               need_name=True,
                               need_phone_number=True,
                               need_email=True,
                               is_flexible=False,
                               payload="to be continued"
                               )
        curs.execute("UPDATE Users SET first_free_three = ? where User_id = ?",
                     (0, us_id))
        curs.execute("INSERT INTO Payment_waiting_list (User_id, Payment_succeeded, Booking_completed, track_list) "
                     "VALUES (?, ?, ?, ?)", (us_id, False, False, message.text,))
        conn.commit()
        await States.PURCHASING.set()
    else:
        curs.execute("UPDATE Users SET first_free_three = ? where User_id = ?",
                     (max(0, left_use - track_list_size), us_id))
        curs.execute("INSERT INTO Payment_waiting_list (User_id, Payment_succeeded, Booking_completed, track_list) "
                     "VALUES (?, ?, ?, ?)", (us_id, True, False, message.text,))
        conn.commit()
        await add_to_queue(message)
        await States.AWAITING.set()


@dp.pre_checkout_query_handler(state=States.PURCHASING)
async def pre_checkout_query(precheck_q: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(precheck_q.id, ok=True, error_message=messages['payment_error'])
    await States.CHECKOUT_QUERY.set()


@dp.message_handler(state=States.CHECKOUT_QUERY, content_types=ContentType.SUCCESSFUL_PAYMENT)
async def success_payment(message: types.Message):
    us_id = message.from_user.username
    curs.execute("UPDATE Payment_waiting_list SET Payment_succeeded = ? "
                 "WHERE User_id == ? and Booking_completed == ?", (True, us_id, False,))
    await bot.send_message(message.chat.id, f"Платеж прошел успешно")
    await add_to_queue(message)
    await States.AWAITING.set()


async def add_to_queue(message: types.Message):
    us_id = message.from_user.username
    track_names = curs.execute("SELECT track_list FROM Payment_waiting_list WHERE "
                               "Payment_succeeded == ? and Booking_completed == ?", (True, False,)).fetchone()[0]
    track_names = track_names.split("\n")
    curs.execute("UPDATE Payment_waiting_list SET Booking_completed = ? "
                 "WHERE User_id == ? AND Booking_completed == ?", (True, us_id, False))
    queue_length = curs.execute("SELECT MAX(ord_num) FROM Songs").fetchone()[0]
    queue_length = 1 if queue_length is None else queue_length + 1

    for track_name in track_names:
        curs.execute("INSERT INTO Songs (User_id, song, ord_num) VALUES (?, ?, ?)",
                     (us_id, track_name, queue_length,))
        await bot.send_message(message.chat.id, f"Твоя песня добавлена в очередь ({queue_length})")
        queue_length += 1
    conn.commit()
    await bot.send_message(admin_chat_id, "Заказали новую песню, обнови очередь!")


def in_list_of_tuples(value, destination):
    for tpl in destination:
        if value in tpl:
            return True
    return False


@dp.message_handler(commands=['start'])
async def start_message(message: types.Message):
    names_list = curs.execute("SELECT User_id FROM Users").fetchall()
    if int(message.chat.id) == int(admin_chat_id):
        keyboard.add(*admin_commands)
    if names_list is None:
        db_table_val(message.from_user.username, message.from_user.first_name + " " + message.from_user.last_name, 3)
        await bot.send_message(message.chat.id, messages["first_time"] + "\n", reply_markup=keyboard)
    else:
        if in_list_of_tuples(message.from_user.username, names_list):
            await bot.send_message(message.chat.id, messages["start_message"] + "\n", reply_markup=keyboard)
        else:
            db_table_val(message.from_user.username, message.from_user.first_name + " " + message.from_user.last_name,
                         3)
            await bot.send_message(message.chat.id, messages["first_time"] + "\n", reply_markup=keyboard)

    await States.AWAITING.set()


@dp.message_handler(state=States.AWAITING, commands=["get_queue"])
async def get_queue(message: types.Message):
    if int(message.chat.id) == int(admin_chat_id):
        queue_list = curs.execute("SELECT User_id, song, ord_num FROM Songs ORDER BY ord_num ASC").fetchall()
        output_string = str()
        for id, song, ord in queue_list:
            output_string += f"[{ord}] {id} : {song}\n"
        if output_string:
            await bot.send_message(admin_chat_id, output_string)
        else:
            await bot.send_message(admin_chat_id, "Очередь пуста.")
    else:
        await message.reply("Эта команда доступна только админу")


@dp.message_handler(state=States.AWAITING, commands=["drop_queue"])
async def drop_queue(message: types.Message):
    if int(message.chat.id) == int(admin_chat_id):
        curs.execute("DELETE FROM Songs").fetchall()
        await bot.send_message(admin_chat_id, "Очередь очищена!")
    else:
        await message.reply("Эта команда доступна только админу")


def start_bot():
    try:
        executor.start_polling(dp, skip_updates=True)
    except KeyboardInterrupt:
        bot.close()
        storage.close()
        storage.wait_closed()
