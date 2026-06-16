#!/usr/bin/env python3
r"""
济南区域 · 销售数据转换器 v5.0 (自动切片+环比版)
============================================================
新数据体系:
  D:\zkn\济南\数据\
    ├── 本月_客单分析报表.csv      ← 当月全量(含时间列)
    ├── 本月_类别销售分析.csv      ← 当月品类(含日期列)
    ├── 本月_充值销售汇总.csv      ← 当月储值(含日期列)
    ├── 上月_客单分析报表.csv      ← 上月全量(环比源)
    ├── 上月_类别销售分析.csv      ← 上月品类
    └── 上月_充值销售汇总.csv      ← 上月储值

切片逻辑:
  日报: 昨日 vs 上周同日(同星期)
  周报: 本周一~昨日 vs 上周一~周日
  月报: 本月1日~昨日 vs 上月全量

用法:
  python convert.py                  → 处理全部
  python convert.py --mode daily     → 仅日报
  python convert.py --date 2026-06-15 → 指定"昨日"
============================================================
"""

import csv, json, os, sys, re
from datetime import date, datetime, timedelta
from collections import defaultdict
from pathlib import Path

# ═══ 路径配置 ═══
BASE_DIR   = Path(__file__).parent
DATA_DIR   = Path("D:/zkn/济南/数据")
TASK_DIR   = Path("D:/zkn/济南/任务配置")
OUTPUT_DIR = BASE_DIR / "data"
HISTORY    = OUTPUT_DIR / "history"

# 默认: 昨日
DEFAULT_YESTERDAY = date.today() - timedelta(days=1)

# ═══════════════════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════════════════

def strip(s):
    return (s or '').strip().lstrip('\ufeff').strip('"')

def find_file(name_hint):
    """在 DATA_DIR 中查找文件，支持模糊匹配"""
    if not DATA_DIR.exists():
        return None
    for f in sorted(DATA_DIR.glob("*.csv")):
        if f.name.startswith('~$'):
            continue
        if name_hint in f.name:
            return f
    return None

def detect_encoding(csv_path):
    for enc in ('utf-8-sig', 'utf-8', 'gbk', 'gb2312', 'gb18030'):
        try:
            with open(csv_path, 'r', encoding=enc) as f:
                f.readline()
            return enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    return 'gbk'

def parse_date(d):
    """解析日期: 2026-06-01 或 2026/6/1"""
    d = strip(d)
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y/%-m/%-d'):
        try:
            return datetime.strptime(d, fmt).date()
        except ValueError:
            continue
    return None

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def fmt_money(v):
    return round(v, 2)

# ═══════════════════════════════════════════════════
#  Target 配置
# ═══════════════════════════════════════════════════

def load_targets():
    for p in [TASK_DIR / "targets.json", OUTPUT_DIR / "targets.json"]:
        if p.exists():
            with open(p, 'r', encoding='utf-8') as f:
                return json.load(f)
    return {"month_target": 0, "stores": {}}

def normalize_name(n):
    n = re.sub(r'^济南市?', '', n.strip())
    n = re.sub(r'店$', '', n)
    return n.strip()

def match_store(csv_name, targets_map):
    if csv_name in targets_map:
        return csv_name
    n = normalize_name(csv_name)
    for k in targets_map:
        if normalize_name(k) == n:
            return k
    for k in targets_map:
        nk = normalize_name(k)
        if n in nk or nk in n:
            return k
    return None

# ═══════════════════════════════════════════════════
#  CSV 解析 (本月 / 上月通用)
# ═══════════════════════════════════════════════════

def parse_store_csv(csv_path, date_filter=None):
    """
    解析 客单分析报表.csv
    标题行 + 表头: 时间,机构名称,门店编号,门店名称,门店类型,销售数量,销售金额,实收金额,订单数,客单价
    返回: [{date, store, qty, sales_amount, revenue, orders, avg_ticket}]
    """
    if not csv_path or not csv_path.exists():
        return []
    enc = detect_encoding(csv_path)
    rows = []

    with open(csv_path, 'r', encoding=enc) as f:
        raw = f.read()
        # 找表头行
        lines = raw.split('\n')
        header_idx = None
        for i, line in enumerate(lines):
            if '门店名称' in line and '实收金额' in line:
                header_idx = i
                break
        if header_idx is None:
            return rows

        reader = csv.DictReader(lines[header_idx:])
        for row in reader:
            d = parse_date(row.get('时间', row.get('日期', '')))
            if not d:
                continue
            if date_filter:
                if isinstance(date_filter, (list, tuple)):
                    if not (date_filter[0] <= d <= date_filter[1]):
                        continue
                elif d != date_filter:
                    continue

            rows.append({
                'date':       d,
                'store':      strip(row.get('门店名称', '')),
                'qty':        float(row.get('销售数量', 0) or 0),
                'sales_amount': float(row.get('销售金额', 0) or 0),
                'revenue':    float(row.get('实收金额', 0) or 0),
                'orders':     int(float(row.get('订单数', 0) or 0)),
                'avg_ticket': float(row.get('客单价', 0) or 0),
            })
    return rows

def parse_category_csv(csv_path, date_filter=None):
    """
    解析 类别销售分析.csv
    表头: 日期,门店名称,门店编号,二级类别,销售数量,销售金额,实收金额,...
    返回: [{date, store, category, qty, revenue}]
    """
    if not csv_path or not csv_path.exists():
        return []
    enc = detect_encoding(csv_path)
    rows = []

    with open(csv_path, 'r', encoding=enc) as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = parse_date(row.get('日期', row.get('时间', '')))
            if not d:
                continue
            if date_filter:
                if isinstance(date_filter, (list, tuple)):
                    if not (date_filter[0] <= d <= date_filter[1]):
                        continue
                elif d != date_filter:
                    continue

            rows.append({
                'date':     d,
                'store':    strip(row.get('门店名称', '')),
                'category': strip(row.get('二级类别', '')),
                'qty':      float(row.get('销售数量', 0) or 0),
                'revenue':  float(row.get('实收金额', 0) or 0),
            })
    return rows

def parse_recharge_csv(csv_path, date_filter=None):
    """
    解析 充值销售汇总.csv
    表头: 日期,门店编号,门店名称,实付金额,到账金额
    返回: [{date, store, paid, received}]
    """
    if not csv_path or not csv_path.exists():
        return []
    enc = detect_encoding(csv_path)
    rows = []

    with open(csv_path, 'r', encoding=enc) as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = parse_date(row.get('日期', row.get('时间', '')))
            if not d:
                continue
            if date_filter:
                if isinstance(date_filter, (list, tuple)):
                    if not (date_filter[0] <= d <= date_filter[1]):
                        continue
                elif d != date_filter:
                    continue

            rows.append({
                'date':     d,
                'store':    strip(row.get('门店名称', '')),
                'paid':     float(row.get('实付金额', 0) or 0),
                'received': float(row.get('到账金额', 0) or 0),
            })
    return rows

# ═══════════════════════════════════════════════════
#  聚合 & 计算
# ═══════════════════════════════════════════════════

def agg_stores(store_rows, targets):
    """按门店聚合销售"""
    m = defaultdict(lambda: {'sales': 0, 'qty': 0, 'orders': 0})
    for r in store_rows:
        m[r['store']]['sales']  += r['revenue']
        m[r['store']]['qty']    += r['qty']
        m[r['store']]['orders'] += r['orders']

    stores = []
    targets_stores = targets.get('stores', {})
    for name, d in m.items():
        mk = match_store(name, targets_stores)
        t = targets_stores.get(mk, {}) if mk else {}
        stores.append({
            'name':      name,
            'area':      t.get('area', ''),
            'sales':     fmt_money(d['sales']),
            'target':    t.get('target', targets.get('default_store_target', 120000)),
            'customers': d['orders'],
            'avg_bill':  fmt_money(d['sales'] / d['orders']) if d['orders'] > 0 else 0,
        })
    return stores

def agg_categories(cat_rows):
    """按二级类别聚合"""
    m = defaultdict(lambda: {'sales': 0})
    for r in cat_rows:
        m[r['category']]['sales'] += r['revenue']

    total = sum(c['sales'] for c in m.values())
    return sorted([
        {'name': n, 'sales': fmt_money(d['sales']),
         'share': round(d['sales']/total*100, 1) if total > 0 else 0}
        for n, d in m.items()
    ], key=lambda x: -x['sales'])

def agg_recharge(rec_rows):
    """按门店聚合储值"""
    m = defaultdict(float)
    for r in rec_rows:
        m[r['store']] += r['received']
    total = round(sum(m.values()), 2)
    return {'stores': {k: round(v, 2) for k, v in m.items()}, 'total': total}

def agg_areas(stores, targets):
    """按区域聚合"""
    m = defaultdict(lambda: {'sales': 0, 'store_count': 0, 'target': 0})
    for s in stores:
        a = s.get('area', '其他')
        m[a]['sales']  += s['sales']
        m[a]['store_count'] += 1
        m[a]['target'] += s.get('target', 0)

    meta_areas = targets.get('_meta', {}).get('areas', {})
    return sorted([{
        'name': n,
        'manager': meta_areas.get(n, {}).get('manager', ''),
        'color':   meta_areas.get(n, {}).get('color', '#2563eb'),
        'sales':   fmt_money(d['sales']),
        'stores':  d['store_count'],
        'target':  d['target'],
    } for n, d in m.items()], key=lambda x: -x['sales'])

def calc_ranks(stores, prev_stores):
    """计算排名变化"""
    if prev_stores:
        pm = {ps['name']: i+1 for i, ps in enumerate(prev_stores)}
        for s in stores:
            s['prev_rank'] = pm.get(s['name'], len(stores))
    else:
        for i, s in enumerate(stores):
            s['prev_rank'] = i+1

def build_trend(store_rows, target_amount):
    """
    从每日明细构建趋势数据
    返回: {dates, sales_amounts, completion_rates, daily_targets}
    """
    daily_sales = defaultdict(float)
    for r in store_rows:
        daily_sales[r['date']] += r['revenue']

    ds = sorted(daily_sales.keys())
    if not ds:
        return {'dates': [], 'sales_amounts': [], 'completion_rates': [], 'daily_targets': []}

    # 计算日均目标 = 月目标 / 月天数
    if ds:
        month_days = max(
            calendar_month_days(ds[0]),
            len(ds)
        )
    else:
        month_days = 30
    daily_target = round(target_amount / month_days, 2) if month_days else 0

    dates = sorted(ds)
    return {
        'dates':            [d.strftime('%m/%d') for d in dates],
        'sales_amounts':    [fmt_money(daily_sales[d]) for d in dates],
        'completion_rates': [round(daily_sales[d]/daily_target*100, 1) if daily_target else 0 for d in dates],
        'daily_targets':    [daily_target] * len(dates),
    }

def calendar_month_days(d):
    import calendar
    return calendar.monthrange(d.year, d.month)[1]

# ═══════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════

def build_period(yesterday, targets, store_cur, store_prev,
                 cat_cur, cat_prev, rec_cur, rec_prev,
                 date_range_cur, date_range_prev, label_cur, label_prev,
                 is_month=False):
    """
    通用周期计算
    """
    # 本期
    cur_store_rows   = [r for r in store_cur if (date_range_cur[0] <= r['date'] <= date_range_cur[1])]
    cur_cat_rows     = [r for r in cat_cur   if (date_range_cur[0] <= r['date'] <= date_range_cur[1])]
    cur_rec_rows     = [r for r in rec_cur   if (date_range_cur[0] <= r['date'] <= date_range_cur[1])]

    # 上期
    prev_store_rows  = [r for r in store_prev if (date_range_prev[0] <= r['date'] <= date_range_prev[1])] if store_prev else []
    prev_cat_rows    = [r for r in cat_prev   if (date_range_prev[0] <= r['date'] <= date_range_prev[1])] if cat_prev else []
    prev_rec_rows    = [r for r in rec_prev   if (date_range_prev[0] <= r['date'] <= date_range_prev[1])] if rec_prev else []

    # 聚合门店
    stores      = agg_stores(cur_store_rows, targets)
    prev_stores = agg_stores(prev_store_rows, targets) if prev_store_rows else []
    calc_ranks(stores, prev_stores)

    # 门店环比（上期销售额用于对比）
    prev_store_map = {s['name']: s['sales'] for s in prev_stores}
    for s in stores:
        s['last_sales'] = prev_store_map.get(s['name'], 0)

    # 聚合品类
    cats      = agg_categories(cur_cat_rows)
    prev_cats = agg_categories(prev_cat_rows) if prev_cat_rows else []
    # 品类环比
    prev_map = {c['name']: c['sales'] for c in prev_cats}
    for c in cats:
        c['last_sales'] = prev_map.get(c['name'], 0)

    # 聚合储值
    recharge      = agg_recharge(cur_rec_rows)
    prev_recharge = agg_recharge(prev_rec_rows) if prev_rec_rows else {'total': 0}

    # 聚合区域
    areas      = agg_areas(stores, targets)
    prev_areas = agg_areas(prev_stores, targets) if prev_stores else []
    prev_area_map = {a['name']: a['sales'] for a in prev_areas}
    for a in areas:
        a['last_sales'] = prev_area_map.get(a['name'], 0)

    # 月报模式: 区域目标缩放至全月
    if is_month:
        days_in_period = (date_range_cur[1] - date_range_cur[0]).days + 1
        month_days = calendar_month_days(date_range_cur[1])
        scale = month_days / max(days_in_period, 1)
        for a in areas:
            a['target'] = round(a['target'] * scale, 2)

    # KPI
    total    = round(sum(s['sales'] for s in stores), 2)
    prev_total = round(sum(s['sales'] for s in prev_stores), 2) if prev_stores else 0
    customers = sum(s['customers'] for s in stores)
    avg_bill = round(total/customers, 2) if customers > 0 else 0
    prev_customers = sum(s['customers'] for s in prev_stores) if prev_stores else 0
    prev_avg_bill  = round(prev_total/prev_customers, 2) if prev_customers > 0 else 0

    # 达标门店（完成率 >= 85%）
    achieved = sum(1 for s in stores if s['target'] > 0 and s['sales'] >= s['target'] * 0.85)
    prev_achieved = sum(1 for s in prev_stores if s['target'] > 0 and s['sales'] >= s['target'] * 0.85) if prev_stores else 0

    # 目标金额 (月报用全月目标，日/周报用时间段累计目标)
    target_amount = sum(s['target'] for s in stores)
    month_target_for_kpi = targets.get('month_target', 0)
    if is_month and month_target_for_kpi > 0:
        target_amount = month_target_for_kpi

    # 趋势
    trend = build_trend(store_cur, targets.get('month_target', 0))

    # 月末缺口
    month_target    = targets.get('month_target', 0)
    month_completed = sum(r['revenue'] for r in store_cur)  # 全月累计
    day = yesterday.day if yesterday else date.today().day
    month_remaining_days = max(calendar_month_days(yesterday) - yesterday.day, 1) if yesterday else 30

    result = {
        'date':          label_cur,
        'compare_date':  label_prev,
        'is_month':      is_month,

        # KPI
        'total_sales':           total,
        'last_period_sales':     prev_total,
        'target_amount':         target_amount,
        'avg_bill':              avg_bill,
        'last_period_avg_bill':  prev_avg_bill,
        'total_customers':       customers,
        'achieved_stores':       achieved,
        'last_period_achieved':  prev_achieved,
        'total_stores':          len(stores),

        # 缺口
        'month_target':        month_target,
        'month_completed':     round(month_completed, 2),
        'month_remaining_days': month_remaining_days,

        # 明细
        'stores':  stores,
        'areas':   areas,
        'category_breakdown': cats,
        'recharge': {
            'current': recharge['total'],
            'last':    prev_recharge['total'],
        },
        'trend': trend,
    }

    return result


def run(yesterday=None):
    if yesterday is None:
        yesterday = DEFAULT_YESTERDAY

    print("=" * 60)
    print("  济南区域 · 销售数据转换器 v5.0 (自动切片)")
    print("=" * 60)
    print(f"  数据盘:  {DATA_DIR}")
    print(f"  昨日:    {yesterday.strftime('%Y-%m-%d')}")

    # ═══ 加载 targets ═══
    targets = load_targets()
    print(f"  门店配置: {len(targets.get('stores', {}))} 家")

    # ═══ 定位 CSV 文件 ═══
    cur_store_f  = find_file("本月_客单分析报表")
    cur_cat_f    = find_file("本月_类别销售分析")
    cur_rec_f    = find_file("本月_充值销售汇总")
    prev_store_f = find_file("上月_客单分析报表")
    prev_cat_f   = find_file("上月_类别销售分析")
    prev_rec_f   = find_file("上月_充值销售汇总")

    # 如果没有找到 "本月_" 前缀的，提示用户
    missing = []
    if not cur_store_f: missing.append("本月_客单分析报表.csv")
    if not cur_cat_f:   missing.append("本月_类别销售分析.csv")
    if not cur_rec_f:   missing.append("本月_充值销售汇总.csv")

    if missing:
        print(f"\n  ⚠️ 本月数据缺失: {', '.join(missing)}")
        print(f"  请将 CSV 文件放到 {DATA_DIR}")
        print(f"  文件命名规范: 本月_客单分析报表.csv / 本月_类别销售分析.csv / 本月_充值销售汇总.csv")
        if not cur_store_f:
            return 1

    # ═══ 解析 CSV ═══
    print(f"\n┌─ 📥 数据加载 ─────────────────────────")

    store_cur  = parse_store_csv(cur_store_f)
    cat_cur    = parse_category_csv(cur_cat_f)
    rec_cur    = parse_recharge_csv(cur_rec_f)
    store_prev = parse_store_csv(prev_store_f)
    cat_prev   = parse_category_csv(prev_cat_f)
    rec_prev   = parse_recharge_csv(prev_rec_f)

    print(f"│  本月_客单分析:  {len(store_cur)} 条")
    print(f"│  本月_类别销售:  {len(cat_cur)} 条")
    print(f"│  本月_充值销售:  {len(rec_cur)} 条")
    print(f"│  上月_客单分析:  {len(store_prev)} 条" if store_prev else "│  上月_客单分析:  无")
    print(f"│  上月_类别销售:  {len(cat_prev)} 条" if cat_prev else "│  上月_类别销售:  无")
    print(f"│  上月_充值销售:  {len(rec_prev)} 条" if rec_prev else "│  上月_充值销售:  无")

    if not store_cur:
        print("│  ❌ 本月门店销售数据为空!")
        return 1

    # ═══ 日期范围 ═══
    all_dates = sorted(set(r['date'] for r in store_cur))
    print(f"│  数据范围: {all_dates[0]} ~ {all_dates[-1]} ({len(all_dates)}天)")

    # 如果是上月的文件（比如本月文件实际包含上月数据），
    # 上月文件用于月环比，日/周环比优先从本月文件切片
    # 如果昨天不在本月文件中，尝试用上月文件
    # 但一般情况下本月文件应该包含昨天

    if yesterday not in all_dates:
        print(f"│  ⚠️ 昨日 {yesterday} 不在本月数据中!")
        # 尝试找包含昨天的文件
        if store_prev and yesterday in set(r['date'] for r in store_prev):
            print(f"│  → 上月文件包含昨天数据，将用作本期源")
            store_cur, store_prev = store_prev, store_cur
            cat_cur, cat_prev = cat_prev, cat_cur
            rec_cur, rec_prev = rec_prev, rec_cur

    # ═══ 日报: 昨天 vs 上周同星期 ═══
    print(f"\n┌─ 📅 日报 ────────────────────────────")
    daily_date = yesterday
    daily_compare = yesterday - timedelta(weeks=1)
    print(f"│  本期: {daily_date}")
    print(f"│  环比: {daily_compare} (同星期)")

    daily = build_period(
        yesterday, targets,
        store_cur, store_cur,         # 本期和上期都优先从本月找
        cat_cur,   cat_cur,
        rec_cur,   rec_cur,
        (daily_date, daily_date),
        (daily_compare, daily_compare),
        daily_date.strftime('%Y-%m-%d'),
        daily_compare.strftime('%Y-%m-%d'),
        is_month=False,
    )

    # 如果上期数据在当月找不到(跨月)，回退到上月文件
    if daily['last_period_sales'] == 0 and store_prev:
        print("│  ℹ️  上期不在本月，回退到上月...")
        prev_store_rows = [r for r in store_prev if r['date'] == daily_compare] if store_prev else []
        prev_cat_rows   = [r for r in cat_prev   if r['date'] == daily_compare] if cat_prev else []
        prev_rec_rows   = [r for r in rec_prev   if r['date'] == daily_compare] if rec_prev else []

        prev_stores = agg_stores(prev_store_rows, targets)
        prev_total  = round(sum(s['sales'] for s in prev_stores), 2)
        prev_cust    = sum(s['customers'] for s in prev_stores)
        prev_avg_bill = round(prev_total/prev_cust, 2) if prev_cust > 0 else 0
        prev_achieved = sum(1 for s in prev_stores if s['target'] > 0 and s['sales'] >= s['target'] * 0.85)

        daily['last_period_sales']    = prev_total
        daily['last_period_avg_bill'] = prev_avg_bill
        daily['last_period_achieved'] = prev_achieved

        # 更新排名环比
        calc_ranks(daily['stores'], prev_stores)

        # 品类环比
        prev_cats = agg_categories(prev_cat_rows)
        prev_map  = {c['name']: c['sales'] for c in prev_cats}
        for c in daily['category_breakdown']:
            c['last_sales'] = prev_map.get(c['name'], 0)

        # 储值环比
        prev_rec = agg_recharge(prev_rec_rows)
        daily['recharge']['last'] = prev_rec['total']

    write_json(OUTPUT_DIR / "daily.json", daily)
    write_json(HISTORY / f"{daily_date.strftime('%Y-%m-%d')}.json", daily)
    print(f"│  ✅ daily.json  ¥{daily['total_sales']:,.0f} (环比 ¥{daily['last_period_sales']:,.0f})")

    # ═══ 周报: 本周一~昨天 vs 上周一~周日 ═══
    print(f"\n┌─ 📊 周报 ────────────────────────────")
    wd = yesterday.weekday()  # 0=Mon, 6=Sun
    week_start = yesterday - timedelta(days=wd)
    week_end   = yesterday
    last_week_start = week_start - timedelta(weeks=1)
    last_week_end   = week_start - timedelta(days=1)

    print(f"│  本期: {week_start} ~ {week_end}")
    print(f"│  环比: {last_week_start} ~ {last_week_end}")

    weekly = build_period(
        yesterday, targets,
        store_cur, store_cur,
        cat_cur,   cat_cur,
        rec_cur,   rec_cur,
        (week_start, week_end),
        (last_week_start, last_week_end),
        f"{week_start.strftime('%m/%d')} ~ {(week_start + timedelta(days=6)).strftime('%m/%d')} (截至{week_end.strftime('%m/%d')})",
        f"上周 ({last_week_start.strftime('%m/%d')}-{last_week_end.strftime('%m/%d')})",
        is_month=False,
    )

    # 周上期跨月回退
    if weekly['last_period_sales'] == 0 and store_prev:
        print("│  ℹ️  上周部分不在本月，合并上月数据...")
        prev_rows_in_cur = [r for r in store_cur if last_week_start <= r['date'] <= last_week_end]
        prev_rows_in_prev = [r for r in store_prev if last_week_start <= r['date'] <= last_week_end]
        all_prev = prev_rows_in_cur + prev_rows_in_prev
        if all_prev:
            prev_stores = agg_stores(all_prev, targets)
            prev_total  = round(sum(s['sales'] for s in prev_stores), 2)
            prev_cust    = sum(s['customers'] for s in prev_stores)
            prev_avg_bill = round(prev_total/prev_cust, 2) if prev_cust > 0 else 0
            prev_achieved = sum(1 for s in prev_stores if s['target'] > 0 and s['sales'] >= s['target'] * 0.85)
            weekly['last_period_sales']    = prev_total
            weekly['last_period_avg_bill'] = prev_avg_bill
            weekly['last_period_achieved'] = prev_achieved
            calc_ranks(weekly['stores'], prev_stores)

    write_json(OUTPUT_DIR / "weekly.json", weekly)
    print(f"│  ✅ weekly.json  ¥{weekly['total_sales']:,.0f} (环比 ¥{weekly['last_period_sales']:,.0f})")

    # ═══ 月报: 本月1日~昨天 vs 上月全量 ═══
    print(f"\n┌─ 📈 月报 ────────────────────────────")
    month_start = yesterday.replace(day=1)
    month_end   = yesterday
    last_month_end   = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    print(f"│  本期: {month_start} ~ {month_end}")
    print(f"│  环比: 上月 ({last_month_start} ~ {last_month_end})")

    monthly = build_period(
        yesterday, targets,
        store_cur, store_prev or store_cur,
        cat_cur,   cat_prev   or cat_cur,
        rec_cur,   rec_prev   or rec_cur,
        (month_start, month_end),
        (last_month_start, last_month_end),
        f"{month_start.strftime('%Y年%m月')} (1-{month_end.day}日)",
        f"{last_month_start.strftime('%Y年%m月')}",
        is_month=True,
    )

    write_json(OUTPUT_DIR / "monthly.json", monthly)
    print(f"│  ✅ monthly.json  ¥{monthly['total_sales']:,.0f} (环比 ¥{monthly['last_period_sales']:,.0f})")

    print(f"\n{'=' * 60}")
    print(f"  ✅ 全部完成: daily.json + weekly.json + monthly.json")
    print(f"  刷新浏览器查看最新数据")
    print("=" * 60)
    return 0


# ═══ CLI ═══
if __name__ == '__main__':
    mode = "all"
    target_date = None

    for i, a in enumerate(sys.argv):
        if a == '--mode' and i+1 < len(sys.argv):
            mode = sys.argv[i+1]
        if a == '--date' and i+1 < len(sys.argv):
            try:
                target_date = datetime.strptime(sys.argv[i+1], '%Y-%m-%d').date()
            except ValueError:
                print(f"❌ 日期格式错误，应为 YYYY-MM-DD")
                exit(1)

    yesterday = target_date or DEFAULT_YESTERDAY
    run(yesterday)
