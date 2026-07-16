# AstrBot 明日方舟综合查询插件

面向 AstrBot 的明日方舟综合查询插件。插件通过鹰角官方接口获取最近可查询的寻访记录，持久化到 SQLite，并生成寻访统计图片；同时通过 PRTS Wiki 的 MediaWiki API 查询干员姓名、星级、数值、技能、模组、头像与立绘，生成横版干员百科卡片。

> 受服务器接口限制，只能获取用户绑定之日起前推约 90 天之后的数据。数据库会保留已经同步过的历史记录。

## 功能

- 官服手机号验证码登录。
- 登录凭证持久化，插件重启后无需重新绑定。
- 分页拉取服务器当前可查询的全部寻访记录，单页大小为 50。
- SQLite 批量事务写入，通过唯一约束自动忽略重复记录。
- 按标准寻访、中坚寻访、限定寻访统计总抽数、当前垫抽数和下一抽六星概率。
- 按实际 `poolName` 展示各卡池总抽数及六星记录。
- 六星记录显示干员头像、名称、NEW 标识、出货抽数及欧非标签。
- HTML/Jinja2 图片渲染，失败时自动回退为文本。
- 干员头像永久缓存在插件数据目录，后续渲染不重复请求头像服务器。
- 通过 PRTS Wiki 查询干员基础数值、技能专精三说明和三级模组效果。
- 自动获取干员头像与精英二立绘，并分别缓存到本地。
- 横版干员百科渲染：左侧展示立绘与身份信息，右侧展示数值、技能和模组。
- 干员百科采用“上白下灰”底色、立绘背景层和半透明信息卡片。
- PRTS 结构化数据默认缓存 24 小时，同名并发查询自动合并。
- 高清立绘在送入远程 T2I 前自动缩放并压缩为 WebP；带立绘渲染失败时自动使用无立绘版本重试。

目前仅支持明日方舟官服，B 服登录命令为预留功能。

## 安装

将仓库安装到 AstrBot 的 `data/plugins` 目录，或通过 AstrBot 插件管理界面安装。部署环境会根据 `requirements.txt` 安装：

```text
cryptography>=42.0.0
requests>=2.31.0
beautifulsoup4>=4.12.0
Pillow>=10.0.0
```

插件要求 AstrBot 提供自定义 HTML 文转图能力。图片渲染使用 `Star.html_render()`；请确保 AstrBot 的 t2i 服务可用。

## 使用

所有命令均以 AstrBot 的命令前缀调用，默认示例使用 `/`。

### 1. 获取验证码

仅支持私聊：

```text
/方舟官服登录 <手机号>
```

### 2. 提交验证码

仅支持私聊：

```text
/官服验证码 <验证码>
```

登录成功后，插件会自动保存游戏 UID、昵称和加密后的账号 token。

### 3. 更新寻访记录

```text
/官服抽卡记录更新
```

从服务器分页获取当前可查询的全部记录并写入数据库。

### 4. 查询寻访统计

```text
/官服抽卡记录查询
```

查询命令只读取本地数据库并生成统计图片，不会请求服务器。需要同步最新数据时，请先执行“官服抽卡记录更新”。

### 5. 查询干员百科

```text
/干员百科 <干员名称>
```

插件会从 PRTS Wiki 查询干员资料并生成横版百科图片。第一次查询需要访问 PRTS 并下载头像、立绘，之后在缓存有效期内直接使用本地数据。

当前百科图片包含：

- 干员姓名、星级、职业和分支。
- 干员头像与默认优先精英二立绘。
- 精英 0 至精英 2 的基础生命、攻击、防御、法术抗性和信赖加成。
- 技能最高等级或专精三的描述、技力和触发类型。
- 专属模组 Stage 1～3 的属性与效果。

数据来自 [PRTS Wiki](https://prts.wiki/)，页面结构或站点服务发生变化时，部分字段可能暂时无法解析。

## 统计口径

- API 中 `rarity == 5` 表示六星干员。
- `category == normal` 计入标准寻访。
- `category == classic` 计入中坚寻访。
- 其余 category 计入限定寻访。
- 同一 `poolName` 视为同一个展示卡池。
- 六星抽数从该卡池首抽开始累计，出现六星后归零重新计算。
- 当前垫抽数为对应寻访类别中最后一个六星之后的抽数；无六星时等于该类别总抽数。
- 下一抽六星概率使用：`max(2, 2 * (x - 50))%`，其中 `x` 为当前垫抽数。
- 少于 10 抽获得六星标记为“超欧”，超过 60 抽标记为“超非”。

## 项目结构

```text
.
├── main.py                         # AstrBot 插件入口与命令编排
├── metadata.yaml                   # 插件元数据
├── requirements.txt                # Python 依赖
├── LoginTools/
│   ├── OfficialServerLogin.py      # 验证码与账号凭证请求
│   └── models.py
├── GetDoctorInfo/
│   ├── OfficialDoctorInfoHandler.py# 官服角色绑定信息请求
│   └── models.py
├── GachaHistory/
│   ├── GetGachaHistory.py          # 卡池与寻访记录分页请求
│   └── models.py
├── storage/
│   ├── UserDB.py                   # SQLite、token 与寻访记录持久化
│   └── models.py
├── analysis/
│   ├── SixStarsAnalyser.py         # 统一统计数据模型与分析逻辑
│   └── GachaHistoryT2I.py          # HTML/Jinja2 模板与截图配置
└── OperatorInfo/
    ├── client.py                   # PRTS MediaWiki API 与图片请求
    ├── parser.py                   # 干员页面、数值、技能和模组解析
    ├── models.py                   # 干员百科结构化数据模型
    ├── service.py                  # 缓存、并发控制与查询编排
    ├── renderer.py                 # 横版百科模板与 html_render 封装
    └── README.md                   # 模块接口及 main.py 接入文档
```

## 数据与缓存

运行数据位于 AstrBot 数据目录：

```text
plugin_data/astrbot_plugin_for_Arknights/
├── user_db.sqlite3
├── token.key
├── avatar_cache/
└── operator_info_cache/
    ├── operators/
    ├── portraits/
    └── avatars/
```

- `user_db.sqlite3` 保存账号绑定和寻访记录。
- token 使用 Fernet 加密后写入数据库。
- `token.key` 是解密凭证所必需的本地密钥，请与数据库一起备份并限制访问权限。
- 抽卡统计头像缓存不设置过期时间；删除 `avatar_cache` 后会按需重新下载。
- `operator_info_cache/operators` 保存 PRTS 结构化数据，默认有效期为 24 小时。
- `operator_info_cache/portraits` 和 `operator_info_cache/avatars` 分别保存百科立绘与头像。
- 百科缓存格式升级时旧结构化缓存会自动失效，无需手动清理。

## 安全说明

- 登录与验证码命令仅允许私聊调用。
- 日志不会记录完整手机号、验证码或 token。
- 手机号仅在验证码登录会话期间保存在内存，不写入数据库。
- token 使用本地 Fernet 密钥加密存储。
- 密钥与数据库位于同一插件数据目录，因此主机目录访问权限仍是安全边界；请勿公开该目录。
- 若 `token.key` 丢失或损坏，已保存 token 无法恢复，用户需要重新登录。

## 性能与并发

- 同步 HTTP 与 SQLite 操作通过 `asyncio.to_thread()` 避免阻塞事件循环。
- SQLite 使用 WAL、busy timeout、进程内重入锁和批量事务。
- 头像首次下载最多使用 6 个工作线程，之后直接读取永久缓存。
- t2i 使用完整页面截图，图片高度随卡池和六星数量动态增长。
- PRTS 同步请求通过 `asyncio.to_thread()` 运行，不直接阻塞 AstrBot 事件循环。
- 同一干员的并发百科请求使用进程内异步锁合并。
- 百科立绘会压缩为 WebP，减少公共 T2I 服务的请求体积。

## 已知限制

- 官方接口只提供有限时间范围内的寻访记录，插件无法补回绑定前且服务器已不再提供的数据。
- 首次生成统计图时需要下载尚未缓存的六星干员头像。
- 超长统计图片可能被消息平台压缩。
- 当前未提供解绑、清空记录和头像缓存清理命令。
- 干员百科依赖 PRTS 当前页面结构；页面模板调整后可能需要更新解析器。
- 公共 T2I 服务可能限制请求体大小或暂时不可用；百科渲染会尝试去掉立绘重试。
- 技能目前只展示专精三；没有专精等级时展示页面中可识别的最高等级。
- 模组不展示解锁材料、任务和剧情文本。
- B 服尚未实现。

## 隐私提示

本插件会在 AstrBot 主机本地保存账号 UID、昵称、加密 token 和寻访记录。部署者应保护 AstrBot 数据目录，并在提供公共机器人服务时向用户说明数据保存行为。

## License

[GNU Affero General Public License v3.0](LICENSE)
