THUMB_BASE = "https://i.ytimg.com/vi"

def get_thumb(videoid: str, chat_id=None) -> str:
    return f"{THUMB_BASE}/{videoid}/maxresdefault.jpg"
