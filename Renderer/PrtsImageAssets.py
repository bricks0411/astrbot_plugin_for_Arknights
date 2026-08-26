from __future__ import annotations

import hashlib
from urllib.parse import quote


class PrtsImageAssets:
    """统一构造渲染器使用的 PRTS 图片素材地址"""

    PROFESSION_NAMES = {
        "PIONEER": "先锋",
        "WARRIOR": "近卫",
        "TANK": "重装",
        "SNIPER": "狙击",
        "CASTER": "术师",
        "MEDIC": "医疗",
        "SUPPORT": "辅助",
        "SPECIAL": "特种",
    }

    @staticmethod
    def build_operator_avatar_url(name: str) -> str:
        filename = f"头像_{name}.png"
        digest = hashlib.md5(filename.encode("utf-8")).hexdigest()
        return f"https://media.prts.wiki/{digest[0]}/{digest[:2]}/{quote(filename)}"

    @staticmethod
    def build_elite_icon_url(elite_phase: int) -> str | None:
        if elite_phase not in {0, 1, 2}:
            return None
        return f"https://static.prts.wiki/charinfo/img/ui/elite{elite_phase}.png"

    @staticmethod
    def build_rarity_icon_url(rarity: int | None) -> str | None:
        if rarity not in {1, 2, 3, 4, 5, 6}:
            return None
        return f"https://static.prts.wiki/charinfo/img/star_{rarity}.png"

    @staticmethod
    def build_profession_icon_url(profession: str) -> str | None:
        if profession not in PrtsImageAssets.PROFESSION_NAMES.values():
            return None
        return f"https://static.prts.wiki/charinfo/img/class_{quote(profession)}.png"

    @staticmethod
    def build_skill_icon_url(skill_id: str) -> str:
        filename = quote(f"skill_icon_{skill_id}.png", safe="")
        return f"https://torappu.prts.wiki/assets/skill_icon/{filename}"
