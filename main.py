import logging
from aiogram import Bot, Dispatcher, types, executor
import json
import sqlite3

from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.types.message import ContentType

from States import States

logging.basicConfig(level=logging.DEBUG,
                    format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                    # filename="debug.log",
                    )

with open("config.json", "r", encoding="utf-8") as config:
    data = json.load(config)
    TOKEN = data["BOT_TOKEN"]
    messages = data["MESSAGES"]
    admin_chat_id = data["ADMIN_CHAT_ID"]
    provider_token = data["PAYMENTS"]["SBER"]

bot = Bot(token=TOKEN)

dp = Dispatcher(bot, storage=MemoryStorage())

queue_dict = {}
track_order = 1

conn = sqlite3.connect("dj_bot.db", check_same_thread=False)
curs = conn.cursor()


def db_table_val(user_id: int, user_name: str, num_songs: int):
    curs.execute('INSERT INTO Users (User_id, User_name, first_free_three) VALUES (?, ?, ?)',
                 (user_id, user_name, num_songs))
    conn.commit()


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
    user_track_id = message.from_user.username + "_" + str(message.message_id)
    queue_dict[user_track_id] = {"message_id": message.message_id,
                                 "user": message.from_user.username,
                                 "track": message.text,
                                 "price": 50,
                                 "state": "in_progress",
                                 "order": track_order
                                 }
    payload = json.dumps(queue_dict[user_track_id])

    await bot.send_invoice(chat_id=message.chat.id, title=message.text,
                           description="Заказ песни/трека",
                           currency="RUB",
                           prices=[types.LabeledPrice(label="track", amount=5000)],
                           provider_token=provider_token,
                           need_name=True,
                           need_phone_number=True,
                           need_email=True,
                           is_flexible=False,
                           payload=payload
                           )
    await States.PURCHASING.set()


@dp.pre_checkout_query_handler(state=States.PURCHASING)
async def pre_checkout_query(precheck_q: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(precheck_q.id, ok=True, error_message=messages['payment_error'])
    await States.CHECKOUT_QUERY.set()


@dp.message_handler(state=States.CHECKOUT_QUERY, content_types=ContentType.SUCCESSFUL_PAYMENT)
async def success_payment(message: types.Message):
    payment_info = message.successful_payment.to_python()

    payload = json.loads(payment_info["invoice_payload"])
    queue_dict[payload["user"] + "_" + str(payload["message_id"])]["state"] = "purchased"

    await bot.send_message(message.chat.id, f"Платеж прошел успешно")
    await bot.send_message(admin_chat_id, "Заказали новую песню, обнови очередь!")
    await States.AWAITING.set()


@dp.message_handler(commands=['start'])
async def start_message(message: types.Message):
    names = curs.execute("SELECT User_name FROM Users")
    if message.from_user.username in names.fetchone():
        db_table_val(message.from_user.username, message.from_user.first_name + " " + message.from_user.last_name, 3)
        await bot.send_message(message.chat.id, messages["first_time"] + "\n")
    else:
        await bot.send_message(message.chat.id, messages["start_message"] + "\n")

    await States.AWAITING.set()


@dp.message_handler(state=States.AWAITING, commands=["get_queue"])
async def send_admin_queue(message: types.Message):
    if int(message.chat.id) == int(admin_chat_id):
        queue_list = ""
        cnt = 1
        for user in queue_dict:
            queue_list += str(cnt) + ": " + queue_dict[user]['user'] + " - " + queue_dict[user]["track"] + "\n"
            cnt += 1

        await bot.send_message(chat_id=admin_chat_id, text=queue_list)
    else:
        await message.reply("Эта команда доступна только админу")


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
