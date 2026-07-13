# OperatorInfo/models.py
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class OperatorAttribute:
    name: str
    elite0_level1: str = "—"
    elite0_max: str = "—"
    elite1_max: str = "—"
    elite2_max: str = "—"
    trust_bonus: str = "—"


@dataclass(slots=True)
class OperatorSkill:
    name: str
    description: str
    unlock: str | None = None
    recovery_type: str | None = None
    trigger_type: str | None = None
    initial_sp: str | None = None
    sp_cost: str | None = None
    duration: str | None = None
    icon_url: str | None = None


@dataclass(slots=True)
class OperatorModuleLevel:
    level: int
    attributes: str = ""
    effect: str = ""


@dataclass(slots=True)
class OperatorModule:
    name: str
    type_code: str | None = None
    levels: list[OperatorModuleLevel] = field(default_factory=list)


@dataclass(slots=True)
class OperatorData:
    name: str
    rarity: int | None = None
    profession: str | None = None
    branch: str | None = None
    avatar_url: str | None = None
    avatar_path: str | None = None
    portrait_url: str | None = None
    portrait_path: str | None = None
    attributes: list[OperatorAttribute] = field(default_factory=list)
    skills: list[OperatorSkill] = field(default_factory=list)
    modules: list[OperatorModule] = field(default_factory=list)
    source_url: str | None = None
    revision_id: int | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "OperatorData":
        return cls(
            name=value["name"],
            rarity=value.get("rarity"),
            profession=value.get("profession"),
            branch=value.get("branch"),
            avatar_url=value.get("avatar_url"),
            avatar_path=value.get("avatar_path"),
            portrait_url=value.get("portrait_url"),
            portrait_path=value.get("portrait_path"),
            attributes=[OperatorAttribute(**item) for item in value.get("attributes", [])],
            skills=[OperatorSkill(**item) for item in value.get("skills", [])],
            modules=[
                OperatorModule(
                    name=item["name"],
                    type_code=item.get("type_code"),
                    levels=[OperatorModuleLevel(**level) for level in item.get("levels", [])],
                )
                for item in value.get("modules", [])
            ],
            source_url=value.get("source_url"),
            revision_id=value.get("revision_id"),
            warnings=list(value.get("warnings", [])),
        )
