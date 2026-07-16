# analysis/SixStarsAnalyser.py
import asyncio
import base64
import hashlib
import requests
import re

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from threading import RLock
from urllib.parse import quote


@dataclass(slots=True, frozen=True)
class SixStarRecord:
    operator_name: str
    pulls: int
    gacha_ts: int
    is_new: bool
    avatar_url: str
    luck_label: str | None
    bar_width: float
    bar_color: str


@dataclass(slots=True, frozen=True)
class PoolStatistics:
    pool_name: str
    total_pulls: int
    latest_gacha_ts: int
    six_stars: tuple[SixStarRecord, ...]


@dataclass(slots=True, frozen=True)
class CategoryStatistics:
    category_name: str
    total_pulls: int
    pulls_since_last_six_star: int
    next_six_star_rate: float


@dataclass(slots=True, frozen=True)
class GachaStatistics:
    doctor_name: str
    doctor_suffix: str | None
    total_pulls: int
    total_six_stars: int
    six_star_rate: float
    average_pulls_per_six_star: float | None
    categories: tuple[CategoryStatistics, ...]
    pools: tuple[PoolStatistics, ...]


class GachaHistoryAnalyser:
    AVATAR_REQUEST_TIMEOUT = 10
    MAX_AVATAR_SIZE = 5 * 1024 * 1024
    PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

    def __init__(self, avatar_cache_dir: str | Path):
        """初始化抽卡统计分析器并创建干员头像缓存目录。"""
        self.avatar_cache_dir = Path(avatar_cache_dir)
        self.avatar_cache_dir.mkdir(parents=True, exist_ok=True)
        self._avatar_cache_lock = RLock()

    @staticmethod
    def build_operator_avatar_url(name: str) -> str:
        """根据干员名称构造 PRTS Wiki 头像文件的直链。"""
        filename = f"头像_{name}.png"
        digest = hashlib.md5(filename.encode("utf-8")).hexdigest()
        return f"https://media.prts.wiki/{digest[0]}/{digest[:2]}/{quote(filename)}"

    @staticmethod
    def _bar_style(pulls: int) -> tuple[float, str]:
        """根据出六星所用抽数计算进度条宽度和颜色。"""
        width = min(100.0, max(4.0, pulls / 70 * 100))
        if pulls < 10:
            color = "linear-gradient(90deg, #58e0b5, #9af1d5)"
        elif pulls <= 35:
            color = "linear-gradient(90deg, #53a9ff, #79c8ff)"
        elif pulls <= 60:
            color = "linear-gradient(90deg, #f0ae49, #ffd072)"
        else:
            color = "linear-gradient(90deg, #e14e58, #ff7b67)"
        return width, color

    @staticmethod
    def _split_doctor_name(doctor_name: str | None) -> tuple[str, str | None]:
        """将博士名称拆分为昵称和可选的数字后缀。"""
        value = (doctor_name or "博士").strip()
        match = re.match(r"^(.*?)(#\d+)$", value)
        if not match:
            return value, None
        return match.group(1) or "博士", match.group(2)

    @staticmethod
    def _category_name(record: dict) -> str:
        """把抽卡记录中的卡池类别转换为展示名称。"""
        category = record.get("category")
        if category == "normal":
            return "标准寻访"
        if category == "classic":
            return "中坚寻访"
        return "限定寻访"

    @staticmethod
    def _next_six_star_rate(pulls: int) -> float:
        """计算当前垫抽数下下一抽获得六星的概率。"""
        return float(max(2, 2 * (pulls - 50)))

    def _build_statistics(
        self,
        gacha_history: list[dict],
        doctor_name: str | None = None,
    ) -> GachaStatistics:
        """汇总原始抽卡记录，生成按类别和卡池划分的统计数据。"""
        records_by_pool: dict[str, list[dict]] = defaultdict(list)
        for record in gacha_history:
            if isinstance(record, dict):
                records_by_pool[record.get("poolName") or "未知卡池"].append(record)

        pools = []
        for pool_name, records in records_by_pool.items():
            records.sort(
                key=lambda record: (
                    int(record.get("gachaTs", 0)),
                    int(record.get("pos", 0)),
                )
            )
            pulls_since_six_star = 0
            six_stars = []
            for record in records:
                pulls_since_six_star += 1
                if record.get("rarity") != 5:
                    continue
                operator_name = record.get("charName") or "未知干员"
                width, color = self._bar_style(pulls_since_six_star)
                luck_label = "超欧" if pulls_since_six_star < 10 else "超非" if pulls_since_six_star > 60 else None
                six_stars.append(
                    SixStarRecord(
                        operator_name=operator_name,
                        pulls=pulls_since_six_star,
                        gacha_ts=int(record.get("gachaTs", 0)),
                        is_new=bool(record.get("isNew")),
                        avatar_url=self.build_operator_avatar_url(operator_name),
                        luck_label=luck_label,
                        bar_width=round(width, 2),
                        bar_color=color,
                    )
                )
                pulls_since_six_star = 0
            pools.append(
                PoolStatistics(
                    pool_name=pool_name,
                    total_pulls=len(records),
                    latest_gacha_ts=max(
                        (int(record.get("gachaTs", 0)) for record in records),
                        default=0,
                    ),
                    six_stars=tuple(reversed(six_stars)),
                )
            )

        pools.sort(key=lambda pool: pool.latest_gacha_ts, reverse=True)
        total_pulls = sum(pool.total_pulls for pool in pools)
        total_six_stars = sum(len(pool.six_stars) for pool in pools)
        category_records: dict[str, list[dict]] = {
            "标准寻访": [],
            "中坚寻访": [],
            "限定寻访": [],
        }
        for record in gacha_history:
            if isinstance(record, dict):
                category_records[self._category_name(record)].append(record)

        categories = []
        for category_name, records in category_records.items():
            records.sort(
                key=lambda record: (
                    int(record.get("gachaTs", 0)),
                    int(record.get("pos", 0)),
                )
            )
            pulls_since_last_six_star = 0
            for record in records:
                pulls_since_last_six_star += 1
                if record.get("rarity") == 5:
                    pulls_since_last_six_star = 0
            categories.append(
                CategoryStatistics(
                    category_name=category_name,
                    total_pulls=len(records),
                    pulls_since_last_six_star=pulls_since_last_six_star,
                    next_six_star_rate=self._next_six_star_rate(
                        pulls_since_last_six_star
                    ),
                )
            )

        display_name, suffix = self._split_doctor_name(doctor_name)
        return GachaStatistics(
            doctor_name=display_name,
            doctor_suffix=suffix,
            total_pulls=total_pulls,
            total_six_stars=total_six_stars,
            six_star_rate=(total_six_stars / total_pulls * 100) if total_pulls else 0.0,
            average_pulls_per_six_star=(total_pulls / total_six_stars) if total_six_stars else None,
            categories=tuple(categories),
            pools=tuple(pools),
        )

    async def abuild_statistics(
        self,
        gacha_history: list[dict],
        doctor_name: str | None = None,
    ) -> GachaStatistics:
        """在线程中构建统计数据并填充本地缓存的头像。"""
        statistics = await asyncio.to_thread(
            self._build_statistics,
            gacha_history,
            doctor_name,
        )
        return await asyncio.to_thread(self._hydrate_avatar_cache, statistics)

    def _avatar_cache_path(self, operator_name: str) -> Path:
        """返回指定干员对应的头像缓存文件路径。"""
        digest = hashlib.sha256(operator_name.encode("utf-8")).hexdigest()
        return self.avatar_cache_dir / f"{digest}.png"

    @staticmethod
    def _avatar_data_url(content: bytes) -> str:
        """将 PNG 图片字节编码为可嵌入页面的 Data URL。"""
        encoded = base64.b64encode(content).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    def _get_cached_avatar(self, operator_name: str, remote_url: str) -> str:
        """永久缓存头像；缓存不可用时回退到远程 URL"""
        cache_path = self._avatar_cache_path(operator_name)
        try:
            with self._avatar_cache_lock:
                if cache_path.is_file():
                    content = cache_path.read_bytes()
                    if content.startswith(self.PNG_SIGNATURE):
                        return self._avatar_data_url(content)

            response = requests.get(
                remote_url,
                timeout=self.AVATAR_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            content = response.content
            content_type = response.headers.get("Content-Type", "").lower()
            if not content.startswith(self.PNG_SIGNATURE) or len(content) > self.MAX_AVATAR_SIZE:
                return remote_url
            if content_type and not content_type.startswith("image/"):
                return remote_url

            with self._avatar_cache_lock:
                temporary_path = cache_path.with_suffix(".tmp")
                temporary_path.write_bytes(content)
                temporary_path.replace(cache_path)
            return self._avatar_data_url(content)
        except (OSError, requests.RequestException):
            return remote_url

    def _hydrate_avatar_cache(self, statistics: GachaStatistics) -> GachaStatistics:
        """并发下载缺失头像，并用本地 Data URL 更新统计数据。"""
        avatar_sources = {
            item.operator_name: item.avatar_url
            for pool in statistics.pools
            for item in pool.six_stars
        }
        with ThreadPoolExecutor(max_workers=min(6, len(avatar_sources) or 1)) as executor:
            resolved_avatars = dict(
                zip(
                    avatar_sources,
                    executor.map(
                        lambda entry: self._get_cached_avatar(*entry),
                        avatar_sources.items(),
                    ),
                )
            )

        pools = []
        for pool in statistics.pools:
            six_stars = tuple(
                replace(
                    item,
                    avatar_url=resolved_avatars.get(item.operator_name, item.avatar_url),
                )
                for item in pool.six_stars
            )
            pools.append(replace(pool, six_stars=six_stars))
        return replace(statistics, pools=tuple(pools))

    @staticmethod
    def build_render_data(statistics: GachaStatistics) -> dict:
        """将统计数据类转换为 HTML 渲染所需的字典。"""
        return asdict(statistics)

    @staticmethod
    def build_text_summary(statistics: GachaStatistics) -> str:
        """生成图片渲染失败时使用的纯文本统计摘要。"""
        sections = [
            f"博士：{statistics.doctor_name}{statistics.doctor_suffix or ''}",
            f"生涯总抽数：{statistics.total_pulls}",
            f"六星总数：{statistics.total_six_stars}",
            f"平均六星率：{statistics.six_star_rate:.2f}%",
        ]
        for category in statistics.categories:
            sections.append(
                f"【{category.category_name}】总计 {category.total_pulls} 抽，"
                f"已垫 {category.pulls_since_last_six_star} 抽，"
                f"下一抽六星概率 {category.next_six_star_rate:g}%"
            )
        for pool in statistics.pools:
            lines = [f"【{pool.pool_name}】总计 {pool.total_pulls} 抽"]
            if pool.six_stars:
                for item in pool.six_stars:
                    tags = ["NEW"] if item.is_new else []
                    if item.luck_label:
                        tags.append(item.luck_label)
                    suffix = f"（{' / '.join(tags)}）" if tags else ""
                    lines.append(f"{item.operator_name}：{item.pulls} 抽{suffix}")
            else:
                lines.append("暂无六星干员记录")
            sections.append("\n".join(lines))
        return "\n\n".join(sections)
