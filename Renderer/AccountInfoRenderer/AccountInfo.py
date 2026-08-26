# Renderer/AccountInfoRenderer/AccountInfo.py
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from ..models import AccountOverview, AssistCharInfo, ReturnResultOfAccountInfo
from ..PrtsImageAssets import PrtsImageAssets
from ..PrtsImageCache import PrtsImageCache


class HtmlRenderer(Protocol):
    async def html_render(
        self,
        tmpl: str,
        data: dict,
        return_url: bool = True,
        options: dict | None = None,
    ) -> str: ...


ACCOUNT_INFO_RENDER_OPTIONS = {
    "type": "png",
    "full_page": True,
    "animations": "disabled",
    "caret": "hide",
    # Keep the T2I viewport aligned with the fixed page width in the template.
    # Without this, the service's default 1280px viewport adds a large right margin.
    "viewport_width": 872,
    "scale": "css",
}

ACCOUNT_INFO_TEMPLATE = (
    Path(__file__).with_name("account_info.html").read_text(encoding="utf-8")
)


class AccountInfoRenderer:
    DISPLAY_TIMEZONE = ZoneInfo("Asia/Shanghai")

    PROFESSION_NAMES = PrtsImageAssets.PROFESSION_NAMES
    build_operator_avatar_url = staticmethod(
        PrtsImageAssets.build_operator_avatar_url
    )
    build_elite_icon_url = staticmethod(PrtsImageAssets.build_elite_icon_url)
    build_rarity_icon_url = staticmethod(PrtsImageAssets.build_rarity_icon_url)
    build_profession_icon_url = staticmethod(
        PrtsImageAssets.build_profession_icon_url
    )

    def __init__(self, avatar_cache_dir: str | Path, logger: Any | None = None):
        """初始化角色总览渲染器和助战头像缓存"""
        self.avatar_cache_dir = Path(avatar_cache_dir)
        self.avatar_cache_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger
        self.image_cache = PrtsImageCache(self.avatar_cache_dir, logger=logger)

    async def arender(
        self,
        renderer: HtmlRenderer,
        account_data: dict,
        *,
        return_url: bool = True,
        options: dict | None = None,
    ) -> ReturnResultOfAccountInfo:
        """解析完整森空岛 data 对象并渲染角色信息总览"""
        try:
            overview = await asyncio.to_thread(self.build_overview, account_data)
        except (TypeError, ValueError, KeyError) as exc:
            return ReturnResultOfAccountInfo(
                status  = False,
                message = f"角色信息格式异常：{exc}",
            )

        render_options = dict(ACCOUNT_INFO_RENDER_OPTIONS)
        if options:
            render_options.update(options)
        try:
            image_url = await renderer.html_render(
                ACCOUNT_INFO_TEMPLATE,
                overview.to_dict(),
                return_url  = return_url,
                options     = render_options,
            )
        except Exception as exc:
            self._log_exception("角色信息图片渲染失败", exc)
            return ReturnResultOfAccountInfo(
                status      = False,
                message     = "角色信息图片渲染失败",
                overview    = overview,
            )
        return ReturnResultOfAccountInfo(
            status      = True,
            message     = "角色信息图片渲染成功",
            image_url   = image_url,
            overview    = overview,
        )

    def build_overview(self, account_data: dict) -> AccountOverview:
        """从完整 data 对象构造与 HTML 模板无关的总览模型"""
        if not isinstance(account_data, dict):
            raise TypeError("account_data 必须是对象")

        status = self._require_dict(account_data.get("status"), "status")
        ap = self._require_dict(status.get("ap"), "status.ap")
        exp = self._require_dict(status.get("exp"), "status.exp")
        char_info_map = self._optional_dict(account_data.get("charInfoMap"))
        stage_info_map = self._optional_dict(account_data.get("stageInfoMap"))

        stage_id = self._required_text(
            status.get("mainStageProgress"), "status.mainStageProgress"
        )
        stage_info = self._optional_dict(stage_info_map.get(stage_id))
        stage_code = self._text_or_default(stage_info.get("code"), stage_id)
        stage_name = self._text_or_default(stage_info.get("name"), "名称未知")

        assist_values = account_data.get("assistChars")
        if assist_values is None:
            assist_values = []
        if not isinstance(assist_values, list):
            raise TypeError("assistChars 必须是数组")

        assist_chars = tuple(
            self._parse_assist_char(item, char_info_map, index)
            for index, item in enumerate(assist_values)
            if isinstance(item, dict)
        )

        ap_current = self._required_int(ap.get("current"), "status.ap.current")
        ap_max = self._required_int(ap.get("max"), "status.ap.max")
        exp_current = self._required_int(exp.get("current"), "status.exp.current")
        exp_max = self._required_int(exp.get("max"), "status.exp.max")
        if ap_max < 0:
            raise ValueError("status.ap.max 不能小于 0")
        if exp_current < 0 or exp_max < 0:
            raise ValueError("status.exp.current 和 status.exp.max 不能小于 0")
        level_progress_percent = (
            100.0 if exp_max == 0 else min(100.0, max(0.0, exp_current / exp_max * 100))
        )

        overview = AccountOverview(
            name=self._required_text(status.get("name"), "status.name"),
            uid=self._required_text(status.get("uid"), "status.uid"),
            level_text=f"Lv.{self._required_int(status.get('level'), 'status.level')}",
            level_progress_percent=round(level_progress_percent, 2),
            stage_text=f"{stage_code} / {stage_name}",
            register_date=self._format_timestamp(
                status.get("registerTs"), "status.registerTs"
            ),
            last_online_date=self._format_timestamp(
                status.get("lastOnlineTs"), "status.lastOnlineTs"
            ),
            ap_text=f"{ap_current} / {ap_max}",
            data_date=self._format_timestamp(
                account_data.get("currentTs"), "currentTs"
            ),
            assist_chars=assist_chars,
        )
        return replace(
            overview,
            assist_chars=self._hydrate_avatar_cache(overview.assist_chars),
        )

    def build_text_summary(self, overview: AccountOverview) -> str:
        """构造 T2I 失败时的纯文本兜底"""
        lines = [
            f"博士：{overview.name}",
            f"UID：{overview.uid}",
            f"等级：{overview.level_text}",
            f"主线进度：{overview.stage_text}",
            f"入职日：{overview.register_date}",
            f"最近在线：{overview.last_online_date}",
            f"剩余理智：{overview.ap_text}",
            f"数据截至：{overview.data_date}",
        ]
        if overview.assist_chars:
            lines.append("助战干员：")
            for char in overview.assist_chars:
                details = " / ".join(
                    value
                    for value in (
                        f"精英 {char.elite_phase} · {char.level_text}",
                        char.potential_text,
                        char.skill_text,
                        char.module_text,
                    )
                    if value
                )
                lines.append(f"- {char.name}：{details}")
        else:
            lines.append("助战干员：未设置")
        return "\n".join(lines)

    def _parse_assist_char(
        self,
        value: dict,
        char_info_map: dict,
        index: int,
    ) -> AssistCharInfo:
        char_id = self._required_text(
            value.get("charId"), f"assistChars[{index}].charId"
        )
        metadata = self._optional_dict(char_info_map.get(char_id))
        name = self._text_or_default(metadata.get("name"), char_id)
        evolve_phase = self._required_int(
            value.get("evolvePhase"), f"assistChars[{index}].evolvePhase"
        )
        level = self._required_int(value.get("level"), f"assistChars[{index}].level")
        potential_rank = self._required_int(
            value.get("potentialRank"), f"assistChars[{index}].potentialRank"
        )
        main_skill_level = self._required_int(
            value.get("mainSkillLvl"), f"assistChars[{index}].mainSkillLvl"
        )
        specialize_level = self._required_int(
            value.get("specializeLevel"), f"assistChars[{index}].specializeLevel"
        )

        equip = value.get("equip")
        module_text = None
        if isinstance(equip, dict) and equip:
            module_level = equip.get("level")
            module_text = (
                f"模组 Lv.{module_level}"
                if isinstance(module_level, int) and not isinstance(module_level, bool)
                else "已装配模组"
            )

        rarity_value = metadata.get("rarity")
        rarity = (
            rarity_value + 1
            if isinstance(rarity_value, int) and not isinstance(rarity_value, bool)
            else None
        )
        profession_code = self._text_or_default(metadata.get("profession"), "")
        profession = self.PROFESSION_NAMES.get(
            profession_code, profession_code or "职业未知"
        )
        skill_text = f"技能 Lv.{main_skill_level}"
        if specialize_level > 0:
            skill_text += f" · 专精 {specialize_level}"

        return AssistCharInfo(
            char_id             = char_id,
            name                = name,
            avatar_url          = self.build_operator_avatar_url(name),
            rarity              = rarity,
            rarity_icon_url     = self.build_rarity_icon_url(rarity),
            elite_phase         = evolve_phase,
            elite_icon_url      = self.build_elite_icon_url(evolve_phase),
            profession          = profession,
            profession_icon_url = self.build_profession_icon_url(profession),
            branch              = self._text_or_default(metadata.get("subProfessionName"), "分支未知"),
            level_text          = f"Lv.{level}",
            potential_text      = f"潜能 {potential_rank + 1}",
            skill_text          = skill_text,
            module_text         = module_text,
        )

    def _hydrate_avatar_cache(
        self, assist_chars: tuple[AssistCharInfo, ...]
    ) -> tuple[AssistCharInfo, ...]:
        if not assist_chars:
            return assist_chars
        with ThreadPoolExecutor(max_workers=min(3, len(assist_chars))) as executor:
            avatars = tuple(
                executor.map(
                    lambda char: self.image_cache.get_png(
                        char.name,
                        char.avatar_url,
                        resource_name=f"PRTS 助战头像（operator={char.name!r}）",
                    ),
                    assist_chars,
                )
            )
        return tuple(
            replace(char, avatar_url=avatar)
            for char, avatar in zip(assist_chars, avatars)
        )

    def _format_timestamp(self, value: object, field: str) -> str:
        timestamp = self._required_int(value, field)
        try:
            return datetime.fromtimestamp(timestamp, self.DISPLAY_TIMEZONE).strftime(
                "%Y-%m-%d"
            )
        except (OverflowError, OSError, ValueError) as exc:
            raise ValueError(f"{field} 不是有效的秒级时间戳") from exc

    @staticmethod
    def _require_dict(value: object, field: str) -> dict:
        if not isinstance(value, dict):
            raise TypeError(f"{field} 必须是对象")
        return value

    @staticmethod
    def _optional_dict(value: object) -> dict:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _required_text(value: object, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} 必须是非空字符串")
        return value

    @staticmethod
    def _text_or_default(value: object, default: str) -> str:
        return value.strip() if isinstance(value, str) and value.strip() else default

    @staticmethod
    def _required_int(value: object, field: str) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{field} 必须是整数")
        return value

    def _log(self, level: str, message: str) -> None:
        method = getattr(self.logger, level, None)
        if callable(method):
            method(message)

    def _log_exception(self, message: str, exc: Exception) -> None:
        method = getattr(self.logger, "exception", None)
        if callable(method):
            method(f"{message}：{type(exc).__name__}: {exc}")
