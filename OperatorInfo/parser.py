# OperatorInfo/parser.py
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup, Tag

from .client import PrtsPage
from .exceptions import OperatorParseError
from .models import (
    OperatorAttribute,
    OperatorData,
    OperatorModule,
    OperatorModuleLevel,
    OperatorSkill,
)


class PrtsOperatorParser:
    _CHAR_INFO_PATTERN = re.compile(
        r"var\s+char_info\s*=\s*(\{.*?\})\s*(?://\s*语音范围限制|var\s+voice_keys)",
        re.S,
    )
    _UNLOCK_PATTERN = re.compile(r"（([^）]+)开放）")

    def parse(
        self,
        page: PrtsPage,
        portrait_url: str | None = None,
        avatar_url: str | None = None,
    ) -> OperatorData:
        soup = BeautifulSoup(page.html, "html.parser")
        char_info = self._parse_char_info(soup)
        name = str(char_info.get("name") or page.title).strip()
        if not name:
            raise OperatorParseError("页面中缺少干员名")

        warnings: list[str] = []
        attributes = self._parse_attributes(soup)
        skills = self._parse_skills(soup)
        modules = self._parse_modules(soup)
        if not attributes:
            warnings.append("未解析到干员数值")
        if not skills:
            warnings.append("未解析到技能信息")

        rarity = char_info.get("star")
        return OperatorData(
            name=name,
            rarity=int(rarity) + 1 if isinstance(rarity, int) else None,
            profession=self._optional_text(char_info.get("class")),
            branch=self._optional_text(char_info.get("branch")),
            avatar_url=avatar_url,
            portrait_url=portrait_url,
            attributes=attributes,
            skills=skills,
            modules=modules,
            source_url=page.source_url,
            revision_id=page.revision_id,
            warnings=warnings,
        )

    def _parse_char_info(self, soup: BeautifulSoup) -> dict:
        for script in soup.find_all("script"):
            source = script.string or script.get_text()
            if "var char_info" not in source:
                continue
            match = self._CHAR_INFO_PATTERN.search(source)
            if not match:
                continue
            raw = re.sub(r",\s*([}\]])", r"\1", match.group(1))
            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(result, dict):
                return result
        raise OperatorParseError("该页面不是可识别的 PRTS 干员页面（缺少 char_info）")

    def _parse_attributes(self, soup: BeautifulSoup) -> list[OperatorAttribute]:
        table = soup.select_one("table.char-base-attr-table")
        if not table:
            return []
        result: list[OperatorAttribute] = []
        for row in table.select("tr")[1:]:
            cells = row.find_all(["th", "td"], recursive=False)
            values = [self._clean_text(cell) for cell in cells]
            if len(values) < 2 or not values[0]:
                continue
            padded = (values[1:] + ["—"] * 5)[:5]
            result.append(OperatorAttribute(values[0], *[value or "—" for value in padded]))
        return result

    def _parse_skills(self, soup: BeautifulSoup) -> list[OperatorSkill]:
        heading = soup.find(id="技能")
        if not heading:
            return []
        result: list[OperatorSkill] = []
        node = heading.parent
        while True:
            node = node.find_next_sibling()
            if node is None or node.name == "h2":
                break
            if node.name != "p" or "技能" not in self._clean_text(node):
                continue
            table = node.find_next_sibling("table")
            if not table or "nomobile" not in table.get("class", []):
                continue
            skill = self._parse_skill_table(node, table)
            if skill:
                result.append(skill)
        return result

    def _parse_skill_table(self, label: Tag, table: Tag) -> OperatorSkill | None:
        first_row = table.find("tr")
        if not first_row:
            return None
        big = first_row.find("big")
        name = self._clean_text(big) if big else ""
        if not name:
            return None

        label_text = self._clean_text(label)
        unlock_match = self._UNLOCK_PATTERN.search(label_text)
        tags = [
            self._clean_text(span)
            for span in first_row.select(".mc-tooltips > span:first-child")
            if self._clean_text(span)
        ]
        rows = table.find_all("tr")
        level_row: Tag | None = None
        for row in rows:
            cells = row.find_all(["th", "td"], recursive=False)
            if cells and self._clean_text(cells[0]) in {"Rank Ⅲ", "Rank III"}:
                level_row = row
                break
        if level_row is None:
            candidates = []
            for row in rows:
                cells = row.find_all("td", recursive=False)
                if cells and re.fullmatch(r"(?:[1-9]|10)", self._clean_text(cells[0])):
                    candidates.append(row)
            level_row = candidates[-1] if candidates else None
        if level_row is None:
            return None

        cells = level_row.find_all("td", recursive=False)
        if len(cells) < 2:
            return None
        trailing = [self._clean_text(cell) or None for cell in cells[-3:]] if len(cells) >= 5 else [None] * 3
        icon = first_row.find("img")
        return OperatorSkill(
            name=name,
            description=self._clean_text(cells[1]),
            unlock=unlock_match.group(1) if unlock_match else None,
            recovery_type=tags[0] if tags else None,
            trigger_type=tags[1] if len(tags) > 1 else None,
            initial_sp=trailing[0],
            sp_cost=trailing[1],
            duration=trailing[2],
            icon_url=self._absolute_url(icon.get("src")) if icon else None,
        )

    def _parse_modules(self, soup: BeautifulSoup) -> list[OperatorModule]:
        heading = soup.find(id="模组")
        if not heading:
            return []
        section = heading.parent
        result: list[OperatorModule] = []
        for template in section.find_all_next(class_="equiptemplate"):
            previous_h2 = template.find_previous("h2")
            if previous_h2 is not section:
                break
            heading3 = template.find_previous("h3")
            name = self._clean_text(heading3) if heading3 else "未知模组"
            type_node = template.select_one(".equip-type-text")
            levels: list[OperatorModuleLevel] = []
            for index, row in enumerate(template.select(".equip-level-row"), start=1):
                stats = row.select_one(".equip-prop-list")
                effect = row.select_one(".equip-level-desc")
                levels.append(
                    OperatorModuleLevel(
                        level=index,
                        attributes=self._clean_text(stats) if stats else "",
                        effect=self._clean_text(effect) if effect else "",
                    )
                )
            result.append(
                OperatorModule(
                    name=name,
                    type_code=self._clean_text(type_node) if type_node else None,
                    levels=levels,
                )
            )
        return result

    @staticmethod
    def _clean_text(tag: Tag | None) -> str:
        if tag is None:
            return ""
        fragment = BeautifulSoup(str(tag), "html.parser")
        for hidden in fragment.select('[style*="display:none"], script, style'):
            hidden.decompose()
        return " ".join(fragment.get_text(" ", strip=True).split())

    @staticmethod
    def _optional_text(value: object) -> str | None:
        text = str(value).strip() if value is not None else ""
        return text or None

    @staticmethod
    def _absolute_url(url: str | None) -> str | None:
        if not url:
            return None
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return "https://prts.wiki" + url
        return url
