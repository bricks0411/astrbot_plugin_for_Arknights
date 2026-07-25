from __future__ import annotations

from .models import OperatorData


def build_operator_text_summary(
    operator: OperatorData,
    *,
    max_length: int = 3500,
) -> str:
    """构造适合消息平台发送的干员百科文本兜底。"""
    identity = [f"【{operator.name}】"]
    if operator.rarity:
        identity.append("★" * operator.rarity)
    role = " · ".join(
        value for value in (operator.profession, operator.branch) if value
    )
    if role:
        identity.append(role)

    sections = [" ".join(identity)]

    if operator.attributes:
        attribute_lines = ["基础数值："]
        for attribute in operator.attributes:
            values = (
                f"精0 Lv1 {attribute.elite0_level1} / "
                f"精0满级 {attribute.elite0_max} / "
                f"精1满级 {attribute.elite1_max} / "
                f"精2满级 {attribute.elite2_max}"
            )
            if attribute.trust_bonus != "—":
                values += f" / 信赖 {attribute.trust_bonus}"
            attribute_lines.append(f"- {attribute.name}：{values}")
        sections.append("\n".join(attribute_lines))

    if operator.skills:
        skill_lines = ["技能："]
        for skill in operator.skills:
            details = " / ".join(
                value
                for value in (
                    skill.unlock,
                    skill.recovery_type,
                    skill.trigger_type,
                    f"初始 {skill.initial_sp}" if skill.initial_sp else None,
                    f"消耗 {skill.sp_cost}" if skill.sp_cost else None,
                    f"持续 {skill.duration}" if skill.duration else None,
                )
                if value
            )
            title = f"- {skill.name}"
            if details:
                title += f"（{details}）"
            skill_lines.append(title)
            if skill.description:
                skill_lines.append(f"  {_compact(skill.description, 260)}")
        sections.append("\n".join(skill_lines))

    if operator.modules:
        module_lines = ["模组："]
        for module in operator.modules:
            label = module.name
            if module.type_code:
                label += f" [{module.type_code}]"
            module_lines.append(f"- {label}")
            for level in module.levels:
                content = "；".join(
                    value for value in (level.attributes, level.effect) if value
                )
                if content:
                    module_lines.append(
                        f"  Lv.{level.level}：{_compact(content, 220)}"
                    )
        sections.append("\n".join(module_lines))

    if operator.warnings:
        sections.append("数据提示：" + "；".join(operator.warnings))
    if operator.source_url:
        sections.append(f"数据来源：{operator.source_url}")

    text = "\n\n".join(sections)
    minimum_length = 200
    limit = max(minimum_length, max_length)
    if len(text) <= limit:
        return text
    suffix = "\n\n（内容较长，文本兜底已截断；完整内容请稍后重试图片查询）"
    return text[: limit - len(suffix)].rstrip() + suffix


def _compact(value: str, limit: int) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
