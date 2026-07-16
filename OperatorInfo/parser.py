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
    _CHAR_INFO_ASSIGNMENT_PATTERN = re.compile(r"var\s+char_info\s*=\s*")
    _UNLOCK_PATTERN = re.compile(r"（([^）]+)开放）")

    def parse(
        self,
        page: PrtsPage,
        portrait_url: str | None = None,
        avatar_url: str | None = None,
    ) -> OperatorData:
        """
        html 解析逻辑
        通过 BeautifulSoup 解析给定的 html page，获取必要信息后加工
        封装为自定义数据类 OperatorData 返回给调用者
        """
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
        return OperatorData (
            name            = name,
            rarity          = int(rarity) + 1 if isinstance(rarity, int) else None,
            profession      = self._optional_text(char_info.get("class")),
            branch          = self._optional_text(char_info.get("branch")),
            avatar_url      = avatar_url,
            portrait_url    = portrait_url,
            attributes      = attributes,
            skills          = skills,
            modules         = modules,
            source_url      = page.source_url,
            revision_id     = page.revision_id,
            warnings        = warnings,
        )

    def _parse_char_info(self, soup: BeautifulSoup) -> dict:
        """
        传入经过 BeautifulSoup 加工后的实例
        遍历 <script> 标签，提取 char_info 变量
        """
        for script in soup.find_all("script"):
            source = script.string or script.get_text()
            if "var char_info" not in source:
                continue
            match = self._CHAR_INFO_PATTERN.search(source)
            if match:
                raw = match.group(1)
            else:
                # 审查问题是主正则依赖 char_info 后方固定的注释或 voice_keys 标记
                # PRTS 调整换行或脚本变量顺序后主正则可能失效，因此回退到花括号配对提取
                # 配对过程只依赖赋值起点和完整对象边界，比继续放宽跨行正则更容易审核和维护
                raw = self._extract_char_info_object(source)
                if raw is None:
                    continue
            """
            清理 json 文件
            形如
            {
                "name": "谬因",
                "rarity": 5,
            }
            的文件是不受 python 支持的，python 标准要求字典最后一项不可以带多余逗号
            需要额外进行解析，不然直接报 JSONDecodeError
            """
            raw = self._normalize_char_info_json(raw)
            # 解析 json 数据，若解析出错，则跳过该 <script> 标签。理论上不会发生，但安全处理总没有错
            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                continue
            # 如果解析出的数据是字典，则直接返回
            if isinstance(result, dict):
                return result
        raise OperatorParseError("该页面不是可识别的 PRTS 干员页面（缺少 char_info）")

    @staticmethod
    def _normalize_char_info_json(raw: str) -> str:
        """将 PRTS 的 JavaScript 对象文本规范化为严格 JSON。"""
        # 维什戴尔和凯尔希·思衡托等页面的英文名包含 JavaScript 合法的单引号转义 \'
        # JSON 字符串不接受该转义并会抛出 Invalid \escape，因此页面会被误判为无法识别
        # 单引号在双引号 JSON 字符串中无需转义，这里只移除它前方的单个反斜杠以保留原文本
        normalized = raw.replace("\\'", "'")

        # PRTS 的 char_info 对象允许数组或对象末项保留逗号，但严格 JSON 不允许尾随逗号
        # 在单引号转义处理完成后继续沿用原有清理规则，保证普通干员页面行为不变
        return re.sub(r",\s*([}\]])", r"\1", normalized)

    def _extract_char_info_object(self, source: str) -> str | None:
        """从脚本文本中按花括号层级提取 char_info 对象。"""
        assignment = self._CHAR_INFO_ASSIGNMENT_PATTERN.search(source)
        if assignment is None:
            return None

        object_start = source.find("{", assignment.end())
        if object_start < 0:
            return None

        depth = 0
        in_string = False
        escaped = False
        for index in range(object_start, len(source)):
            character = source[index]
            if in_string:
                if escaped:
                    escaped = False
                    continue
                if character == "\\":
                    escaped = True
                    continue
                if character == '"':
                    in_string = False
                continue

            if character == '"':
                in_string = True
                continue
            if character == "{":
                depth += 1
                continue
            if character != "}":
                continue

            depth -= 1
            if depth == 0:
                return source[object_start:index + 1]
        return None

    def _parse_attributes(self, soup: BeautifulSoup) -> list[OperatorAttribute]:
        """从基础属性表中解析各精英阶段的数值。"""
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
        """解析干员技能区块中的全部技能。"""
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
        """从单个技能标题和表格中提取技能详情。"""
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
        """解析干员模组及各阶段的属性和效果。"""
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
        """移除隐藏节点并规范化 HTML 节点中的文本空白。"""
        if tag is None:
            return ""
        fragment = BeautifulSoup(str(tag), "html.parser")
        # T2I 模组名旁出现的“[编辑]”来自 MediaWiki 自动插入的 mw-editsection 节点
        # 在通用文本清洗阶段移除该节点，可以同时覆盖模组标题和其他章节标题且不改动正文
        removable_selector = (
            '[style*="display:none"], '
            ".mw-editsection, "
            "script, "
            "style"
        )
        for hidden in fragment.select(removable_selector):
            hidden.decompose()
        return " ".join(fragment.get_text(" ", strip=True).split())

    @staticmethod
    def _optional_text(value: object) -> str | None:
        """将可选值转换为去除首尾空白的非空字符串。"""
        text = str(value).strip() if value is not None else ""
        return text or None

    @staticmethod
    def _absolute_url(url: str | None) -> str | None:
        """将 PRTS 页面中的相对或协议相对地址转换为绝对 URL。"""
        if not url:
            return None
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return "https://prts.wiki" + url
        return url
