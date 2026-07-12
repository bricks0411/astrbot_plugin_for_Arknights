# AstrBot 明日方舟综合查询插件

面向 AstrBot 的明日方舟官服账号登录与寻访记录统计插件。插件通过鹰角官方接口获取最近可查询的寻访记录，持久化到 SQLite，并生成包含干员头像、六星抽数、卡池汇总和概率提示的统计图片。

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

目前仅支持明日方舟官服，B 服登录命令为预留功能。

## 安装

将仓库安装到 AstrBot 的 `data/plugins` 目录，或通过 AstrBot 插件管理界面安装。部署环境会根据 `requirements.txt` 安装：

```text
cryptography>=42.0.0
requests>=2.31.0
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
/验证码 <验证码>
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

查询时会验证数据库中的登录凭证、同步服务器最新记录、读取本地完整历史并生成统计图片。凭证失效时会提示重新登录。

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
└── analysis/
    ├── SixStarsAnalyser.py         # 统一统计数据模型与分析逻辑
    └── GachaHistoryT2I.py          # HTML/Jinja2 模板与截图配置
```

## 数据与缓存

运行数据位于 AstrBot 数据目录：

```text
plugin_data/astrbot_plugin_for_Arknights/
├── user_db.sqlite3
├── token.key
└── avatar_cache/
```

- `user_db.sqlite3` 保存账号绑定和寻访记录。
- token 使用 Fernet 加密后写入数据库。
- `token.key` 是解密凭证所必需的本地密钥，请与数据库一起备份并限制访问权限。
- 头像缓存不设置过期时间；删除 `avatar_cache` 后会按需重新下载。

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

## 已知限制

- 官方接口只提供有限时间范围内的寻访记录，插件无法补回绑定前且服务器已不再提供的数据。
- 首次生成统计图时需要下载尚未缓存的六星干员头像。
- 超长统计图片可能被消息平台压缩。
- 当前未提供解绑、清空记录和头像缓存清理命令。
- B 服尚未实现。

## 隐私提示

本插件会在 AstrBot 主机本地保存账号 UID、昵称、加密 token 和寻访记录。部署者应保护 AstrBot 数据目录，并在提供公共机器人服务时向用户说明数据保存行为。

## License

[GNU General Public License v3.0](LICENSE)
