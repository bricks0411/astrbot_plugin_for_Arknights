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
    ) -> str: ...


OPERATOR_INFO_RENDER_OPTIONS = {
    "type": "png",
    "full_page": True,
    "animations": "disabled",
    "caret": "hide",
}


def build_operator_render_data(operator: OperatorData, *, include_portrait: bool = True) -> dict:
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
    """压缩本地图片，避免远程 T2I 的 JSON 请求体过大。"""
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
    """调用 AstrBot Star.html_render() 渲染干员百科卡片。"""
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


OPERATOR_INFO_TEMPLATE = r"""
<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>
*{box-sizing:border-box}html,body{margin:0;padding:0}body{width:1280px;padding:44px;color:#18202b;font-family:"Microsoft YaHei","Noto Sans SC",sans-serif;background:#fff}.card{position:relative;overflow:hidden;border:1px solid #dfe4ea;border-radius:26px;background:#fff;box-shadow:0 20px 60px rgba(25,38,55,.14)}.hero{min-height:610px;background:transparent}.portrait{position:absolute;z-index:0;inset:0;overflow:hidden;pointer-events:none;background:#fff}.portrait:after{content:"";position:absolute;inset:0;background:linear-gradient(90deg,rgba(255,255,255,.94) 0%,rgba(255,255,255,.8) 29%,rgba(255,255,255,.32) 61%,rgba(255,255,255,.18) 100%),linear-gradient(180deg,rgba(255,255,255,.12) 0%,rgba(255,255,255,.2) 32%,rgba(255,255,255,.35) 68%,rgba(255,255,255,.5) 100%)}.portrait img{width:100%;height:100%;min-height:610px;object-fit:cover;object-position:center top;opacity:.58}.portrait-empty{height:610px;display:grid;place-items:center;color:#99a3af;font-size:24px}.identity{position:relative;z-index:2;width:53%;min-height:610px;padding:78px 56px;display:flex;flex-direction:column;justify-content:center}.eyebrow{color:#1478c9;font-size:17px;font-weight:800;letter-spacing:5px}.name{margin:13px 0 7px;color:#111820;font-size:66px;line-height:1.08;font-weight:950}.stars{color:#e9a900;font-size:31px;letter-spacing:4px}.role{margin-top:24px;color:#4f5f70;font-size:23px}.section{position:relative;z-index:2;margin:0 22px 18px;padding:34px 40px;border:1px solid rgba(207,215,224,.9);border-radius:20px;background:rgba(255,255,255,.78);box-shadow:0 8px 24px rgba(34,47,62,.08);backdrop-filter:blur(5px)}.section-title{margin-bottom:22px;color:#17212d;font-size:30px;font-weight:900}.attr-table{width:100%;border-collapse:separate;border-spacing:0 8px;font-size:18px}.attr-table th{padding:12px 14px;color:#6d7b8a;text-align:center;font-size:15px}.attr-table th:first-child{text-align:left}.attr-table td{padding:14px;text-align:center;background:rgba(242,245,248,.9)}.attr-table td:first-child{text-align:left;color:#243549;font-weight:800;border-radius:10px 0 0 10px}.attr-table td:last-child{border-radius:0 10px 10px 0}.skill-list,.module-list{display:grid;gap:16px}.skill,.module{padding:22px;border:1px solid rgba(215,223,231,.94);border-radius:17px;background:rgba(255,255,255,.84);box-shadow:0 5px 15px rgba(38,52,69,.05)}.skill-head{display:flex;align-items:center;gap:15px}.skill-icon{width:58px;height:58px;border-radius:10px}.skill-name,.module-name{color:#17212d;font-size:25px;font-weight:900}.badges{margin-top:6px;display:flex;gap:7px;flex-wrap:wrap}.badge{padding:4px 9px;border-radius:999px;color:#1766a7;background:rgba(229,242,252,.94);font-size:14px}.description{margin-top:14px;color:#303b48;font-size:18px;line-height:1.75}.skill-cost{margin-top:13px;color:#697888;font-size:15px}.module-type{margin-left:9px;color:#1478c9;font-size:16px}.module-level{margin-top:13px;padding:13px 15px;border-left:3px solid #d8a100;background:rgba(255,255,255,.8);font-size:17px;line-height:1.65}.module-level b{color:#9b7200}.empty{padding:25px;color:#7d8996;text-align:center;border:1px dashed #cfd6dd;border-radius:13px;background:rgba(250,251,252,.86)}.source{position:relative;z-index:2;padding:20px 40px;color:#667585;text-align:center;font-size:13px;background:rgba(255,255,255,.72)}
/* 横版布局：立绘位于白色底层之上，数据面板位于立绘之上。 */
body{width:1800px;padding:32px}.card{display:grid;grid-template-columns:46% 54%;grid-template-rows:auto auto auto auto;align-items:stretch;min-height:1080px}.portrait:after{background:linear-gradient(90deg,rgba(255,255,255,.02) 0%,rgba(255,255,255,.06) 36%,rgba(255,255,255,.58) 49%,rgba(255,255,255,.9) 64%,rgba(255,255,255,.97) 100%)}.portrait img{opacity:.9;object-position:36% center}.hero{grid-column:1;grid-row:1 / 5;position:relative;z-index:2;min-height:1080px;display:flex;align-items:flex-end;padding:36px}.identity{width:auto;min-height:0;padding:28px 32px;border:1px solid rgba(255,255,255,.82);border-radius:20px;background:rgba(255,255,255,.86);box-shadow:0 12px 32px rgba(20,32,45,.16);backdrop-filter:blur(3px)}.eyebrow{font-size:15px}.name{font-size:58px}.stars{font-size:27px}.role{margin-top:16px;font-size:20px}.section{grid-column:2;margin:16px 18px 0 8px;padding:23px 27px;border-radius:17px;background:rgba(255,255,255,.9);backdrop-filter:blur(2px)}.section-title{margin-bottom:14px;font-size:25px}.attr-table{border-spacing:0 5px;font-size:15px}.attr-table th{padding:8px 9px;font-size:12px}.attr-table td{padding:9px}.skill-list,.module-list{gap:9px}.skill,.module{padding:14px 16px;border-radius:13px;background:rgba(255,255,255,.91)}.skill-head{gap:10px}.skill-icon{width:46px;height:46px}.skill-name,.module-name{font-size:20px}.badges{margin-top:3px;gap:5px}.badge{padding:3px 7px;font-size:12px}.description{margin-top:8px;font-size:15px;line-height:1.48}.skill-cost{margin-top:7px;font-size:12px}.module-type{font-size:13px}.module-level{margin-top:7px;padding:8px 10px;font-size:14px;line-height:1.45}.source{grid-column:2;position:relative;z-index:2;margin-top:16px;padding:13px 25px;background:rgba(255,255,255,.9);font-size:11px}
.operator-avatar{width:112px;height:112px;margin-bottom:15px;object-fit:cover;border:4px solid rgba(255,255,255,.96);border-radius:20px;background:#eef2f5;box-shadow:0 8px 24px rgba(20,32,45,.2)}
body{background:linear-gradient(180deg,#fff 0%,#f7f8fa 48%,#e3e6ea 100%)}.card{background:linear-gradient(180deg,#fff 0%,#f5f6f8 52%,#dfe3e7 100%)}.portrait{background:transparent}.identity,.section{backdrop-filter:none}.identity{background:rgba(255,255,255,.9)}.section{background:rgba(255,255,255,.92)}
/* 缩小信息卡片的白色遮罩感，让立绘清晰透过数据层。 */
.portrait:after{background:linear-gradient(90deg,rgba(255,255,255,.01) 0%,rgba(255,255,255,.03) 36%,rgba(255,255,255,.24) 50%,rgba(255,255,255,.48) 68%,rgba(255,255,255,.62) 100%)}.section{border-color:rgba(207,215,224,.68);background:rgba(255,255,255,.56);box-shadow:0 5px 15px rgba(34,47,62,.05)}.skill,.module{border-color:rgba(215,223,231,.72);background:rgba(255,255,255,.76);box-shadow:0 3px 9px rgba(38,52,69,.04)}.attr-table td{background:rgba(242,245,248,.76)}.module-level{background:rgba(255,255,255,.7)}.source{background:rgba(255,255,255,.62)}
</style></head><body><article class="card"><section class="hero"><div class="portrait">{% if portrait_src %}<img src="{{ portrait_src }}" alt="{{ name }}立绘">{% else %}<div class="portrait-empty">暂无立绘</div>{% endif %}</div><div class="identity">{% if avatar_src %}<img class="operator-avatar" src="{{ avatar_src }}" alt="{{ name }}头像">{% endif %}<div class="eyebrow">PRTS · OPERATOR FILE</div><div class="name">{{ name }}</div><div class="stars">{{ rarity_text }}</div><div class="role">{% if profession %}{{ profession }}{% endif %}{% if branch %} · {{ branch }}{% endif %}</div></div></section>
<section class="section"><div class="section-title">基础数值</div>{% if attributes %}<table class="attr-table"><thead><tr><th>属性</th><th>精英 0 · 1级</th><th>精英 0 · 满级</th><th>精英 1 · 满级</th><th>精英 2 · 满级</th><th>信赖加成</th></tr></thead><tbody>{% for item in attributes %}<tr><td>{{ item.name }}</td><td>{{ item.elite0_level1 }}</td><td>{{ item.elite0_max }}</td><td>{{ item.elite1_max }}</td><td>{{ item.elite2_max }}</td><td>{{ item.trust_bonus }}</td></tr>{% endfor %}</tbody></table>{% else %}<div class="empty">暂无基础数值</div>{% endif %}</section>
<section class="section"><div class="section-title">技能介绍 · 专精三</div>{% if skills %}<div class="skill-list">{% for skill in skills %}<div class="skill"><div class="skill-head">{% if skill.icon_url %}<img class="skill-icon" src="{{ skill.icon_url }}">{% endif %}<div><div class="skill-name">{{ skill.name }}</div><div class="badges">{% if skill.unlock %}<span class="badge">{{ skill.unlock }}开放</span>{% endif %}{% if skill.recovery_type %}<span class="badge">{{ skill.recovery_type }}</span>{% endif %}{% if skill.trigger_type %}<span class="badge">{{ skill.trigger_type }}</span>{% endif %}</div></div></div><div class="description">{{ skill.description }}</div><div class="skill-cost">初始技力 {{ skill.initial_sp or '—' }} · 消耗 {{ skill.sp_cost or '—' }} · 持续 {{ skill.duration or '—' }}</div></div>{% endfor %}</div>{% else %}<div class="empty">暂无技能信息</div>{% endif %}</section>
<section class="section"><div class="section-title">模组介绍</div>{% if modules %}<div class="module-list">{% for module in modules %}<div class="module"><div><span class="module-name">{{ module.name }}</span>{% if module.type_code %}<span class="module-type">{{ module.type_code }}</span>{% endif %}</div>{% for level in module.levels %}<div class="module-level"><b>Stage {{ level.level }}</b>{% if level.attributes %} · {{ level.attributes }}{% endif %}{% if level.effect %}<br>{{ level.effect }}{% endif %}</div>{% endfor %}</div>{% endfor %}</div>{% else %}<div class="empty">该干员暂无专属模组</div>{% endif %}</section>
<footer class="source">数据来源：PRTS Wiki · {{ source_url }}</footer></article></body></html>
"""
