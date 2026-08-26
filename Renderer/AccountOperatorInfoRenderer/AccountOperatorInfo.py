from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from ..models import (
    AccountOperatorInfo,
    AccountOperatorOverview,
    AccountOperatorRarityGroup,
    AccountOperatorSkillInfo,
    ReturnResultOfAccountOperatorInfo,
)
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

# astrbot t2i 渲染选项
ACCOUNT_OPERATOR_INFO_RENDER_OPTIONS = {
    "type": "png",
    "full_page": True,
    "animations": "disabled",
    "caret": "hide",
    "viewport_width": 1120,
    "scale": "css",
}

ACCOUNT_OPERATOR_INFO_TEMPLATE = (
    Path(__file__).with_name("account_operator_info.html").read_text(encoding="utf-8")
)


class AccountOperatorInfoRenderer:
    """构造并渲染账号内三至六星干员练度排行"""

    DISPLAY_RARITIES = (6, 5, 4, 3)
    TOP_LIMIT = 10
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
    build_skill_icon_url = staticmethod(PrtsImageAssets.build_skill_icon_url)

    def __init__(self, avatar_cache_dir: str | Path, logger: Any | None = None):
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
    ) -> ReturnResultOfAccountOperatorInfo:
        try:
            # 传入从 main.py 获取的角色数据（dict 类型），将其交由 build_overview 统一解析
            overview = await asyncio.to_thread(self.build_overview, account_data)
        except (TypeError, ValueError, KeyError) as exc:
            return ReturnResultOfAccountOperatorInfo(
                status	= False,
                message	= f"干员练度数据格式异常：{exc}",
            )

        render_options = dict(ACCOUNT_OPERATOR_INFO_RENDER_OPTIONS)
        if options:
            render_options.update(options)
        try:
            image_url = await renderer.html_render(
                ACCOUNT_OPERATOR_INFO_TEMPLATE,
                overview.to_dict(),
                return_url=return_url,
                options=render_options,
            )
        except Exception as exc:
            self._log_exception("干员练度图片渲染失败", exc)
            return ReturnResultOfAccountOperatorInfo(
                status		= False,
                message		= "干员练度图片渲染失败",
                overview	= overview,
            )

        return ReturnResultOfAccountOperatorInfo(
            status		= True,
            message		= "干员练度图片渲染成功",
            image_url	= image_url,
            overview	= overview,
        )

    def build_overview(self, account_data: dict) -> AccountOperatorOverview:
        """解析传入数据，按照规则进行排序"""
        if not isinstance(account_data, dict):
            raise TypeError("account_data 必须是对象")

        status = self._require_dict(account_data.get("status"), "status")
        # 维护 chars 字段与干员名的映射
        # 这里图方便就直接每次现场维护了，一共也就 400+ 条映射，开销不是很大
        char_info_map = self._require_dict(
            account_data.get("charInfoMap"), "charInfoMap"
        )
        # 抓取角色干员列表
        char_values = account_data.get("chars")
        if not isinstance(char_values, list):
            raise TypeError("chars 必须是数组")

        # 星级分类器 grouped
        # rarity 即星级
        grouped: dict[int, list[AccountOperatorInfo]] = {
            rarity: [] for rarity in self.DISPLAY_RARITIES
        }
        # 把下标和映射绑定成一个元组，然后把这个元组丢到之前的星级分类器
        for index, value in enumerate(char_values):
            if not isinstance(value, dict):
                raise TypeError(f"chars[{index}] 必须是对象")
            # 解析角色信息
            operator = self._parse_operator(value, char_info_map, index)
            if operator is not None:
                grouped[operator.rarity].append(operator)

        # 构造便于后续解析的按照干员星级分类的元组
        # tuple(6 星干员列表, 5 星干员列表, 4 星干员列表, 3 星干员列表)
        groups = []
        for rarity in self.DISPLAY_RARITIES:
            operators_of_rarity = grouped[rarity]
            sorted_operators = sorted(
                operators_of_rarity,
                key     = self.operator_sort_key,
                reverse = True
            )
            top_operators = sorted_operators[:self.TOP_LIMIT]

            group = AccountOperatorRarityGroup(
                rarity          = rarity,
                title           = f"{rarity} 星干员练度 TOP 10",
                rarity_icon_url = self.build_rarity_icon_url(rarity),
                operators       = tuple(top_operators)
            )
            groups.append(group)

        groups = tuple(groups)

        groups = self._hydrate_operator_avatars(groups)

        return AccountOperatorOverview(
            name        = self._required_text(status.get("name"), "status.name"),
            uid         = self._required_text(status.get("uid"), "status.uid"),
            data_date   = self._format_timestamp(account_data.get("currentTs"), "currentTs"),
            groups      = groups,
        )

    def _parse_operator(
        self,
        value: dict,
        char_info_map: dict,
        index: int,
    ) -> AccountOperatorInfo | None:
        """
        解析角色信息
        传入类似
        {
            "charId": "char_002_amiya",
            "skinId": "char_002_amiya#2",
            "level": 80,
            "evolvePhase": 2,
            "potentialRank": 5,
            "mainSkillLvl": 7,
            ...
        }
        的字典，根据这些字段解析出渲染必要的信息
        """
        field_prefix = f"chars[{index}]"
        char_id = self._required_text(value.get("charId"), f"{field_prefix}.charId")
        metadata = self._optional_dict(char_info_map.get(char_id))
        rarity_value = metadata.get("rarity")
        if not isinstance(rarity_value, int) or isinstance(rarity_value, bool):
            return None
        # 修正星级表述，因为一星干员 rarity 是 0
        rarity = rarity_value + 1
        if rarity not in self.DISPLAY_RARITIES:
            return None

        name = self._text_or_default(metadata.get("name"), char_id)
        evolve_phase = self._required_int(
            value.get("evolvePhase"), f"{field_prefix}.evolvePhase"
        )
        level = self._required_int(value.get("level"), f"{field_prefix}.level")
        potential_rank = self._required_int(
            value.get("potentialRank"), f"{field_prefix}.potentialRank"
        )
        favor_percent = self._required_int(
            value.get("favorPercent"), f"{field_prefix}.favorPercent"
        )
        main_skill_level = self._required_int(
            value.get("mainSkillLvl"), f"{field_prefix}.mainSkillLvl"
        )
        gain_time = self._required_int(
            value.get("gainTime"), f"{field_prefix}.gainTime"
        )

        raw_skills = value.get("skills")
        if not isinstance(raw_skills, list):
            raise TypeError(f"{field_prefix}.skills 必须是数组")

        # 解析干员技能
        skills = []
        for skill_index, skill in enumerate(raw_skills, start=1):
            skills.append(self._parse_skill(skill, main_skill_level, field_prefix, skill_index))
        skills = tuple(skills)
        # 获取技能专精等级之和
        specialize_total = sum(skill.specialize_level for skill in skills)
        # 获取职业
        profession_code = self._text_or_default(metadata.get("profession"), "")
        profession = self.PROFESSION_NAMES.get(
            profession_code, profession_code or "职业未知"
        )
        return AccountOperatorInfo(
            char_id             = char_id,
            name                = name,
            avatar_url          = self.build_operator_avatar_url(name),
            rarity              = rarity,
            profession          = profession,
            profession_icon_url = self.build_profession_icon_url(profession),
            level               = level,
            level_text          = f"Lv.{level}",
            evolve_phase        = evolve_phase,
            elite_icon_url      = self.build_elite_icon_url(evolve_phase),
            potential_rank      = potential_rank,
            potential_text      = f"潜能 {potential_rank + 1}",
            favor_percent       = favor_percent,
            favor_text          = f"{favor_percent}%",
            main_skill_level    = main_skill_level,
            specialize_total    = specialize_total,
            gain_time           = gain_time,
            skills              = skills,
        )

    def _parse_skill(
        self,
        value: object,
        main_skill_level: int,
        field_prefix: str,
        index: int,
    ) -> AccountOperatorSkillInfo:

        if not isinstance(value, dict):
            raise TypeError(f"{field_prefix}.skills[{index}] 必须是对象")
        skill_id = self._required_text(
            value.get("id"), f"{field_prefix}.skills[{index}].id"
        )
        specialize_level = self._required_int(
            value.get("specializeLevel"),
            f"{field_prefix}.skills[{index}].specializeLevel",
        )
        return AccountOperatorSkillInfo(
            skill_id            = skill_id,
            sequence            = index + 1,
            icon_url            = self.build_skill_icon_url(skill_id),
            level_text          = f"Lv.{main_skill_level}",
            specialize_level    = specialize_level,
            specialize_text     = f"专 {specialize_level}" if specialize_level > 0 else None
        )

    @staticmethod
    def operator_sort_key(operator: AccountOperatorInfo) -> tuple[int, ...]:
        """规定排序关键字"""
        # 如果干员技能没到 7 级，就不可能专精，直接定成 0
        specialize_total = (
            operator.specialize_total if operator.main_skill_level == 7 else 0
        )
        return (
            operator.evolve_phase,
            operator.level,
            operator.main_skill_level,
            specialize_total,
            operator.potential_rank,
            operator.favor_percent,
            operator.gain_time,
        )

    def _hydrate_operator_avatars(
        self,
        groups: tuple[AccountOperatorRarityGroup, ...],
    ) -> tuple[AccountOperatorRarityGroup, ...]:
        """把排行榜中每个干员的头像 URL，尽量变成本地缓存的 base64 图片数据"""
        operators = []
        for group in groups:
            for operator in group.operators:
                operators.append(operator)

        operators = tuple(operators)

        if not operators:
            return groups
        # 启动最多 8 个线程并发下载干员头像
        # 你可能会问，为什么不复用 TCP 连接呢？
        # 其实没必要！！在同一台机子上长期跑的这个项目，会优先使用缓存中的图片数据，这也就代表，每个干员的头像最多会被请求一次
        # 时间越长，这一坨发送 HTTP 请求就会越低，直到所有 4 ~ 6 星干员的头像被全部缓存
        with ThreadPoolExecutor(max_workers=min(8, len(operators))) as executor:
            avatars = tuple(
                executor.map(
                    lambda operator: self.image_cache.get_png(
                        operator.name,
                        operator.avatar_url,
                        resource_name=(
                            f"PRTS 干员头像（operator={operator.name!r}）"
                        ),
                    ),
                    operators,
                )
            )
        # 把每个原对象和对应头像配上
        hydrated = []
        for operator, avatar in zip(operators, avatars):
            updated_operator = replace(operator, avatar_url=avatar)
            hydrated.append(updated_operator)
        hydrated = iter(hydrated)

        return_result = []
        for group in groups:
            group_operators = []
            for _ in group.operators:
                # next() 用于从迭代器中获取下一个元素，这里的 hydrated 就是迭代器，方便迭代
                # 以防后面忘记，在这里记一下
                group_operators.append(next(hydrated))

            updated_group = replace(
                group,
                operators=tuple(group_operators),
            )
            return_result.append(updated_group)
        return_result = tuple(return_result)

        return return_result

    def _format_timestamp(self, value: object, field: str) -> str:
        """格式化时间戳"""
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

    def _log_exception(self, message: str, exc: Exception) -> None:
        method = getattr(self.logger, "exception", None)
        if callable(method):
            method(f"{message}：{type(exc).__name__}: {exc}")
