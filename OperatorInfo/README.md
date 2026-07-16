# OperatorInfo 模块接口文档

`OperatorInfo` 是独立于 `main.py` 的 PRTS 干员百科模块。目前提供：

- 干员正式名称与星级。
- 职业和分支。
- 默认优先精英二立绘，并缓存到本地。
- 独立获取干员头像，并在横版身份面板中展示。
- 精英 0/1/2 四阶段基础数值和信赖加成。
- 技能专精三介绍、技力与触发类型。
- 专属模组 Stage 1～3 的属性和效果介绍。
- 可直接交给 AstrBot `html_render()` 的百科模板。

## 1. 初始化

建议在插件类的 `__init__()` 中初始化一次：

```python
from pathlib import Path

from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .OperatorInfo import OperatorEncyclopedia, PrtsWikiClient


operator_cache_dir = (
    Path(get_astrbot_data_path())
    / "plugin_data"
    / PLUGIN_NAME
    / "operator_info_cache"
)

self.operator_encyclopedia = OperatorEncyclopedia(
    PrtsWikiClient(self.http_client),
    operator_cache_dir,
    cache_ttl_seconds=24 * 60 * 60,
    download_portrait=True,
)
```

模块通过构造函数注入项目现有的 `network.HttpClient`，不在内部维护第二套 HTTP 配置。

## 2. 异步查询接口

```python
operator = await self.operator_encyclopedia.get_operator(
    "能天使",
    force_refresh=False,
)
```

### 参数

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | PRTS 页面名或能被 PRTS 重定向解析的名称 |
| `force_refresh` | `bool` | `False` | 忽略有效缓存并重新请求 |

异步接口使用 `asyncio.to_thread()` 隔离现有同步 HTTP 请求，避免直接阻塞 AstrBot 的事件循环。相同名称的并发查询会由进程内锁合并。

另有同步接口 `get_operator_sync()`，主要供脚本和测试使用，不应直接放在 AstrBot 异步指令处理器中。

## 3. 返回模型

返回值为 `OperatorData`：

```python
operator.name              # 正式名称
operator.rarity            # 1～6；无法解析时为 None
operator.profession        # 例如“狙击”
operator.branch            # 例如“速射手”
operator.avatar_url        # PRTS 远程头像地址
operator.avatar_path       # 本地缓存头像的绝对路径
operator.portrait_url      # PRTS 远程立绘地址
operator.portrait_path     # 本地缓存立绘的绝对路径
operator.attributes        # list[OperatorAttribute]
operator.skills            # list[OperatorSkill]
operator.modules           # list[OperatorModule]
operator.source_url        # PRTS 来源页面
operator.revision_id       # MediaWiki 页面版本 ID
operator.warnings          # 非致命的缺失或降级信息
```

`warnings` 不代表查询失败。例如立绘下载失败时，基础数值和技能仍然可以正常返回。

## 4. 渲染接口

### 4.1 直接调用 `html_render()`

模块提供 `render_operator_card()`，内部会实际调用传入对象的 `html_render()`：

```python
from .OperatorInfo import render_operator_card

image_url = await render_operator_card(self, operator)
```

这里的 `self` 是当前插件的 `Star` 实例。函数内部实际执行：

```python
return await renderer.html_render(
    OPERATOR_INFO_TEMPLATE,
    build_operator_render_data(operator),
    return_url=return_url,
    options=render_options,
)
```

完整签名：

```python
await render_operator_card(
    renderer,                  # 具有 async html_render(...) 的对象
    operator,                  # OperatorData
    return_url=True,           # True 返回 URL，False 返回本地路径
    options=None,              # 覆盖或追加默认渲染参数
)
```

### 4.2 查询并直接渲染

最简入口是 `OperatorEncyclopedia.query_and_render()`：

```python
image_url = await self.operator_encyclopedia.query_and_render(
    self,
    "能天使",
)
```

该方法依次执行缓存查询、PRTS 请求、解析、立绘缓存、构造模板数据和 `self.html_render()`。

完整签名：

```python
await encyclopedia.query_and_render(
    renderer,
    name,
    force_refresh=False,
    return_url=True,
    render_options=None,
)
```

### 4.3 手动控制模板和数据

如果需要在 `main.py` 中修改模板或插入额外字段，也可以使用底层接口：

```python
from .OperatorInfo import (
    OPERATOR_INFO_RENDER_OPTIONS,
    OPERATOR_INFO_TEMPLATE,
    build_operator_render_data,
)

image_url = await self.html_render(
    OPERATOR_INFO_TEMPLATE,
    build_operator_render_data(operator),
    options=OPERATOR_INFO_RENDER_OPTIONS,
)
```

`build_operator_render_data()` 会优先把本地立绘缩放到最大 1000×1000，并压缩为 WebP `data:` URL，避免高清 PNG 令远程 T2I 请求体过大，也避免 HTML 渲染进程无法读取本地文件；本地立绘不存在时才使用远程 URL。原始缓存图片不会被修改。如果公共 T2I 服务仍然拒绝带图请求，`render_operator_card()` 会自动去掉立绘重试，确保基础数值、技能和模组仍可生成图片。

默认模板为 1800px 横版双栏布局：左侧显示立绘背景、头像和身份信息，右侧显示基础数值、技能与模组。白色为最底层，立绘为中间背景层，半透明数据面板为最上层。

## 5. `main.py` 指令接入示例

推荐接入方式如下，本模块没有主动修改 `main.py`：

```python
from .OperatorInfo import OperatorInfoError, OperatorNotFoundError


@filter.command("干员")
async def query_operator(self, event: AstrMessageEvent, name: str):
    try:
        image_url = await self.operator_encyclopedia.query_and_render(
            self,
            name,
        )
        yield event.image_result(image_url)
    except OperatorNotFoundError:
        yield event.plain_result(f"PRTS 中没有找到干员：{name}")
    except OperatorInfoError as exc:
        logger.exception("干员百科查询失败")
        yield event.plain_result(f"干员百科查询失败：{exc}")
```

请根据当前 AstrBot 版本实际支持的图片消息构造方法调整最后一行；`html_render()` 默认返回 URL。

## 6. 异常接口

模块公开以下异常：

| 异常 | 含义 |
| --- | --- |
| `OperatorInfoError` | 模块异常基类 |
| `OperatorNotFoundError` | 页面不存在或标题无效 |
| `OperatorResponseError` | PRTS/MediaWiki 响应结构异常 |
| `OperatorParseError` | 页面存在，但不是可识别的干员页面 |
| `OperatorValidationError` | 输入为空或超过 64 字符 |

建议将“未找到”单独提示用户，其余异常记录日志并返回统一的稍后重试提示。

## 7. 缓存行为

缓存目录结构：

```text
operator_info_cache/
├── operators/     # 结构化 JSON，默认有效 24 小时
├── portraits/     # 立绘文件，不按 TTL 主动删除
└── avatars/       # 干员头像文件，不按 TTL 主动删除
```

结构化缓存包含 `cache_version`。数据格式发生不兼容变化时，提升 `OperatorEncyclopedia.CACHE_VERSION` 即可令旧缓存失效。

## 8. 当前实现边界

- 数据解析依赖 PRTS 当前的 `char_info`、`char-base-attr-table`、技能表和 `equiptemplate` 页面结构。
- 技能只展示专精三；没有专精等级时降级为页面中最高等级。
- 数值不叠加潜能、信赖或模组，信赖加成单独展示。
- 立绘优先查询 `立绘_<干员名>_2.png`，不存在时查询精英 0/1 立绘及页面图片候选。
- 模组只展示三级属性与战斗效果，不展示解锁材料、任务和模组故事。
- PRTS 页面结构改变后，通常只需修改 `parser.py`；调用方接口不应随之变化。
