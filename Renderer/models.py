# Renderer/models.py
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True, frozen=True)
class AssistCharInfo:
    char_id: str
    name: str
    avatar_url: str
    rarity: int | None
    rarity_icon_url: str | None
    elite_phase: int
    elite_icon_url: str | None
    profession: str
    profession_icon_url: str | None
    branch: str
    level_text: str
    potential_text: str
    skill_text: str
    module_text: str | None


@dataclass(slots=True, frozen=True)
class AccountOverview:
    name: str
    uid: str
    level_text: str
    level_progress_percent: float
    stage_text: str
    register_date: str
    last_online_date: str
    ap_text: str
    data_date: str
    assist_chars: tuple[AssistCharInfo, ...]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class ReturnResultOfAccountInfo:
    status: bool
    message: str | None = None
    image_url: str | None = None
    overview: AccountOverview | None = None


@dataclass(slots=True, frozen=True)
class AccountOperatorSkillInfo:
    skill_id: str
    sequence: int
    icon_url: str
    level_text: str
    specialize_level: int
    specialize_text: str | None


@dataclass(slots=True, frozen=True)
class AccountOperatorInfo:
    char_id: str
    name: str
    avatar_url: str
    rarity: int
    profession: str
    profession_icon_url: str | None
    level: int
    level_text: str
    evolve_phase: int
    elite_icon_url: str | None
    potential_rank: int
    potential_text: str
    favor_percent: int
    favor_text: str
    main_skill_level: int
    specialize_total: int
    gain_time: int
    skills: tuple[AccountOperatorSkillInfo, ...]


@dataclass(slots=True, frozen=True)
class AccountOperatorRarityGroup:
    rarity: int
    title: str
    rarity_icon_url: str | None
    operators: tuple[AccountOperatorInfo, ...]


@dataclass(slots=True, frozen=True)
class AccountOperatorOverview:
    name: str
    uid: str
    data_date: str
    groups: tuple[AccountOperatorRarityGroup, ...]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class ReturnResultOfAccountOperatorInfo:
    status: bool
    message: str | None = None
    image_url: str | None = None
    overview: AccountOperatorOverview | None = None
