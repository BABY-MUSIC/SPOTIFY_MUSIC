import os
import re
import io
import time
import json
import asyncio
import random
import aiohttp
from urllib.parse import quote_plus
from pymongo import MongoClient

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import RPCError

from youtubesearchpython.__future__ import VideosSearch

from ntgcalls import NekoTgCalls as TgCalls
from ntgcalls.types import AudioStream

from PIL import Image, ImageDraw

# ---------------- CONFIG ----------------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
STRING_SESSION = os.getenv("STRING_SESSION")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
API_BASE = os.getenv("API_BASE").rstrip("/") if os.getenv("API_BASE") else ""
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
DURATION_LIMIT = 7200  # 2 hours

os.makedirs("downloads", exist_ok=True)

# ---------------- CLIENTS ----------------
bot = Client("music-bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user = Client("music-user", api_id=API_ID, api_hash=API_HASH, session_string=STRING_SESSION)
vc = TgCalls(user)

mongo = MongoClient(MONGO_URI)
db = mongo["music_db"]
col = db["queues"]

# ---------------- HELPERS ----------------
def sec_to_time(sec: int):
    m, s = divmod(int(sec), 60)
    return f"{m:02d}:{s:02d}"

def sec(s):
    try:
        parts = s.split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        return int(parts[0])
    except:
        return 0

async def youtube_search(query: str):
    search = VideosSearch(query, limit=1)
    result = (await search.next())["result"][0]
    vidid = result["id"]
    title = result["title"]
    duration = result.get("duration", "0:00")
    thumb = result["thumbnails"][0]["url"]
    return vidid, title, duration, thumb

async def get_api_link(vidid: str) -> str:
    """Fetch only 'link' from API JSON."""
    if not API_BASE:
        return None
    url = f"{API_BASE}/song?query={quote_plus(vidid)}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            if r.status == 200:
                j = await r.json()
                return j.get("link")
    return None

def get_queue(chat_id):
    q = col.find_one({"chat_id": chat_id}) or {"chat_id": chat_id, "queue": [], "now": None}
    return q

def save_queue(q):
    col.update_one({"chat_id": q["chat_id"]}, {"$set": q}, upsert=True)

async def background_download_tme(link, path):
    """If API link is a Telegram message (t.me/<c>/<id>), download in background."""
    try:
        parsed = re.search(r"t\.me\/(.*?)\/(\d+)", link)
        if not parsed:
            return
        cname, msgid = parsed.group(1), int(parsed.group(2))
        msg = await user.get_messages(cname, msgid)
        await msg.download(file_name=path)
    except Exception as e:
        print("BG download error:", e)

# --- DP + Thumbnail Composite ---
async def get_user_dp_bytes(user_id: int) -> bytes | None:
    try:
        photos = await bot.get_profile_photos(user_id, limit=1)
        if not photos or len(photos) == 0:
            return None
        f = await bot.download_media(photos[0].file_id, in_memory=True)
        return f.getbuffer().tobytes()
    except Exception:
        return None

async def fetch_image_bytes(url: str) -> bytes | None:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=20) as r:
                if r.status == 200:
                    return await r.read()
    except Exception:
        return None
    return None

def circular_mask(size: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)
    return mask

async def make_thumb_with_user(thumb_url: str | None, req_user_id: int | None) -> bytes | None:
    """Create 640x360 JPEG using YouTube thumb + requester's circular DP at bottom-right."""
    W, H = 640, 360
    base = Image.new("RGB", (W, H), (24, 24, 24))
    # base thumb
    if thumb_url:
        raw = await fetch_image_bytes(thumb_url)
        if raw:
            try:
                img = Image.open(io.BytesIO(raw)).convert("RGB")
                base.paste(img.resize((W, H)), (0, 0))
            except Exception:
                pass
    # requester DP
    if req_user_id:
        dp_raw = await get_user_dp_bytes(req_user_id)
        if dp_raw:
            try:
                dp = Image.open(io.BytesIO(dp_raw)).convert("RGB")
                dp = dp.resize((108, 108))
                mask = circular_mask(108)
                # subtle border circle behind
                border = Image.new("RGB", (116, 116), (255, 255, 255))
                bmask = circular_mask(116)
                base.paste(border, (W-116-16, H-116-16), bmask)
                base.paste(dp, (W-108-20, H-108-20), mask)
            except Exception:
                pass
    out = io.BytesIO()
    base.save(out, format="JPEG", quality=85)
    out.seek(0)
    return out.getvalue()

# ---------------- PLAYER ----------------
async def join_and_stream(chat_id, link):
    await vc.join_group_call(chat_id, AudioStream(link))
    print(f"🎧 Streaming: {link}")

async def play_next(chat_id):
    data = get_queue(chat_id)
    if not data["queue"]:
        try:
            await vc.leave_group_call(chat_id)
        except Exception:
            pass
        data["now"] = None
        save_queue(data)
        return

    song = data["queue"].pop(0)
    save_queue(data)

    title = song["title"]
    link = song["link"]
    thumb = song["thumb"]
    dur = song["dur"]
    req_name = song["req"]
    req_id = song.get("req_id")

    # start progressive stream immediately
    await join_and_stream(chat_id, link)

    # background download if telegram link
    asyncio.create_task(background_download_tme(link, f"downloads/{int(time.time())}_{random.randint(100,999)}.mp3"))

    # compose thumbnail with requester DP (fallback to original thumb URL or generic)
    composed = await make_thumb_with_user(thumb, req_id)
    photo_to_send = composed or thumb or "https://i.ibb.co/4pDNDk1/music.jpg"

    msg = await bot.send_photo(
        chat_id,
        photo=photo_to_send,
        caption=f"🎵 **{title}**\n⏱ `{dur}`\n👤 Requested by: {req_name}",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⏭ Skip", callback_data=f"skip_{chat_id}")],
             [InlineKeyboardButton("📜 Queue", callback_data=f"queue_{chat_id}")]]
        )
    )

    data["now"] = {"msg": msg.id, "start": time.time(), "dur": sec(dur)}
    save_queue(data)
    asyncio.create_task(update_progress(chat_id))

async def update_progress(chat_id):
    """Every 5s update elapsed; auto-next when duration completes."""
    while True:
        await asyncio.sleep(5)
        data = get_queue(chat_id)
        now = data.get("now")
        if not now:
            return
        elapsed = int(time.time() - now["start"])
        dur = now.get("dur", 0)
        if dur and elapsed >= dur:
            try:
                await vc.leave_group_call(chat_id)
            except Exception:
                pass
            await play_next(chat_id)
            return
        try:
            await bot.edit_message_caption(
                chat_id,
                now["msg"],
                caption=f"🎶 Playing… {sec_to_time(elapsed)} / {sec_to_time(dur)}",
            )
        except RPCError:
            pass

# ---------------- COMMANDS ----------------
@bot.on_message(filters.command("start"))
async def start_cmd(_, m: Message):
    await m.reply_text(
        "👋 Hey! I'm an instant YouTube streamer.\n\n"
        "• /play <song name>\n"
        "   → YouTube se vidid, API se link (JSON: link only), instant stream\n"
        "• DP overlay on thumbnail\n"
        "• Queue + background download\n"
    )

@bot.on_message(filters.command("play") & filters.group)
async def play_cmd(_, m: Message):
    if len(m.command) < 2 and not (m.reply_to_message and (m.reply_to_message.text or m.reply_to_message.caption)):
        return await m.reply_text("Usage: /play <song name>")

    query = None
    if len(m.command) >= 2:
        query = m.text.split(None, 1)[1].strip()
    elif m.reply_to_message:
        query = (m.reply_to_message.text or m.reply_to_message.caption).strip()

    await m.reply_chat_action("typing")

    # Step 1: YouTube search → vidid, title, duration, thumb
    try:
        vidid, title, duration, thumb = await youtube_search(query)
    except Exception:
        return await m.reply_text("❌ YouTube search failed.")

    # Step 2: API call /song?query=vidid → JSON{link}
    link = await get_api_link(vidid)
    if not link:
        return await m.reply_text("❌ API didn’t return a link.")

    # Step 3: Queue
    data = get_queue(m.chat.id)
    data["queue"].append({
        "title": title,
        "link": link,
        "thumb": thumb,
        "dur": duration,
        "req": (m.from_user.first_name if m.from_user else "User"),
        "req_id": (m.from_user.id if m.from_user else None),
    })
    save_queue(data)

    # Step 4: If idle → play; else queued
    # ntgcalls doesn't expose active_calls like PyTgCalls; try join status by now-state
    now_state = data.get("now")
    if not now_state:
        await play_next(m.chat.id)
        await m.reply_text(f"▶️ Now playing: **{title}**")
    else:
        pos = len(data["queue"])
        await m.reply_text(f"➕ Added to queue (#{pos}): **{title}**")

@bot.on_callback_query(filters.regex(r"^skip_(\-\d+|\d+)$"))
async def skip_cb(_, q):
    chat_id = int(q.data.split("_")[1])
    try:
        await vc.leave_group_call(chat_id)
    except Exception:
        pass
    await play_next(chat_id)
    await q.answer("⏭ Skipped!")

@bot.on_callback_query(filters.regex(r"^queue_(\-\d+|\d+)$"))
async def cb_queue(_, q):
    chat_id = int(q.data.split("_")[1])
    await queue_cmd(_, type("M", (), {"chat": type("C", (), {"id": chat_id})})())

@bot.on_message(filters.command("skip") & filters.group)
async def skip_cmd(_, m: Message):
    try:
        await vc.leave_group_call(m.chat.id)
    except Exception:
        pass
    await play_next(m.chat.id)
    await m.reply_text("⏭ Skipped current track.")

@bot.on_message(filters.command("queue") & filters.group)
async def queue_cmd(_, m: Message):
    data = get_queue(m.chat.id)
    q = data.get("queue", [])
    if not q:
        return await m.reply_text("📭 Queue empty.")
    text = "\n".join([f"{i+1}. {x['title']} ({x['dur']})" for i, x in enumerate(q)])
    await m.reply_text("📜 **Queue:**\n" + text)

@bot.on_message(filters.command("stop") & filters.group)
async def stop_cmd(_, m: Message):
    try:
        await vc.leave_group_call(m.chat.id)
    except Exception:
        pass
    data = get_queue(m.chat.id)
    data["queue"] = []
    data["now"] = None
    save_queue(data)
    await m.reply_text("⏹ Stopped and cleared queue.")

# ---------------- STARTUP ----------------
async def main():
    await bot.start()
    await user.start()
    await vc.start()
    print("✅ Bot started with String Session Userbot.")
    if OWNER_ID:
        try:
            await bot.send_message(OWNER_ID, "🚀 Music Bot started successfully!")
        except:
            pass
    await asyncio.get_event_loop().create_future()

if __name__ == "__main__":
    try:
        import uvloop; uvloop.install()
    except Exception:
        pass
    asyncio.run(main())
