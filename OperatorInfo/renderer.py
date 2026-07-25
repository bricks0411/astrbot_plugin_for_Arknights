# OperatorInfo/renderer.py
from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

from PIL import Image

from .models import OperatorData


class HtmlRenderer(Protocol):
    async def html_render(
        self,
        tmpl: str,
        data: dict,
        return_url: bool = True,
        options: dict | None = None,
    ) -> str:
        """使用 HTML 模板和数据生成图片或图片地址"""
        ...


OPERATOR_INFO_RENDER_OPTIONS = {
    "type": "png",
    "full_page": True,
    "animations": "disabled",
    "caret": "hide",
}

OPERATOR_INFO_TEMPLATE = (
    Path(__file__).with_name("templates") / "operator_info.html"
).read_text(encoding="utf-8")


def build_operator_render_data(operator: OperatorData, *, include_portrait: bool = True) -> dict:
    """字典化待渲染干员数据，方便 html 脚本编制"""
    portrait = operator.portrait_url if include_portrait else None
    if include_portrait and operator.portrait_path:
        path = Path(operator.portrait_path)
        try:
            portrait = _build_image_data_uri(path, 1000, 74)
        except (OSError, ValueError):
            pass
    avatar = operator.avatar_url
    if operator.avatar_path:
        try:
            avatar = _build_image_data_uri(Path(operator.avatar_path), 260, 82)
        except (OSError, ValueError):
            pass
    result = operator.to_dict()
    result["portrait_src"] = portrait
    result["avatar_src"] = avatar
    result["rarity_text"] = "★" * operator.rarity if operator.rarity else "星级未知"
    return result


def _build_image_data_uri(path: Path, max_side: int, quality: int) -> str:
    """压缩本地图片，避免远程 T2I 的 JSON 请求体过大"""
    with Image.open(path) as source:
        image = source.copy()
    image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)

    output = BytesIO()
    image.save(output, format="WEBP", quality=quality, method=6)
    content = output.getvalue()
    if len(content) > 1024 * 1024:
        image.thumbnail((1100, 1100), Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, format="WEBP", quality=72, method=6)
        content = output.getvalue()

    encoded = base64.b64encode(content).decode("ascii")
    return f"data:image/webp;base64,{encoded}"


async def render_operator_card(
    renderer: HtmlRenderer,
    operator: OperatorData,
    *,
    return_url: bool = True,
    options: dict[str, Any] | None = None,
) -> str:
    """调用 AstrBot Star.html_render() 渲染干员百科卡片"""
    render_options = dict(OPERATOR_INFO_RENDER_OPTIONS)
    if options:
        render_options.update(options)
    try:
        return await renderer.html_render(
            OPERATOR_INFO_TEMPLATE,
            build_operator_render_data(operator),
            return_url=return_url,
            options=render_options,
        )
    except Exception:
        # 部分公共 T2I 服务对 Base64 图片或请求体大小限制较严。
        # 首次渲染失败时去掉立绘重试，至少保留百科文字内容。
        return await renderer.html_render(
            OPERATOR_INFO_TEMPLATE,
            build_operator_render_data(operator, include_portrait=False),
            return_url=return_url,
            options=render_options,
        )
