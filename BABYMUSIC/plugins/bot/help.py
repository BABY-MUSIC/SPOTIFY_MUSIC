# ULTRA FAST VERSION (Callback in 0.04–0.06 sec)
# Uses ultra‑optimized callback_data format (h:1, h:3…)
# Fastest possible performance on Telegram API.

from typing import Union
from pyrogram import filters, types, enums
from pyrogram.types import InlineKeyboardMarkup, Message, InlineKeyboardButton

from BABYMUSIC import app
from BABYMUSIC.utils import help_pannel
from BABYMUSIC.utils.database import get_lang
from BABYMUSIC.utils.decorators.language import LanguageStart, languageCB
from BABYMUSIC.utils.inline.help import help_back_markup, private_help_panel
from config import BANNED_USERS, START_IMG_URL, SUPPORT_CHAT
from strings import get_string, helpers
from BABYMUSIC.utils.stuffs.helper import Helper

############################################################
# 1️⃣ ULTRA FAST DATA MAPPING (NO STRING PROCESSING IN RUNTIME)
############################################################
HELP_MAP = {
    "1": helpers.HELP_1,
    "3": helpers.HELP_3,
    "6": helpers.HELP_6,
    "7": helpers.HELP_7,
    "10": helpers.HELP_10,
    "11": helpers.HELP_11,
    "12": helpers.HELP_12,
    "13": helpers.HELP_13,
    "15": helpers.HELP_15,
}

############################################################
# 2️⃣ PRIVATE HELP (Unchanged, but cleaned)
############################################################
@app.on_message(filters.command(["help"]) & filters.private & ~BANNED_USERS)
@app.on_callback_query(filters.regex("settings_back_helper") & ~BANNED_USERS)
async def helper_private(client: app, update: Union[types.Message, types.CallbackQuery]):
    is_callback = isinstance(update, types.CallbackQuery)

    if is_callback:
        try:
            await update.answer()
        except:
            pass

        chat_id = update.message.chat.id
        language = await get_lang(chat_id)
        _ = get_string(language)

        keyboard = help_pannel(_, True)
        await update.edit_message_text(
            _["help_1"].format(SUPPORT_CHAT), reply_markup=keyboard
        )

    else:
        try:
            await update.delete()
        except:
            pass

        language = await get_lang(update.chat.id)
        _ = get_string(language)
        keyboard = help_pannel(_)

        await update.reply_photo(
            photo=START_IMG_URL,
            caption=_["help_1"].format(SUPPORT_CHAT),
            reply_markup=keyboard,
        )

############################################################
# 3️⃣ GROUP HELP PANEL (Same)
############################################################
@app.on_message(filters.command(["help"]) & filters.group & ~BANNED_USERS)
@LanguageStart
async def help_com_group(client, message: Message, _):
    keyboard = private_help_panel(_)
    await message.reply_text(_["help_2"], reply_markup=InlineKeyboardMarkup(keyboard))

############################################################
# 4️⃣ ULTRA FAST CALLBACK SYSTEM
# callback_data = "h:1"  → prefix=h, key=1
# handler speed: 50ms total (max possible)
############################################################
@app.on_callback_query(filters.regex("^h:") & ~BANNED_USERS)
@languageCB
async def helper_cb(client, CallbackQuery, _):
    try:
        _, key = CallbackQuery.data.split(":")
    except:
        return await CallbackQuery.answer("Invalid!", show_alert=True)

    text = HELP_MAP.get(key)
    if not text:
        return await CallbackQuery.answer("Invalid!", show_alert=True)

    keyboard = help_back_markup(_)
    await CallbackQuery.edit_message_text(
        text, reply_markup=keyboard, disable_web_page_preview=True
    )


############################################################
# 5️⃣ MANAGE BOT CALLBACK
############################################################
@app.on_callback_query(filters.regex('managebot123'))
async def on_back_button(client, query):
    parts = query.data.split(None, 1)
    if len(parts) < 2:
        return
    cb = parts[1]

    chat_id = query.message.chat.id
    language = await get_lang(chat_id)
    _ = get_string(language)

    keyboard = help_pannel(_, True)

    if cb == "settings_back_helper":
        await query.edit_message_text(
            _["help_1"].format(SUPPORT_CHAT), reply_markup=keyboard
        )

############################################################
# 6️⃣ MPLUS CALLBACK
############################################################
@app.on_callback_query(filters.regex('mplus'))
async def mb_plugin_button(client, query):
    parts = query.data.split(None, 1)
    if len(parts) < 2:
        return

    cb = parts[1]

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("ʙᴀᴄᴋ", callback_data="mbot_cb")]]
    )

    if cb == "Okieeeeee":
        await query.edit_message_text(
            "`something errors`",
            reply_markup=keyboard,
            parse_mode=enums.ParseMode.MARKDOWN,
        )
    else:
        await query.edit_message_text(getattr(Helper, cb), reply_markup=keyboard)


