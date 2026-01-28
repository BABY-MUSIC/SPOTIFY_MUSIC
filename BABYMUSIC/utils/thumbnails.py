# thumbnail.py
# Always working YouTube thumbnail generator
# Fast | Simple | No API | No Download | No PIL

YOUTUBE_THUMB_BASE = "https://i.ytimg.com/vi"

async def get_thumb(videoid: str, chat_id=None):
    """
    Always returns a working YouTube thumbnail
    Works for every public video
    """
    return f"{YOUTUBE_THUMB_BASE}/{videoid}/hqdefault.jpg"
