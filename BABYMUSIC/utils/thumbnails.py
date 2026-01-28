import os
import aiohttp
from io import BytesIO
from PIL import Image

YOUTUBE_THUMB_BASE = "https://i.ytimg.com/vi_webp"
CACHE_DIR = "thumb_cache"

os.makedirs(CACHE_DIR, exist_ok=True)

async def get_thumb(videoid: str, chat_id=None):
    cache_path = f"{CACHE_DIR}/{videoid}.jpg"

    # 1️⃣ cache hit
    if os.path.exists(cache_path):
        return cache_path

    url = f"{YOUTUBE_THUMB_BASE}/{videoid}/maxresdefault.webp"

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; TelegramBot/1.0)"
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url, timeout=10) as resp:
            if resp.status != 200:
                return None

            data = await resp.read()
            if len(data) < 1024:   # empty / fake response guard
                return None

    # 2️⃣ convert webp → jpg (NO resize, web-like quality)
    img = Image.open(BytesIO(data)).convert("RGB")
    img.save(
        cache_path,
        "JPEG",
        quality=95,
        subsampling=0,
        optimize=True
    )

    return cache_path
