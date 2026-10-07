from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_search_keyboard():
    """Клавиатура запуска inline-поиска для команды /get."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🔍 Начать поиск",
            switch_inline_query_current_chat="get "
        )
    ]])
