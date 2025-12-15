import asyncio
import logging
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from os import getenv

from BABYMUSIC import YouTube, app
from BABYMUSIC.core.call import BABY
from BABYMUSIC.misc import SUDOERS, db
from BABYMUSIC.utils.database import (
    get_active_chats,
    get_lang,
    get_upvote_count,
    is_active_chat,
    is_music_playing,
    is_nonadmin_chat,
    music_off,
    music_on,
    set_loop,
)
from BABYMUSIC.utils.decorators.language import languageCB
from BABYMUSIC.utils.formatters import seconds_to_min
from BABYMUSIC.utils.inline import (
    close_markup,
    stream_markup,
    telegram_markup,
    telegram_markup_timer,
)
from BABYMUSIC.utils.stream.autoclear import auto_clean
from BABYMUSIC.utils.thumbnails import get_thumb
from config import (
    BANNED_USERS,
    SOUNCLOUD_IMG_URL,
    STREAM_IMG_URL,
    TELEGRAM_AUDIO_URL,
    TELEGRAM_VIDEO_URL,
    adminlist,
    confirmer,
    votemode # New threshold import
)
from strings import get_string

checker = {}
upvoters = {}

VOTE_THRESHOLD = int(getenv("VOTE_THRESHOLD", 5))  # Default threshold is 5 votes

@app.on_callback_query(filters.regex("ADMIN") & ~BANNED_USERS)
@languageCB
async def del_back_playlist(client, CallbackQuery, _):
    callback_data = CallbackQuery.data.strip()
    callback_request = callback_data.split(None, 1)[1]
    command, chat = callback_request.split("|")
    if "_" in str(chat):
        bet = chat.split("_")
        chat = bet[0]
        counter = bet[1]
    chat_id = int(chat)
    
    if not await is_active_chat(chat_id):
        return await CallbackQuery.answer(_["general_5"], show_alert=True)
    
    mention = CallbackQuery.from_user.mention
    
    if command == "UpVote":
        if chat_id not in votemode:
            votemode[chat_id] = {}
        if chat_id not in upvoters:
            upvoters[chat_id] = {}

        voters = upvoters[chat_id].get(CallbackQuery.message.id)
        if not voters:
            upvoters[chat_id][CallbackQuery.message.id] = []

        vote = votemode[chat_id].get(CallbackQuery.message.id)
        if not vote:
            votemode[chat_id][CallbackQuery.message.id] = 0

        if CallbackQuery.from_user.id in upvoters[chat_id][CallbackQuery.message.id]:
            upvoters[chat_id][CallbackQuery.message.id].remove(
                CallbackQuery.from_user.id
            )
            votemode[chat_id][CallbackQuery.message.id] -= 1
        else:
            upvoters[chat_id][CallbackQuery.message.id].append(
                CallbackQuery.from_user.id
            )
            votemode[chat_id][CallbackQuery.message.id] += 1
        
        upvote = await get_upvote_count(chat_id)
        get_upvotes = votemode[chat_id][CallbackQuery.message.id]

        if get_upvotes >= VOTE_THRESHOLD:  # Upvote threshold check
            votemode[chat_id][CallbackQuery.message.id] = VOTE_THRESHOLD
            try:
                exists = confirmer[chat_id][CallbackQuery.message.id]
                current = db[chat_id][0]
            except:
                return await CallbackQuery.edit_message_text("Failed to confirm.")
            
            try:
                if current["vidid"] != exists["vidid"]:
                    return await CallbackQuery.edit_message.text(_["admin_35"])
                if current["file"] != exists["file"]:
                    return await CallbackQuery.edit_message.text(_["admin_35"])
            except:
                return await CallbackQuery.edit_message_text(_["admin_36"])

            try:
                await CallbackQuery.edit_message_text(_["admin_37"].format(upvote))
            except:
                pass
            
            command = counter
            mention = "UpVotes"
        
        else:
            if CallbackQuery.from_user.id in upvoters[chat_id][CallbackQuery.message.id]:
                await CallbackQuery.answer(_["admin_38"], show_alert=True)
            else:
                await CallbackQuery.answer(_["admin_39"], show_alert=True)
            
            upl = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text=f"👍 {get_upvotes}",  # Dynamic button text
                            callback_data=f"ADMIN UpVote|{chat_id}_{counter}",
                        )
                    ]
                ]
            )
            await CallbackQuery.answer(_["admin_40"], show_alert=True)
            return await CallbackQuery.edit_message_reply_markup(reply_markup=upl)

    else:
        is_non_admin = await is_nonadmin_chat(CallbackQuery.message.chat.id)
        if not is_non_admin:
            if CallbackQuery.from_user.id not in SUDOERS:
                admins = adminlist.get(CallbackQuery.message.chat.id)
                if not admins:
                    return await CallbackQuery.answer(_["admin_13"], show_alert=True)
                elif CallbackQuery.from_user.id not in admins:
                    return await CallbackQuery.answer(_["admin_14"], show_alert=True)

    if command == "Pause":
        if not await is_music_playing(chat_id):
            return await CallbackQuery.answer(_["admin_1"], show_alert=True)
        await CallbackQuery.answer()
        await music_off(chat_id)
        try:
            await BABY.pause_stream(chat_id)
            await CallbackQuery.message.reply_text(_["admin_2"].format(mention))
        except Exception as e:
            logging.error(f"Error pausing stream in chat {chat_id}: {str(e)}")
            await CallbackQuery.message.reply_text("Error while pausing the stream.")

    elif command == "Resume":
        if await is_music_playing(chat_id):
            return await CallbackQuery.answer(_["admin_3"], show_alert=True)
        await CallbackQuery.answer()
        await music_on(chat_id)
        try:
            await BABY.resume_stream(chat_id)
            await CallbackQuery.message.reply_text(_["admin_4"].format(mention))
        except Exception as e:
            logging.error(f"Error resuming stream in chat {chat_id}: {str(e)}")
            await CallbackQuery.message.reply_text("Error while resuming the stream.")

    elif command == "Stop" or command == "End":
        await CallbackQuery.answer()
        try:
            await BABY.stop_stream(chat_id)
            await set_loop(chat_id, 0)
            await CallbackQuery.message.reply_text(_["admin_5"].format(mention))
        except Exception as e:
            logging.error(f"Error stopping stream in chat {chat_id}: {str(e)}")
            await CallbackQuery.message.reply_text("Error while stopping the stream.")

    elif command == "Skip" or command == "Replay":
        check = db.get(chat_id)
        if command == "Skip":
            txt = f"Stream skipped by {mention}"
            try:
                popped = check.pop(0)
                if popped:
                    await auto_clean(popped)
                if not check:
                    await BABY.stop_stream(chat_id)
                    return await CallbackQuery.message.reply_text(txt)
            except Exception as e:
                logging.error(f"Error skipping stream in chat {chat_id}: {str(e)}")
                await CallbackQuery.message.reply_text("Error while skipping the stream.")
                return

        await CallbackQuery.answer()
        queued = check[0]["file"]
        title = check[0]["title"].title()
        user = check[0]["by"]
        duration = check[0]["dur"]
        videoid = check[0]["vidid"]

        # Skipping to the next song/video
        try:
            image = await YouTube.thumbnail(videoid, True)
            await BABY.skip_stream(chat_id, queued, video=True, image=image)
            button = stream_markup(_, videoid, chat_id)
            img = await get_thumb(videoid)
            run = await CallbackQuery.message.reply_photo(
                photo=img,
                caption=_["stream_1"].format(
                    f"https://t.me/{app.username}?start=info_{videoid}",
                    title[:23],
                    duration,
                    user,
                ),
                reply_markup=InlineKeyboardMarkup(button),
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "stream"
        except Exception as e:
            logging.error(f"Error in skipping stream for chat {chat_id}: {str(e)}")
            await CallbackQuery.message.reply_text("Error in stream skipping.")
