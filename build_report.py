import re, json, os, sys
from datetime import datetime
from collections import defaultdict

# --- Config ---
BASE_DIR = os.path.expanduser("~/marketplace-scraper")
SCRAPE_FILE = os.path.join(BASE_DIR, "scrape_results.txt")
SEEN_FILE = os.path.join(BASE_DIR, "seen-listings.json")
OUTPUT_FILE = os.path.join(BASE_DIR, "fb-marketplace-scan.html")

CATEGORIES = {
    "Original": ["vw bug", "vw bus", "toyota land cruiser", "ford bronco", "jeep wagoneer", "toyota pickup"],
    "Jeep / Off-Road": ["jeep cj", "jeep cherokee xj", "land rover defender"],
    "Trucks": ["chevy k10", "ford f100", "dodge power wagon", "chevy c10"],
    "Boats & Off-Road": ["jet boat", "sandrail"],
    "Small / Economy": ["datsun 510", "volkswagen rabbit", "toyota corolla", "honda civic classic"],
    "VW Adjacent": ["vw thing", "vw karmann ghia"],
    "Muscle / Classic": ["69 camaro"],
}

# Title-relevance keywords: a listing must contain at least one keyword to stay under a search term
RELEVANCE_KEYWORDS = {
    "vw bug": ["vw", "volkswagen", "beetle", "bug"],
    "vw bus": ["vw", "volkswagen", "bus", "vanagon", "baywindow", "splitwindow", "type 2", "eurovan", "westfalia"],
    "toyota land cruiser": ["land cruiser", "landcruiser", "fj40", "fj60", "fj80", "fzj80", "lx 470", "lx470"],
    "ford bronco": ["bronco"],
    "jeep wagoneer": ["wagoneer", "willys"],
    "toyota pickup": ["toyota", "tacoma", "hilux", "pickup", "pick up"],
    "jeep cj": ["cj", "cj5", "cj7", "cj-5", "cj-7"],
    "jeep cherokee xj": ["cherokee", "xj"],
    "land rover defender": ["land rover", "landrover", "defender", "discovery", "range rover", "lr3", "lr4"],
    "chevy k10": ["chevy", "chevrolet", "k10", "k20", "silverado", "gmc", "square body"],
    "ford f100": ["f100", "f-100", "f250", "f-250", "ford"],
    "dodge power wagon": ["dodge", "power wagon", "w200", "w100", "d150", "ramcharger"],
    "chevy c10": ["c10", "c-10", "chevy", "chevrolet", "cheyenne", "gmc", "square body"],
    "jet boat": ["jet boat", "jetboat", "jet", "boat"],
    "sandrail": ["sandrail", "sand rail", "dune buggy", "buggy", "rail"],
    "datsun 510": ["datsun", "nissan 510", "510"],
    "volkswagen rabbit": ["rabbit", "vw", "volkswagen"],
    "toyota corolla": ["corolla", "toyota"],
    "honda civic classic": ["honda", "civic"],
    "vw thing": ["thing", "vw", "volkswagen"],
    "vw karmann ghia": ["karmann", "ghia", "vw", "volkswagen"],
    "69 camaro": ["camaro", "chevy", "chevrolet"],
}

def parse_price(raw):
    if not raw or raw == "Free":
        return 0
    prices = re.findall(r'\$[\d,]+(?:\.\d+)?', raw)
    if not prices:
        return 0
    p = prices[0].replace('$', '').replace(',', '')
    try:
        return float(p)
    except:
        return 0

def parse_line(line):
    parts = line.strip().split('|')
    if len(parts) < 2:
        return None
    lid = parts[0].strip()
    if not lid or not lid.isdigit():
        return None
    raw_price = parts[1].strip() if len(parts) > 1 else ''
    title = parts[2].strip() if len(parts) > 2 else ''
    location = parts[3].strip() if len(parts) > 3 else ''
    image_url = parts[4].strip() if len(parts) > 4 else ''
    if title.startswith('$'):
        price = parse_price(raw_price)
        return {
            'id': lid, 'price': price, 'price_raw': raw_price,
            'title': f'(Listing {lid[:8]}...)',
            'location': location if not location.startswith('$') else '',
            'image_url': image_url,
            'url': f'https://www.facebook.com/marketplace/item/{lid}/'
        }
    price = parse_price(raw_price)
    return {
        'id': lid, 'price': price, 'price_raw': raw_price,
        'title': title, 'location': location,
        'image_url': image_url,
        'url': f'https://www.facebook.com/marketplace/item/{lid}/'
    }

def is_parts_listing(l):
    title = (l.get('title') or '').lower()
    price = l.get('price', 0)
    parts_kw = ['parts', 'part-out', 'partout', 'seats', 'seat', 'bumper', 'wheel', 'rim',
                 'tire', 'door', 'hood', 'fender', 'grille', 'grill', 'exhaust', 'engine',
                 'motor', 'transmission', 'trans ', 'axle', 'brake', 'headlight', 'taillight',
                 'window', 'mirror', 'rack', 'roof rack', 'roofrack', 'wanted', 'wtb',
                 'hot wheels', 'model', 'diecast', 'poster', 'manual', 'book', 'emblem',
                 'badge', 'decal', 'sticker', 'cover', 'mat', 'carpet', 'hubcap',
                 'transaxle', 'carburetor', 'carb', 'intake', 'headers', 'muffler',
                 'springs', 'shocks', 'struts', 'radiator', 'alternator', 'starter',
                 'rines', 'parrilla', 'long block', 'fan shroud']
    if any(kw in title for kw in parts_kw):
        return True
    if price > 0 and price < 150 and not re.search(r'19\d\d|20[012]\d', title):
        return True
    return False

def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE) as f:
                data = json.load(f)
            if isinstance(data, list):
                return {lid: {'price': 0, 'first_seen': today} for lid in data}
            return data
        except:
            pass
    return {}

def save_seen(seen):
    os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)
    with open(SEEN_FILE, 'w') as f:
        json.dump(seen, f, indent=2)

# --- Parse scrape results ---
listings_by_search = defaultdict(list)
current_search = None
today = datetime.now().strftime('%Y-%m-%d')

def is_relevant(listing, search_term):
    """Check if a listing title is relevant to the search term."""
    keywords = RELEVANCE_KEYWORDS.get(search_term)
    if not keywords:
        return True  # no filter defined, keep everything
    title = (listing.get('title') or '').lower()
    if not title or title.startswith('(listing'):
        return True  # can't filter untitled listings, keep them
    return any(kw in title for kw in keywords)

with open(SCRAPE_FILE) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        if line.startswith('=== ') and line.endswith(' ==='):
            current_search = line[4:-4].strip()
            continue
        if current_search:
            listing = parse_line(line)
            if listing and is_relevant(listing, current_search):
                listings_by_search[current_search].append(listing)

# --- Deduplicate across all searches ---
seen_ids = {}
all_listings = []
for search_term, listings in listings_by_search.items():
    for l in listings:
        lid = l['id']
        if lid not in seen_ids:
            l['search_terms'] = [search_term]
            seen_ids[lid] = l
            all_listings.append(l)
        else:
            if search_term not in seen_ids[lid]['search_terms']:
                seen_ids[lid]['search_terms'].append(search_term)

# --- Load historical data and compute deltas ---
prev_seen = load_seen()
new_listings = []
price_drops = []

for l in all_listings:
    lid = l['id']
    if lid in prev_seen:
        old_price = prev_seen[lid].get('price', 0)
        if old_price > 0 and l['price'] > 0 and l['price'] < old_price:
            l['old_price'] = old_price
            l['drop_pct'] = round((1 - l['price'] / old_price) * 100)
            price_drops.append(l)
        l['first_seen'] = prev_seen[lid].get('first_seen', today)
        l['days_on_market'] = (datetime.now() - datetime.strptime(l['first_seen'], '%Y-%m-%d')).days
        if not l.get('image_url'):
            l['image_url'] = prev_seen[lid].get('image_url', '')
    else:
        new_listings.append(l)
        l['first_seen'] = today
        l['days_on_market'] = 0

stale_listings = [l for l in all_listings if l.get('days_on_market', 0) >= 5]

# --- Detect sold listings (in prev_seen but missing 2+ days from scrape) ---
sold_listings = []
current_ids = set(l['id'] for l in all_listings)
for lid, data in prev_seen.items():
    if lid not in current_ids and not data.get('sold'):
        last_seen = data.get('last_seen', today)
        days_gone = (datetime.now() - datetime.strptime(last_seen, '%Y-%m-%d')).days
        if days_gone >= 2:
            first_seen = data.get('first_seen', today)
            days_on = (datetime.strptime(last_seen, '%Y-%m-%d') - datetime.strptime(first_seen, '%Y-%m-%d')).days
            sold_listings.append({
                'id': lid, 'title': data.get('title', '(unknown)'),
                'price': data.get('price', 0), 'price_raw': '',
                'location': '', 'first_seen': first_seen,
                'last_seen': last_seen,
                'days_on_market': days_on,
                'url': f'https://www.facebook.com/marketplace/item/{lid}/',
                'search_terms': data.get('search_terms', []),
                'image_url': data.get('image_url', ''),
                'is_parts': False, 'sold': True
            })
sold_vehicles = [l for l in sold_listings if not is_parts_listing(l)]
sold_vehicles.sort(key=lambda x: x.get('days_on_market', 0))

# --- Update seen file (preserve missing listings until sold, track sold) ---
new_seen = {}
# Active listings
for l in all_listings:
    prev_image = prev_seen.get(l['id'], {}).get('image_url', '')
    new_image = l.get('image_url', '')
    new_seen[l['id']] = {
        'price': l['price'], 'title': l['title'],
        'first_seen': l.get('first_seen', today),
        'last_seen': today,
        'search_terms': l.get('search_terms', []),
        'image_url': new_image if new_image else prev_image,
    }
# Carry forward missing listings (not yet 2 days gone) so we can detect sold later
for lid, data in prev_seen.items():
    if lid not in current_ids and not data.get('sold'):
        last_seen = data.get('last_seen', today)
        days_gone = (datetime.now() - datetime.strptime(last_seen, '%Y-%m-%d')).days
        if days_gone < 2:
            new_seen[lid] = data  # keep tracking, might reappear
        else:
            new_seen[lid] = {**data, 'sold': True, 'sold_date': today}  # mark as sold
save_seen(new_seen)

# --- Classify parts vs vehicles ---
for l in all_listings:
    l['is_parts'] = is_parts_listing(l)

# --- Organize by category, then by search term ---
category_data = {}
for cat_name, search_terms in CATEGORIES.items():
    category_data[cat_name] = {}
    for st in search_terms:
        vehicles, parts, seen_in_st = [], [], set()
        for l in listings_by_search.get(st, []):
            if l['id'] not in seen_in_st:
                seen_in_st.add(l['id'])
                (parts if l.get('is_parts') else vehicles).append(l)
        vehicles.sort(key=lambda x: (x['price'] == 0, x['price']))
        parts.sort(key=lambda x: (x['price'] == 0, x['price']))
        category_data[cat_name][st] = {'vehicles': vehicles, 'parts': parts}

# --- Stats ---
total_unique = len(all_listings)
total_new = len(new_listings)
total_drops = len(price_drops)
total_stale = len(stale_listings)
total_vehicles = sum(1 for l in all_listings if not l.get('is_parts'))
total_parts = sum(1 for l in all_listings if l.get('is_parts'))

search_stats = {}
for cat_name, search_terms in CATEGORIES.items():
    for st in search_terms:
        vehs = category_data[cat_name][st]['vehicles']
        prices = [l['price'] for l in vehs if l['price'] >= 500]
        if prices:
            avg = round(sum(prices) / len(prices))
            search_stats[st] = {'avg': avg, 'min': round(min(prices)), 'max': round(max(prices)), 'count': len(vehs)}
            for l in vehs:
                if l['price'] >= 500 and l['price'] < avg * 0.7:
                    l['is_deal'] = True
        else:
            search_stats[st] = {'avg': 0, 'min': 0, 'max': 0, 'count': len(vehs)}

cat_stats = {}
for cat_name, search_terms in CATEGORIES.items():
    all_cat_prices = []
    total_cat_count = 0
    for st in search_terms:
        vehs = category_data[cat_name][st]['vehicles']
        all_cat_prices.extend([l['price'] for l in vehs if l['price'] >= 500])
        total_cat_count += len(category_data[cat_name][st]['vehicles']) + len(category_data[cat_name][st]['parts'])
    if all_cat_prices:
        cat_stats[cat_name] = {
            'avg': round(sum(all_cat_prices) / len(all_cat_prices)),
            'min': round(min(all_cat_prices)),
            'max': round(max(all_cat_prices)),
            'count': total_cat_count
        }
    else:
        cat_stats[cat_name] = {'avg': 0, 'min': 0, 'max': 0, 'count': total_cat_count}

# --- Generate HTML ---
def fmt_price(p):
    if p == 0:
        return "Free"
    return f"${p:,.0f}"

def listing_row(l, show_badge=None, show_deal=False):
    badge = ''
    if show_badge == 'new':
        badge = '<span class="badge new">NEW</span>'
    elif show_badge == 'drop':
        badge = f'<span class="badge drop">↓{l.get("drop_pct",0)}%</span>'
    elif show_badge == 'stale':
        badge = f'<span class="badge stale">{l.get("days_on_market",0)}d</span>'
    elif show_badge == 'sold':
        badge = '<span class="badge sold">SOLD</span>'
    if show_deal and l.get('is_deal'):
        badge += '<span class="badge deal">DEAL</span>'
    price_html = fmt_price(l['price'])
    if 'old_price' in l:
        price_html = f'{fmt_price(l["price"])} <s class="old-price">{fmt_price(l["old_price"])}</s>'
    searches = ', '.join(l.get('search_terms', []))
    is_part = 'parts' if l.get('is_parts') else 'vehicle'
    dom = l.get('days_on_market', 0)
    dom_html = f'<span class="dom">{dom}d</span>' if dom > 0 else '<span class="dom">new</span>'
    img_url = l.get('image_url', '')
    thumb_html = ''
    if img_url:
        thumb_html = f'''<details class="thumb-toggle"><summary class="thumb-summary">&#128247;</summary><img class="thumb-img" loading="lazy" onerror="this.style.display=\'none\'" src="{img_url}"></details>'''
    return f'''<tr class="listing-row" data-search="{searches}" data-type="{is_part}" data-price="{l['price']}" data-title="{(l.get('title') or '').lower()}" data-location="{(l.get('location') or '').lower()}">
        <td>{badge} <a href="{l['url']}" target="_blank">{l['title'] or '(untitled)'}</a>{thumb_html}</td>
        <td class="price">{price_html}</td>
        <td>{l['location']}</td>
        <td>{dom_html}</td>
    </tr>'''

def section_table(items, badge_type=None, empty_msg="Nothing yet — check back tomorrow.", show_deal=False):
    if not items:
        return f'<p class="empty">{empty_msg}</p>'
    rows = '\n'.join(listing_row(l, badge_type, show_deal) for l in items)
    return f'''<table class="listing-table">
        <thead><tr><th>Listing</th><th>Price</th><th>Location</th><th>Age</th></tr></thead>
        <tbody>{rows}</tbody>
    </table>'''

is_day_one = len(prev_seen) == 0

html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FB Marketplace Scout — {today}</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0a0a; color: #e0e0e0; padding: 20px; max-width: 1200px; margin: 0 auto; }}
    h1 {{ font-size: 1.8em; margin-bottom: 4px; color: #fff; }}
    .subtitle {{ color: #888; font-size: 0.9em; margin-bottom: 20px; }}
    .filter-bar {{ background: #111; border: 1px solid #333; border-radius: 10px; padding: 14px 18px; margin-bottom: 24px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }}
    .filter-bar input[type="text"] {{ flex: 1; min-width: 200px; background: #1a1a1a; border: 1px solid #444; border-radius: 6px; padding: 8px 12px; color: #fff; font-size: 0.9em; outline: none; }}
    .filter-bar input[type="text"]:focus {{ border-color: #60a5fa; }}
    .filter-bar input[type="text"]::placeholder {{ color: #666; }}
    .filter-pills {{ display: flex; gap: 6px; flex-wrap: wrap; }}
    .pill {{ background: #1a1a1a; border: 1px solid #333; border-radius: 20px; padding: 5px 14px; font-size: 0.8em; color: #aaa; cursor: pointer; transition: all 0.15s; user-select: none; }}
    .pill:hover {{ border-color: #555; color: #fff; }}
    .pill.active {{ background: #1e3a5f; border-color: #60a5fa; color: #60a5fa; }}
    .filter-count {{ font-size: 0.8em; color: #666; min-width: 100px; text-align: right; }}
    .stats-bar {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
    .stat {{ background: #1a1a1a; border: 1px solid #333; border-radius: 8px; padding: 12px 18px; min-width: 110px; }}
    .stat .num {{ font-size: 1.6em; font-weight: 700; color: #fff; }}
    .stat .label {{ font-size: 0.75em; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }}
    .stat.new .num {{ color: #4ade80; }}
    .stat.drop .num {{ color: #f59e0b; }}
    .stat.stale .num {{ color: #ef4444; }}
    .stat.sold .num {{ color: #c084fc; }}
    .stat.clickable {{ cursor: pointer; transition: border-color 0.15s; }}
    .stat.clickable:hover {{ border-color: #555; }}
    .section {{ margin-bottom: 32px; }}
    .section > h2 {{ font-size: 1.2em; color: #fff; margin-bottom: 12px; padding-bottom: 6px; border-bottom: 1px solid #333; }}
    .section > h2.collapsible {{ cursor: pointer; }}
    .section > h2.collapsible:hover {{ color: #60a5fa; }}
    .section h2 .count {{ color: #666; font-weight: 400; font-size: 0.8em; }}
    .category {{ margin-bottom: 32px; border: 1px solid #222; border-radius: 10px; padding: 16px; background: #0d0d0d; }}
    .category > h3 {{ font-size: 1.1em; color: #fff; margin-bottom: 4px; }}
    .cat-stats {{ font-size: 0.8em; color: #666; margin-bottom: 12px; }}
    .search-group {{ margin-bottom: 20px; margin-left: 8px; }}
    .search-group h4 {{ font-size: 0.95em; color: #ccc; margin-bottom: 2px; cursor: pointer; }}
    .search-group h4:hover {{ color: #fff; }}
    .search-group h4 .st-count {{ color: #555; font-weight: 400; font-size: 0.85em; }}
    .search-group h4 .st-avg {{ color: #666; font-weight: 400; font-size: 0.8em; margin-left: 8px; }}
    .search-group h4 .arrow {{ display: inline-block; transition: transform 0.2s; margin-right: 4px; font-size: 0.8em; color: #555; }}
    .search-group h4 .arrow.open {{ transform: rotate(90deg); }}
    .parts-toggle {{ margin-top: 8px; }}
    .parts-toggle summary {{ font-size: 0.8em; color: #666; cursor: pointer; padding: 4px 0; }}
    .parts-toggle summary:hover {{ color: #aaa; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.85em; }}
    thead th {{ text-align: left; padding: 6px 10px; color: #888; font-weight: 500; font-size: 0.8em; text-transform: uppercase; border-bottom: 1px solid #333; }}
    tbody tr {{ border-bottom: 1px solid #1a1a1a; }}
    tbody tr:hover {{ background: #151515; }}
    tbody tr.hidden {{ display: none; }}
    td {{ padding: 8px 10px; vertical-align: top; }}
    td a {{ color: #60a5fa; text-decoration: none; }}
    td a:hover {{ text-decoration: underline; }}
    .price {{ font-weight: 600; white-space: nowrap; }}
    .old-price {{ color: #666; font-weight: 400; font-size: 0.85em; }}
    .dim {{ color: #555; font-size: 0.85em; }}
    .badge {{ display: inline-block; font-size: 0.7em; font-weight: 700; padding: 2px 6px; border-radius: 3px; margin-right: 4px; vertical-align: middle; }}
    .badge.new {{ background: #064e3b; color: #4ade80; }}
    .badge.drop {{ background: #451a03; color: #f59e0b; }}
    .badge.stale {{ background: #450a0a; color: #ef4444; }}
    .badge.deal {{ background: #1e1b4b; color: #a78bfa; }}
    .badge.sold {{ background: #3b0764; color: #c084fc; }}
    .dom {{ color: #555; font-size: 0.8em; white-space: nowrap; }}
    .empty {{ color: #555; font-style: italic; padding: 12px 0; }}
    .thumb-toggle {{ display: inline-block; margin-left: 6px; }}
    .thumb-summary {{ display: inline; cursor: pointer; font-size: 0.8em; color: #555; list-style: none; }}
    .thumb-summary::-webkit-details-marker {{ display: none; }}
    .thumb-summary:hover {{ color: #60a5fa; }}
    .thumb-img {{ display: block; margin-top: 6px; max-width: 180px; max-height: 140px; border-radius: 6px; border: 1px solid #333; object-fit: cover; }}
    .day-one-note {{ background: #1a1a2e; border: 1px solid #2a2a4e; border-radius: 8px; padding: 14px 18px; margin-bottom: 24px; color: #a0a0d0; font-size: 0.9em; }}
    @media (max-width: 768px) {{
        .stats-bar {{ gap: 8px; }}
        .stat {{ min-width: 90px; padding: 8px 12px; }}
        .filter-bar {{ padding: 10px; }}
        table {{ font-size: 0.8em; }}
        td, th {{ padding: 6px; }}
    }}
</style>
</head>
<body>
<h1>FB Marketplace Scout</h1>
<p class="subtitle">Phoenix metro, 250mi radius &middot; {today} &middot; {total_vehicles} vehicles + {total_parts} parts across 25 searches</p>

{"<div class='day-one-note'><strong>Day 1 baseline.</strong> All " + str(total_unique) + " listings are new today. Starting tomorrow, this report will highlight only new listings, price drops, and stale inventory.</div>" if is_day_one else ""}

<div class="filter-bar">
    <input type="text" id="searchBox" placeholder="Search listings by title, location..." oninput="filterAll()">
    <div class="filter-pills">
        <span class="pill active" data-filter="vehicles" onclick="togglePill(this)">Vehicles</span>
        <span class="pill" data-filter="parts" onclick="togglePill(this)">Parts</span>
        <span class="pill" data-filter="deals" onclick="togglePill(this)">Deals Only</span>
    </div>
    <span class="filter-count" id="filterCount">{total_vehicles} shown</span>
</div>

<div class="stats-bar">
    <div class="stat new clickable" onclick="scrollToSection('section-new')"><div class="num">{total_new}</div><div class="label">New Today</div></div>
    <div class="stat drop clickable" onclick="scrollToSection('section-drops')"><div class="num">{total_drops}</div><div class="label">Price Drops</div></div>
    <div class="stat stale clickable" onclick="scrollToSection('section-stale')"><div class="num">{total_stale}</div><div class="label">Stale (5d+)</div></div>
    <div class="stat sold clickable" onclick="scrollToSection('section-sold')"><div class="num">{len(sold_vehicles)}</div><div class="label">Sold</div></div>
    <div class="stat"><div class="num">{total_vehicles}</div><div class="label">Vehicles</div></div>
    <div class="stat"><div class="num">{total_parts}</div><div class="label">Parts</div></div>
</div>
'''

# New Today section
new_vehicles = [l for l in new_listings if not l.get('is_parts')] if not is_day_one else []
new_vehicles.sort(key=lambda x: (x['price'] == 0, x['price']))
html += f'''<div class="section" id="section-new">
<h2 class="collapsible" onclick="this.querySelector('.arrow').classList.toggle('open');this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'"><span class="arrow">&#9654;</span> New Today <span class="count">({len(new_vehicles)} vehicles)</span></h2>
<div style="display:none">
{section_table(new_vehicles, 'new', "Day 1 baseline — everything is new. Check back tomorrow for true new listings.", show_deal=True)}
</div>
</div>'''

# Price Drops section
price_drops.sort(key=lambda x: x.get('drop_pct', 0), reverse=True)
html += f'''<div class="section" id="section-drops">
<h2 class="collapsible" onclick="this.querySelector('.arrow').classList.toggle('open');this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'"><span class="arrow">&#9654;</span> Price Drops <span class="count">({total_drops})</span></h2>
<div style="display:none">
{section_table(price_drops, 'drop', "No price drops detected yet — tracking starts after day 1.")}
</div>
</div>'''

# Stale section
stale_vehicles = [l for l in stale_listings if not l.get('is_parts')]
stale_vehicles.sort(key=lambda x: x.get('days_on_market', 0), reverse=True)
html += f'''<div class="section" id="section-stale">
<h2 class="collapsible" onclick="this.querySelector('.arrow').classList.toggle('open');this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'"><span class="arrow">&#9654;</span> Getting Stale (5+ days) <span class="count">({len(stale_vehicles)})</span></h2>
<div style="display:none">
{section_table(stale_vehicles, 'stale', "No stale listings yet — needs 5+ days of tracking.")}
</div>
</div>'''

# Sold section
html += f'''<div class="section" id="section-sold">
<h2 class="collapsible" onclick="this.querySelector('.arrow').classList.toggle('open');this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'"><span class="arrow">&#9654;</span> Recently Sold <span class="count">({len(sold_vehicles)})</span></h2>
<div style="display:none">
{section_table(sold_vehicles, 'sold', "No sold listings detected yet — needs 2+ days of tracking.")}
</div>
</div>'''

# Full listings: Category > Search Term > Vehicles / Parts
html += '<div class="section"><h2>All Listings by Category</h2></div>'

for cat_name, search_terms in CATEGORIES.items():
    stats = cat_stats.get(cat_name, {})
    cat_vehicle_count = sum(len(category_data[cat_name][st]['vehicles']) for st in search_terms)
    cat_parts_count = sum(len(category_data[cat_name][st]['parts']) for st in search_terms)
    html += f'''<div class="category">
    <h3>{cat_name} <span class="count">({cat_vehicle_count} vehicles, {cat_parts_count} parts)</span></h3>
    <div class="cat-stats">Vehicle avg: {fmt_price(stats.get("avg",0))} &middot; Range: {fmt_price(stats.get("min",0))} – {fmt_price(stats.get("max",0))}</div>
    '''
    for st in search_terms:
        data = category_data[cat_name][st]
        vehs = data['vehicles']
        parts = data['parts']
        st_stats = search_stats.get(st, {})
        st_title = st.replace('_', ' ').title()
        html += f'''<div class="search-group">
        <h4 onclick="this.querySelector('.arrow').classList.toggle('open');this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'">
            <span class="arrow">&#9654;</span> {st_title}
            <span class="st-count">({len(vehs)} vehicles{", " + str(len(parts)) + " parts" if parts else ""})</span>
            <span class="st-avg">avg {fmt_price(st_stats.get("avg",0))}</span>
        </h4>
        <div class="search-group-body" style="display:none">
        '''
        if vehs:
            html += section_table(vehs, show_deal=True)
        else:
            html += '<p class="empty">No vehicle listings found.</p>'
        if parts:
            html += f'''<details class="parts-toggle">
            <summary>Parts &amp; Accessories ({len(parts)})</summary>
            {section_table(parts)}
            </details>'''
        html += '</div></div>'
    html += '</div>'

# JS for search/filter
html += '''
<script>
function scrollToSection(id) {
    var el = document.getElementById(id);
    if (!el) return;
    var h2 = el.querySelector('h2.collapsible');
    if (h2) {
        var body = h2.nextElementSibling;
        if (body && body.style.display === 'none') {
            body.style.display = 'block';
            var arrow = h2.querySelector('.arrow');
            if (arrow) arrow.classList.add('open');
        }
    }
    el.scrollIntoView({behavior: 'smooth', block: 'start'});
}
function togglePill(el) {
    el.classList.toggle('active');
    filterAll();
}
function filterAll() {
    var q = document.getElementById('searchBox').value.toLowerCase();
    var pills = document.querySelectorAll('.pill');
    var showVehicles = false, showParts = false, dealsOnly = false;
    pills.forEach(function(p) {
        if (p.classList.contains('active')) {
            if (p.dataset.filter === 'vehicles') showVehicles = true;
            if (p.dataset.filter === 'parts') showParts = true;
            if (p.dataset.filter === 'deals') dealsOnly = true;
        }
    });
    var rows = document.querySelectorAll('.listing-row');
    var count = 0;
    rows.forEach(function(r) {
        var type = r.dataset.type;
        var title = r.dataset.title || '';
        var loc = r.dataset.location || '';
        var search = r.dataset.search || '';
        var noTypeFilter = !showVehicles && !showParts;
        var typeMatch = noTypeFilter || (type === 'vehicle' && showVehicles) || (type === 'parts' && showParts);
        var textMatch = !q || title.indexOf(q) !== -1 || loc.indexOf(q) !== -1 || search.indexOf(q) !== -1;
        var dealMatch = !dealsOnly || r.innerHTML.indexOf('badge deal') !== -1;
        if (typeMatch && textMatch && dealMatch) {
            r.classList.remove('hidden');
            count++;
        } else {
            r.classList.add('hidden');
        }
    });
    document.getElementById('filterCount').textContent = count + ' shown';
}
filterAll();
</script>

<p class="dim" style="margin-top: 40px; text-align: center; font-size: 0.75em;">
    Generated by FB Marketplace Scout &middot; Data scraped from Facebook Marketplace
</p>
</body>
</html>'''

# Write output
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
with open(OUTPUT_FILE, 'w') as f:
    f.write(html)

print(f"Report generated: {OUTPUT_FILE}")
print(f"Total unique listings: {total_unique}")
print(f"New today: {total_new}")
print(f"Price drops: {total_drops}")
print(f"Stale: {total_stale}")
print(f"Day 1: {is_day_one}")
print(f"Seen file updated: {SEEN_FILE} ({len(new_seen)} entries)")
for cat, stats in cat_stats.items():
    print(f"  {cat}: {stats['count']} listings, avg {fmt_price(stats['avg'])}")
