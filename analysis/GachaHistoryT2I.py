# analysis/GachaHistoryT2I.py
from pathlib import Path

GACHA_STATISTICS_RENDER_OPTIONS = {
    "type": "png",
    "full_page": True,
    "animations": "disabled",
    "caret": "hide",
}

GACHA_STATISTICS_TEMPLATE = (
    Path(__file__).with_name("templates") / "gacha_statistics.html"
).read_text(encoding="utf-8")
