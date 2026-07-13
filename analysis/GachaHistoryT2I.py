# analysis/GachaHistoryT2I.py

GACHA_STATISTICS_RENDER_OPTIONS = {
    "type": "png",
    "full_page": True,
    "animations": "disabled",
    "caret": "hide",
}

GACHA_STATISTICS_TEMPLATE = r"""
<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><style>
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body { width: 1400px; padding: 54px; color: #18202b; font-family: "Microsoft YaHei", "Noto Sans SC", sans-serif; background: linear-gradient(180deg, #fff 0%, #f7f8fa 48%, #e3e6ea 100%); }
.header { padding: 38px 42px; border: 1px solid #dfe4ea; border-radius: 24px; background: #fff; box-shadow: 0 18px 45px rgba(25,38,55,.12); }
.eyebrow { color: #246eb5; font-size: 17px; letter-spacing: 5px; font-weight: 700; }
h1 { margin: 10px 0 18px; font-size: 52px; line-height: 1.15; }
.doctor { margin-bottom: 12px; color: #17212d; font-size: 30px; font-weight: 800; }
.doctor-suffix { margin-left: 8px; color: #758292; font-size: 17px; font-weight: 500; }
.date-notice { margin-bottom: 28px; color: #566474; font-size: 18px; font-weight: 400; }
.metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.metric { padding: 21px 23px; border: 1px solid #e2e7ec; border-radius: 18px; background: #f5f7f9; }
.metric-label { color: #6f7d8d; font-size: 18px; }
.metric-value { margin-top: 7px; font-size: 35px; font-weight: 800; }
.categories { margin-top: 16px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.category { padding: 19px 22px; border: 1px solid #d9e3ed; border-radius: 18px; background: #f3f7fb; }
.category-name { color: #29445f; font-size: 21px; font-weight: 800; text-align: center; }
.category-total { margin-top: 8px; display: flex; justify-content: center; align-items: baseline; gap: 8px; color: #697888; text-align: center; }
.category-total-label { font-size: 16px; }
.category-total-value { color: #152536; font-size: 38px; line-height: 1; font-weight: 900; }
.category-total-unit { font-size: 18px; font-weight: 700; }
.category-padded { margin-top: 7px; color: #697888; font-size: 16px; text-align: center; }
.category-pity { margin-top: 10px; font-size: 20px; font-weight: 750; }
.category-rate { color: #c98b00; font-size: 29px; font-weight: 900; }
.pools { margin-top: 28px; display: grid; gap: 23px; }
.pool-card { padding: 31px 34px; border: 1px solid #dfe4ea; border-radius: 22px; background: #fff; box-shadow: 0 12px 32px rgba(25,38,55,.1); break-inside: avoid; }
.pool-head { display: flex; justify-content: space-between; align-items: baseline; gap: 20px; }
.pool-name { font-size: 34px; font-weight: 800; }
.pool-total { color: #697888; font-size: 21px; white-space: nowrap; }
.operators { margin-top: 23px; display: grid; gap: 17px; }
.operator { display: grid; grid-template-columns: 88px 250px 1fr 96px; align-items: center; gap: 19px; }
.avatar { width: 80px; height: 80px; object-fit: cover; border-radius: 17px; background: #eef1f4; border: 2px solid #dce2e8; }
.name-row { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; }
.operator-name { font-size: 25px; font-weight: 750; }
.tag { padding: 4px 10px; border-radius: 999px; font-size: 15px; font-weight: 900; }
.new { color: #2a1300; background: linear-gradient(135deg, #ffe071, #ff9d35); box-shadow: 0 0 14px rgba(255,177,57,.35); }
.lucky { color: #032b22; background: #6bf0c2; }
.unlucky { color: #fff; background: #e45757; }
.bar-track { height: 28px; border-radius: 999px; background: #e9edf1; overflow: hidden; }
.bar { height: 100%; min-width: 8px; border-radius: inherit; }
.pull-count { text-align: right; font-size: 24px; font-weight: 800; }
.empty { margin-top: 23px; padding: 28px; font-size: 20px; text-align: center; color: #7d8996; border: 1px dashed #cfd6dd; border-radius: 15px; background: #fafbfc; }
.footer { margin-top: 22px; color: #7b8794; text-align: center; font-size: 13px; }
</style></head><body>
<section class="header"><div class="eyebrow">ARKNIGHTS · HEADHUNTING</div><h1>寻访生涯统计</h1>
<div class="doctor">Dr. {{ doctor_name }}{% if doctor_suffix %}<span class="doctor-suffix">({{ doctor_suffix }})</span>{% endif %}</div>
<div class="date-notice">由于服务器限制，仅统计用户绑定之日起前推 90 天之后的数据</div>
<div class="metrics">
<div class="metric"><div class="metric-label">生涯总抽数</div><div class="metric-value">{{ total_pulls }}</div></div>
<div class="metric"><div class="metric-label">六星总数</div><div class="metric-value">{{ total_six_stars }}</div></div>
<div class="metric"><div class="metric-label">平均六星率</div><div class="metric-value">{{ '%.2f'|format(six_star_rate) }}%</div></div>
<div class="metric"><div class="metric-label">平均六星抽数</div><div class="metric-value">{% if average_pulls_per_six_star is not none %}{{ '%.1f'|format(average_pulls_per_six_star) }}{% else %}—{% endif %}</div></div>
</div><div class="categories">{% for category in categories %}<div class="category"><div class="category-name">{{ category.category_name }}</div><div class="category-total"><span class="category-total-label">总计</span><span class="category-total-value">{{ category.total_pulls }}</span><span class="category-total-unit">抽</span></div><div class="category-padded">当前已垫 {{ category.pulls_since_last_six_star }} 抽</div><div class="category-pity">下一抽六星概率 <span class="category-rate">{{ '%g'|format(category.next_six_star_rate) }}%</span></div></div>{% endfor %}</div>
</section><main class="pools">
{% for pool in pools %}<section class="pool-card"><div class="pool-head"><div class="pool-name">{{ pool.pool_name }}</div><div class="pool-total">总计 {{ pool.total_pulls }} 抽 · {{ pool.six_stars|length }} 个六星</div></div>
{% if pool.six_stars %}<div class="operators">{% for item in pool.six_stars %}<div class="operator"><img class="avatar" src="{{ item.avatar_url }}" alt="{{ item.operator_name }}"><div class="name-row"><span class="operator-name">{{ item.operator_name }}</span>{% if item.is_new %}<span class="tag new">NEW</span>{% endif %}{% if item.luck_label == '超欧' %}<span class="tag lucky">超欧</span>{% elif item.luck_label == '超非' %}<span class="tag unlucky">超非</span>{% endif %}</div><div class="bar-track"><div class="bar" style="width: {{ item.bar_width }}%; background: {{ item.bar_color }}"></div></div><div class="pull-count">{{ item.pulls }} 抽</div></div>{% endfor %}</div>
{% else %}<div class="empty">该卡池暂无六星记录</div>{% endif %}</section>{% endfor %}</main>
<div class="footer">数据来自已保存的寻访记录 · 六星稀有度按 rarity = 5 统计</div></body></html>
"""
