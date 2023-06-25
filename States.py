
from aiogram.dispatcher.filters.state import State, StatesGroup


class States(StatesGroup):
    PURCHASING = State("Purchasing")
    PURCHASED = State("Purchased")
    AWAITING = State("Awaits_for_messages")
    TRACK_CHOSEN = State("User_sent_trackname")
    CHECKOUT_QUERY = State("Checkout_query_sent")
    COMMENT = State("Comment_to_dj")
    ADDING = State("Adding to queue")