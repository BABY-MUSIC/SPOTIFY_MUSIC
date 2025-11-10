import os
import re
import json
import requests
import subprocess
from urllib.parse import urlparse
from pyrogram import Client, filters
from pyrogram.enums import ChatType, ChatMemberStatus
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from config import MONGO_DB_URI
from BABYMUSIC import app
from youtubesearchpython import VideosSearch


# ================ DATABASE ===================
mongo_client = MongoClient(MONGO_DB_URI)
db = mongo_client["streambot"]
rtmp_col = db["group_rtmp"]
# ================ BASE_URL ===================
CUSTOM_API_BASE = "https://BabyAPI.Pro/video?query={vidid}"
TMP_FILE  = "/tmp/downloaded_video_{chat_id}.mp4"
PID_FILE  = "/tmp/ffmpeg_{chat_id}.pid"


# ================ HELPERS ===================
def get_rtmp(group_id: int):
    data = rtmp_col.find_one({"group_id": group_id})
    return data.get("rtmp") if data else None

def set_rtmp(user_id: int, group_id: int, link: str, group_name: str):
    rtmp_col.update_one(
        {"group_id": group_id},
        {"$set": {"user_id": user_id, "rtmp": link, "group_name": group_name}},
        upsert=True
    )

def clear_rtmp(group_id: int):
    rtmp_col.delete_one({"group_id": group_id})

def kill_ffmpeg(chat_id: int):
    pid_path = PID_FILE.format(chat_id=chat_id)
    try:
        if os.path.exists(pid_path):
            with open(pid_path) as f:
                pid = int(f.read().strip())
            os.kill(pid, 9)
            os.remove(pid_path)
        else:
            os.system("pkill -9 ffmpeg")
    except Exception as e:
        print(f"⚠️ KILL FFMPEG ERROR: {e}")


TG_LINK_RE = re.compile(
    r"^https?://t\.me/(?:(?P<c>c)/(?P<c_id>\d+)|(?P<user>[A-Za-z0-9_]+))/(?P<msg_id>\d+)$"
)

async def download_from_tg_link(link: str, dest_path: str) -> str:
    """
    Accepts a t.me message link and downloads the media in it to dest_path.
    Supports:
      - https://t.me/username/123
      - https://t.me/c/123456789/45
    Returns saved filepath.
    Raises Exception on failures.
    """
    m = TG_LINK_RE.match(link.strip())
    if not m:
        raise ValueError(f"Unsupported Telegram link: {link}")

    if m.group("c"):
        internal = int(m.group("c_id"))
        chat_id = int(f"-100{internal}")
        msg_id = int(m.group("msg_id"))
        msg = await app.get_messages(chat_id, msg_id)
    else:
        username = m.group("user")
        msg_id = int(m.group("msg_id"))
        msg = await app.get_messages(username, msg_id)

    if not msg or not (msg.video or msg.document or msg.animation):
        raise ValueError("No downloadable media found in the given Telegram message.")

    saved = await app.download_media(msg, file_name=dest_path)
    if not saved or not os.path.exists(saved):
        raise IOError("Download failed or file missing after download.")
    return saved


def extract_tg_link_from_response(resp_text: str, resp_json: dict | None) -> str | None:
    """
    Your API might return JSON or plain text. Try common keys; fallback to text scanning.
    Expected keys could be: channel_link, link, url, telegram
    """
    if resp_json:
        for key in ("channel_link", "link", "url", "telegram"):
            val = resp_json.get(key)
            if isinstance(val, str) and "t.me" in val:
                return val.strip()

    m = re.search(r"https?://t\.me/[^\s\"'>]+", resp_text)
    if m:
        return m.group(0)

    return None


def youtube_search_first_vidid(query: str) -> tuple[str, str]:
    """
    Returns (video_id, title) for best YouTube match of query.
    Raises on failure.
    """
    vs = VideosSearch(query, limit=1)
    data = vs.result()
    if not data or not data.get("result"):
        raise ValueError("No YouTube results.")
    r = data["result"][0]
    vidid = r.get("id")
    title = r.get("title") or "Unknown Title"
    if not vidid:
        raise ValueError("Video ID not found.")
    return vidid, title

@app.on_message(filters.command("setrtmp"))
async def set_rtmp_cmd(client, message):
    if message.chat.type != ChatType.PRIVATE:
        return await message.reply("**⚠️ Use this command in private chat**")

    if len(message.command) < 3:
        return await message.reply("**❌ ᴜsᴀɢᴇ :-** /setrtmp group_id rtmp_link")

    try:
        group_id = int(message.command[1])
    except ValueError:
        return await message.reply("**⚠️ Invalid group id**")

    link = message.command[2]
    if not link.startswith("rtmp"):
        return await message.reply("**⚠️ Invalid RTMP link.**")

    try:
        chat_info = await client.get_chat(group_id)
        group_name = chat_info.title
    except:
        group_name = "Unknown Group"

    kill_ffmpeg(group_id)
    set_rtmp(message.from_user.id, group_id, link, group_name)

    await message.reply(
        f"**✅ RTMP Link set for {group_name}** (`{group_id}`)\n\n**link :-** {link}"
    )


@app.on_message(filters.command("playstream"))
async def play_stream(client, message):
    chat = message.chat
    user_id = message.from_user.id

    if chat.type == ChatType.PRIVATE:
        user_groups = rtmp_col.find_one({"user_id": user_id})
        if not user_groups:
            return await message.reply(
                "**⚠️ Please set RTMP first using /setrtmp group_id rtmp_link**"
            )
        else:
            return await message.reply(
                "**✅ Now use :-** `/playstream song name` **in your group.**"
            )

    elif chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        group_id = chat.id
        user_rtmp = get_rtmp(group_id)

        if not user_rtmp:
            return await message.reply(
                "**⚠️ This group has no RTMP Set.**\n\n**👉 Set it in private using** `/setrtmp`"
            )

        if len(message.command) < 2:
            return await message.reply("**❌ Uses :-** `/playstream song name`")

        await message.delete()
        query = " ".join(message.command[1:])
        user_mention = message.from_user.mention if message.from_user else "Unknown User"
        working = await message.reply(f"**🔎 Searching... :-** {query}")

        try:
            vidid, title = youtube_search_first_vidid(query)
            url = CUSTOM_API_BASE.format(vidid=vidid)
            r = requests.get(url, timeout=60)
            resp_text = r.text
            resp_json = None
            try:
                resp_json = r.json()
            except Exception:
                pass

            tg_link = extract_tg_link_from_response(resp_text, resp_json)
            if not tg_link:
                return await working.edit("**❌ API Response fail.**")
            tmp_path = TMP_FILE.format(chat_id=group_id)
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except:
                    pass

            downloaded_path = await download_from_tg_link(tg_link, tmp_path)

        except Exception as e:
            return await working.edit(f"**❌ Error :-** `{e}`")

        ffmpeg_command = [
            "ffmpeg", "-re", "-i", downloaded_path,
            "-c:v", "copy", "-c:a", "aac",
            "-f", "flv", user_rtmp
        ]

        try:
            process = subprocess.Popen(ffmpeg_command)
            pid_path = PID_FILE.format(chat_id=group_id)
            with open(pid_path, "w") as f:
                f.write(str(process.pid))

            await working.delete()

            msg = (
                f"**📡 Streaming now...**\n\n"
                f"**🎵 Title :-** {title}\n\n"
                f"**🙋 Played by :-** {user_mention}"
            )

            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    text="✙ ʌᴅᴅ ϻє ɪη ʏσυʀ ɢʀσυᴘ ✙",
                    url=f"https://t.me/{app.username}?startgroup=true"
                )]
            ])

            await message.reply(msg, reply_markup=buttons)

        except Exception as e:
            await message.reply(f"**❌ ғғᴍᴘᴇɢ ғᴀɪʟᴇᴅ :-** `{e}`")


# ================= END STREAM ==================
@app.on_message(filters.command("endstream"))
async def end_stream(client, message):
    user_id = message.from_user.id
    chat = message.chat

    if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        try:
            member = await client.get_chat_member(chat.id, user_id)
            if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                return await message.reply("**⚠️ ᴏɴʟʏ ᴀᴅᴍɪɴs ᴄᴀɴ sᴛᴏᴘ ᴛʜᴇ sᴛʀᴇᴀᴍ !!**")
        except Exception as e:
            return await message.reply(f"**❌ ᴇʀʀᴏʀ :-** {e}")

    kill_ffmpeg(chat.id)
    tmp_path = TMP_FILE.format(chat_id=chat.id)
    if os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except:
            pass

    await message.reply(f"**🛑 sᴛʀᴇᴀᴍ sᴛᴏᴘᴘᴇᴅ ʙʏ :-** {message.from_user.mention}")
