import argparse
import sqlite3


parser = argparse.ArgumentParser(description="'python main.py --help' for help")

parser.add_argument("-s", '--start', action='store_true', help='Start bot poiling')
parser.add_argument("-a", "--admin", type=int, help='Add new admin to database. Pass admin chat id.')
parser.add_argument("-p", '--pay_token', type=str, help='Add new payload token')
parser.add_argument("-t", "--bot_token", type=str, help='Add new bot token')
parser.add_argument("-d", "--drop_credentials", action='store_true', help='Drop bot token, admin chat id and pay token')

args = parser.parse_args()


admin_chat_id = args.admin
payload_token = args.pay_token
bot_token = args.bot_token
start = args.start
drop = args.drop_credentials
conn = sqlite3.connect("dj_bot.db", check_same_thread=False)
curs = conn.cursor()

if admin_chat_id:
    curs.execute("UPDATE Admin SET Admin_id = ? WHERE TRUE", (admin_chat_id,))
    conn.commit()

if payload_token:
    curs.execute("UPDATE Payments SET Sber_key = ? WHERE TRUE", (payload_token,))
    conn.commit()

if bot_token:
    curs.execute("UPDATE Admin SET bot_key = ? WHERE TRUE", (bot_token,))
    conn.commit()

if drop == 1:
    curs.execute("DELETE FROM Admin")
    curs.execute("DELETE FROM Payments")
    conn.commit()

curs.close()
conn.close()

if start:
    import bot
    bot.start_bot()



