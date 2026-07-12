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
body { width: 1400px; padding: 54px; color: #edf3ff; font-family: "Microsoft YaHei", "Noto Sans SC", sans-serif; background: radial-gradient(circle at 12% 5%, rgba(54,126,255,.26), transparent 28%), radial-gradient(circle at 92% 0%, rgba(255,176,65,.18), transparent 25%), #0b1120; }
.header { padding: 38px 42px; border: 1px solid rgba(255,255,255,.12); border-radius: 24px; background: linear-gradient(135deg, rgba(25,39,68,.96), rgba(13,22,40,.96)); box-shadow: 0 18px 45px rgba(0,0,0,.28); }
.eyebrow { color: #82aaff; font-size: 17px; letter-spacing: 5px; font-weight: 700; }
h1 { margin: 10px 0 18px; font-size: 52px; line-height: 1.15; }
.doctor { margin-bottom: 12px; color: #fff; font-size: 30px; font-weight: 800; }
.doctor-suffix { margin-left: 8px; color: #9eacc4; font-size: 17px; font-weight: 500; }
.date-notice { margin-bottom: 28px; color: #fff; font-size: 18px; font-weight: 400; }
.metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.metric { padding: 21px 23px; border-radius: 18px; background: rgba(255,255,255,.065); }
.metric-label { color: #9eacc4; font-size: 18px; }
.metric-value { margin-top: 7px; font-size: 35px; font-weight: 800; }
.categories { margin-top: 16px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.category { padding: 19px 22px; border: 1px solid rgba(130,170,255,.18); border-radius: 18px; background: rgba(48,69,108,.3); }
.category-name { color: #dce8ff; font-size: 21px; font-weight: 800; }
.category-total { margin-top: 8px; color: #aab7cc; font-size: 16px; }
.category-pity { margin-top: 10px; font-size: 20px; font-weight: 750; }
.category-rate { color: #ffd16e; font-size: 29px; font-weight: 900; }
.pools { margin-top: 28px; display: grid; gap: 23px; }
.pool-card { padding: 31px 34px; border: 1px solid rgba(255,255,255,.1); border-radius: 22px; background: rgba(18,29,50,.94); box-shadow: 0 12px 32px rgba(0,0,0,.2); break-inside: avoid; }
.pool-head { display: flex; justify-content: space-between; align-items: baseline; gap: 20px; }
.pool-name { font-size: 34px; font-weight: 800; }
.pool-total { color: #aab7cc; font-size: 21px; white-space: nowrap; }
.operators { margin-top: 23px; display: grid; gap: 17px; }
.operator { display: grid; grid-template-columns: 88px 250px 1fr 96px; align-items: center; gap: 19px; }
.avatar { width: 80px; height: 80px; object-fit: cover; border-radius: 17px; background: #202b40; border: 2px solid rgba(255,255,255,.16); }
.name-row { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; }
.operator-name { font-size: 25px; font-weight: 750; }
.tag { padding: 4px 10px; border-radius: 999px; font-size: 15px; font-weight: 900; }
.new { color: #2a1300; background: linear-gradient(135deg, #ffe071, #ff9d35); box-shadow: 0 0 14px rgba(255,177,57,.35); }
.lucky { color: #032b22; background: #6bf0c2; }
.unlucky { color: #fff; background: #e45757; }
.bar-track { height: 28px; border-radius: 999px; background: rgba(255,255,255,.075); overflow: hidden; }
.bar { height: 100%; min-width: 8px; border-radius: inherit; }
.pull-count { text-align: right; font-size: 24px; font-weight: 800; }
.empty { margin-top: 23px; padding: 28px; font-size: 20px; text-align: center; color: #8f9db4; border: 1px dashed rgba(255,255,255,.13); border-radius: 15px; }
.footer { margin-top: 22px; color: #68768f; text-align: center; font-size: 13px; }
</style></head><body>
<section class="header"><div class="eyebrow">ARKNIGHTS · HEADHUNTING</div><h1>寻访生涯统计</h1>
<div class="doctor">Dr. {{ doctor_name }}{% if doctor_suffix %}<span class="doctor-suffix">({{ doctor_suffix }})</span>{% endif %}</div>
<div class="date-notice">由于服务器限制，仅统计用户绑定之日起前推 90 天之后的数据</div>
<div class="metrics">
<div class="metric"><div class="metric-label">生涯总抽数</div><div class="metric-value">{{ total_pulls }}</div></div>
<div class="metric"><div class="metric-label">六星总数</div><div class="metric-value">{{ total_six_stars }}</div></div>
<div class="metric"><div class="metric-label">平均六星率</div><div class="metric-value">{{ '%.2f'|format(six_star_rate) }}%</div></div>
<div class="metric"><div class="metric-label">平均六星抽数</div><div class="metric-value">{% if average_pulls_per_six_star is not none %}{{ '%.1f'|format(average_pulls_per_six_star) }}{% else %}—{% endif %}</div></div>
</div><div class="categories">{% for category in categories %}<div class="category"><div class="category-name">{{ category.category_name }}</div><div class="category-total">总计 {{ category.total_pulls }} 抽 · 当前已垫 {{ category.pulls_since_last_six_star }} 抽</div><div class="category-pity">下一抽六星概率 <span class="category-rate">{{ '%g'|format(category.next_six_star_rate) }}%</span></div></div>{% endfor %}</div>
</section><main class="pools">
{% for pool in pools %}<section class="pool-card"><div class="pool-head"><div class="pool-name">{{ pool.pool_name }}</div><div class="pool-total">总计 {{ pool.total_pulls }} 抽 · {{ pool.six_stars|length }} 个六星</div></div>
{% if pool.six_stars %}<div class="operators">{% for item in pool.six_stars %}<div class="operator"><img class="avatar" src="{{ item.avatar_url }}" alt="{{ item.operator_name }}"><div class="name-row"><span class="operator-name">{{ item.operator_name }}</span>{% if item.is_new %}<span class="tag new">NEW</span>{% endif %}{% if item.luck_label == '超欧' %}<span class="tag lucky">超欧</span>{% elif item.luck_label == '超非' %}<span class="tag unlucky">超非</span>{% endif %}</div><div class="bar-track"><div class="bar" style="width: {{ item.bar_width }}%; background: {{ item.bar_color }}"></div></div><div class="pull-count">{{ item.pulls }} 抽</div></div>{% endfor %}</div>
{% else %}<div class="empty">该卡池暂无六星记录</div>{% endif %}</section>{% endfor %}</main>
<div class="footer">数据来自已保存的寻访记录 · 六星稀有度按 rarity = 5 统计</div></body></html>
"""
