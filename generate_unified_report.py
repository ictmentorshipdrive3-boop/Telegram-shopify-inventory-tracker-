import csv
import json
import os
import re
import base64
import requests
import datetime

from concurrent.futures import ThreadPoolExecutor

image_b64_cache = {}
dynamic_url_cache = {}

def resolve_image_url_smart(store_name, store_domain, product_title, product_url, cache_dict):
    if not product_url:
        return ""
        
    key_combo = (store_name, product_title, product_url)
    if key_combo in dynamic_url_cache:
        return dynamic_url_cache[key_combo]

    # Stage 1: Exact Variant ID Match
    match = re.search(r'variant=(gid://shopify/ProductVariant/\d+|\d+)', product_url)
    if match:
        m_str = match.group(1)
        v_gid = m_str if m_str.startswith('gid://') else f"gid://shopify/ProductVariant/{m_str}"
        if v_gid in cache_dict and isinstance(cache_dict[v_gid], dict) and cache_dict[v_gid].get('image_url'):
            img = cache_dict[v_gid]['image_url']
            dynamic_url_cache[key_combo] = img
            return img

    # Stage 2: Numeric Variant ID Substring Match
    if match:
        numeric_id = m_str.replace('gid://shopify/ProductVariant/', '')
        for c_key, c_val in cache_dict.items():
            if numeric_id in c_key and isinstance(c_val, dict) and c_val.get('image_url'):
                img = c_val['image_url']
                dynamic_url_cache[key_combo] = img
                return img

    # Stage 3: Product Handle Match
    handle_match = re.search(r'/products/([^/?#]+)', product_url)
    if handle_match:
        handle = handle_match.group(1).lower()
        for c_key, c_val in cache_dict.items():
            if isinstance(c_val, dict):
                c_url = c_val.get('url', '').lower()
                c_title = c_val.get('title', '').lower()
                if (handle in c_url or handle in c_title) and c_val.get('image_url'):
                    img = c_val['image_url']
                    dynamic_url_cache[key_combo] = img
                    return img

    # Stage 4: Title Match
    title_clean = product_title.strip().lower()
    for c_key, c_val in cache_dict.items():
        if isinstance(c_val, dict) and c_val.get('title', '').strip().lower() == title_clean and c_val.get('image_url'):
            img = c_val['image_url']
            dynamic_url_cache[key_combo] = img
            return img

    # Stage 5: Live Shopify Product JSON Fetch
    if handle_match and store_domain:
        json_url = f"https://{store_domain}/products/{handle_match.group(1)}.json"
        try:
            r = requests.get(json_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
            if r.status_code == 200:
                p_data = r.json().get('product', {})
                imgs = p_data.get('images', [])
                if imgs and imgs[0].get('src'):
                    img_src = imgs[0]['src']
                    dynamic_url_cache[key_combo] = img_src
                    return img_src
        except Exception:
            pass

    return ""

def fetch_single_image(url):
    if not url or url in image_b64_cache:
        return
    try:
        sep = '&' if '?' in url else '?'
        optimized_url = f"{url}{sep}format=jpg&width=150"
        r = requests.get(optimized_url, timeout=5)
        if r.status_code == 200:
            b64_str = base64.b64encode(r.content).decode('utf-8')
            image_b64_cache[url] = f"data:image/jpeg;base64,{b64_str}"
    except Exception:
        pass

def preload_images(urls):
    unique_urls = list(set([u for u in urls if u and u not in image_b64_cache]))
    if unique_urls:
        print(f"Parallel downloading and base64 encoding {len(unique_urls)} images...")
        with ThreadPoolExecutor(max_workers=25) as executor:
            executor.map(fetch_single_image, unique_urls)

def get_base64_image(url):
    if not url:
        return 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100"><rect width="100%" height="100%" fill="%231a1222"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="%239c91a4" font-size="12">No Photo</text></svg>'
    return image_b64_cache.get(url, url)

def resolve_repo_dir():
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "shopify-inventory-tracker-github"),
        os.path.dirname(os.path.abspath(__file__)),
        r"C:\Users\AMD\Downloads\shopify-inventory-tracker-github",
        os.path.join(os.path.expanduser("~"), "Downloads", "shopify-inventory-tracker-github")
    ]
    for c in candidates:
        if os.path.exists(c) and os.path.exists(os.path.join(c, "theamethyststore_com_live_sales_log.csv")):
            return c
    return candidates[0]

def resolve_output_dir():
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports"),
        r"C:\Users\AMD\Downloads",
        os.path.join(os.path.expanduser("~"), "Downloads")
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    os.makedirs(candidates[0], exist_ok=True)
    return candidates[0]

def generate_unified_report(target_date_str=None):
    repo_dir = resolve_repo_dir()
    out_dir = resolve_output_dir()
    
    # Get current time in IST (UTC + 5:30)
    now_utc = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    now_ist = now_utc + datetime.timedelta(hours=5, minutes=30)
    
    is_24h = (target_date_str == "24h")
    
    if is_24h:
        title_date = f"Last 24 Hours (As of {now_ist.strftime('%A, %b %d, %Y %I:%M %p')} IST)"
        output_html = os.path.join(out_dir, "multi_store_sales_report_24h.html")
        cutoff_ist = now_ist - datetime.timedelta(hours=24)
    else:
        if target_date_str is None:
            today_ist = now_ist.date()
        else:
            today_ist = datetime.datetime.strptime(target_date_str, '%Y-%m-%d').date()
            
        title_date = today_ist.strftime('%A, %B %d, %Y (IST)')
        output_html = os.path.join(out_dir, f"multi_store_sales_report_{today_ist.strftime('%Y%m%d')}.html")
        
    stores_config = {
        'kanshijewels_com': {
            'name': 'Kanshi Jewels',
            'domain': 'kanshijewels.com',
            'log': 'kanshijewels_com_live_sales_log.csv',
            'cache': 'kanshijewels_com_live_cache.json'
        },
        'theamethyststore_com': {
            'name': 'The Amethyst Store',
            'domain': 'theamethyststore.com',
            'log': 'theamethyststore_com_live_sales_log.csv',
            'cache': 'theamethyststore_com_live_cache.json'
        },
        'dulhanjewels_com': {
            'name': 'Dulhan Jewels',
            'domain': 'dulhanjewels.com',
            'log': 'dulhanjewels_com_live_sales_log.csv',
            'cache': 'dulhanjewels_com_live_cache.json'
        },
        'rasasilver_com': {
            'name': 'Rasa Silver',
            'domain': 'rasasilver.com',
            'log': 'rasasilver_com_live_sales_log.csv',
            'cache': 'rasasilver_com_live_cache.json'
        },
        'muskanjewel_com': {
            'name': 'Muskan Jewel',
            'domain': 'muskanjewel.com',
            'log': 'muskanjewel_com_live_sales_log.csv',
            'cache': 'muskanjewel_com_live_cache.json'
        },
        'daivik_in': {
            'name': 'Daivik Jewels',
            'domain': 'daivik.in',
            'log': 'daivik_in_live_sales_log.csv',
            'cache': 'daivik_in_live_cache.json'
        }
    }
    
    combined_data = {}
    total_network_revenue = 0.0
    total_network_qty = 0
    total_network_sold_out = 0
    total_network_restocked = 0
    total_network_new_arrivals = 0
    
    all_sold_out_feed = []
    all_restocked_feed = []
    all_new_arrival_feed = []
    
    for key, cfg in stores_config.items():
        log_path = os.path.join(repo_dir, cfg['log'])
        cache_path = os.path.join(repo_dir, cfg['cache'])
        
        if not os.path.exists(log_path) or not os.path.exists(cache_path):
            continue
            
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache = json.load(f)
            
        sales = []
        sold_out = []
        restocked_items = []
        new_arrival_items = []
        store_revenue = 0.0
        store_qty = 0
        store_restocked = 0
        store_new_arrivals = 0
        
        # Read log file raw data and convert UTC to IST
        raw_rows = []
        with open(log_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                title_lower = row.get('Product Title', '').lower()
                sku_lower = row.get('SKU', '').lower()
                try:
                    qty_val = int(row.get('Quantity', 1))
                except (ValueError, TypeError):
                    qty_val = 1
                
                if 'test' in title_lower or 'test' in sku_lower or qty_val >= 1000:
                    continue

                try:
                    dt_utc = datetime.datetime.strptime(row['Timestamp'], "%Y-%m-%d %H:%M:%S")
                except Exception:
                    continue
                
                # Convert to IST (UTC + 5:30)
                dt_ist = dt_utc + datetime.timedelta(hours=5, minutes=30)
                
                # Filter based on 24h rolling or specific IST date
                if is_24h:
                    if dt_ist >= cutoff_ist:
                        raw_rows.append((row, dt_ist))
                else:
                    if dt_ist.date() == today_ist:
                        raw_rows.append((row, dt_ist))
                        
        # Pre-pass reconciliation: filter out catalog flickers (false disappearances/reappearances)
        flicker_indices = set()
        sales_indices = []
        restock_indices = []

        for idx, (row, dt_ist) in enumerate(raw_rows):
            evt = row['Event Type']
            key_item = (row.get('Product Title', '').strip(), row.get('Variant Title', '').strip())
            if evt in ['Sale', 'Sold Out']:
                sales_indices.append((idx, dt_ist, key_item))
            elif evt in ['Restock', 'New Arrival']:
                restock_indices.append((idx, dt_ist, key_item))

        for s_idx, s_dt, s_key in sales_indices:
            for r_idx, r_dt, r_key in restock_indices:
                if r_idx not in flicker_indices and s_key == r_key and r_dt >= s_dt:
                    diff_mins = (r_dt - s_dt).total_seconds() / 60.0
                    if diff_mins <= 30.0:
                        flicker_indices.add(s_idx)
                        flicker_indices.add(r_idx)
                        break

        reconciled_raw_rows = [item for idx, item in enumerate(raw_rows) if idx not in flicker_indices]
                    
        # Process rows and optimize CDN URLs
        for row, dt_ist in reconciled_raw_rows:
            evt = row['Event Type']
            url = row['Product URL']
            image_url = resolve_image_url_smart(key, cfg.get('domain', ''), row['Product Title'], url, cache)
            price = float(row['Price'])
            qty = int(row['Quantity'])
            
            item_data = {
                'dt_ist': dt_ist,
                'timestamp': dt_ist.strftime('%I:%M %p'), # 12-hour format with AM/PM for IST
                'title': row['Product Title'],
                'variant': row['Variant Title'],
                'sku': row['SKU'] or 'N/A',
                'price': price,
                'qty': qty,
                'event': evt,
                'old': int(row['Previous Stock']),
                'new': int(row['Current Stock']),
                'url': url,
                'image': image_url
            }
            
            sales.append(item_data)
            
            if evt in ['Sale', 'Sold Out']:
                if evt == 'Sold Out' or item_data['new'] == 0:
                    sold_out.append(item_data)
                    all_sold_out_feed.append({
                        'store': cfg['name'],
                        'title': item_data['title'],
                        'image': item_data['image'],
                        'price': item_data['price'],
                        'sku': item_data['sku'],
                        'url': item_data['url'],
                        'dt_ist': dt_ist,
                        'timestamp': item_data['timestamp']
                    })
                store_revenue += price * qty
                store_qty += qty
            elif evt == 'Restock':
                restocked_items.append(item_data)
                all_restocked_feed.append({
                    'store': cfg['name'],
                    'title': item_data['title'],
                    'image': item_data['image'],
                    'price': item_data['price'],
                    'sku': item_data['sku'],
                    'url': item_data['url'],
                    'qty': qty,
                    'old': item_data['old'],
                    'new': item_data['new'],
                    'dt_ist': dt_ist,
                    'timestamp': item_data['timestamp']
                })
                store_restocked += qty
            elif evt == 'New Arrival':
                new_arrival_items.append(item_data)
                all_new_arrival_feed.append({
                    'store': cfg['name'],
                    'title': item_data['title'],
                    'image': item_data['image'],
                    'price': item_data['price'],
                    'sku': item_data['sku'],
                    'url': item_data['url'],
                    'qty': qty,
                    'dt_ist': dt_ist,
                    'timestamp': item_data['timestamp']
                })
                store_new_arrivals += qty
                    
        if sales:
            # Sort with Sold Out items FIRST, followed by Sales, Restocks, New Arrivals (newest timestamp first within each category)
            def item_sort_key(x):
                evt = x['event']
                evt_order = 0 if evt == 'Sold Out' else (1 if evt == 'Sale' else (2 if evt == 'Restock' else 3))
                return (evt_order, -x['dt_ist'].timestamp())
                
            sales.sort(key=item_sort_key)
            combined_data[key] = {
                'name': cfg['name'],
                'sales': sales,
                'sold_out': sold_out,
                'restocked_items': restocked_items,
                'new_arrival_items': new_arrival_items,
                'revenue': store_revenue,
                'qty': store_qty,
                'restocked': store_restocked,
                'new_arrivals': store_new_arrivals
            }
            
            total_network_revenue += store_revenue
            total_network_qty += store_qty
            total_network_sold_out += len(sold_out)
            total_network_restocked += store_restocked
            total_network_new_arrivals += store_new_arrivals

    # Sort photo feeds by newest timestamp first
    all_sold_out_feed.sort(key=lambda x: x.get('dt_ist', datetime.datetime.min), reverse=True)
    all_restocked_feed.sort(key=lambda x: x.get('dt_ist', datetime.datetime.min), reverse=True)
    all_new_arrival_feed.sort(key=lambda x: x.get('dt_ist', datetime.datetime.min), reverse=True)

    # Preload images in parallel
    all_img_urls = []
    for s_data in combined_data.values():
        for item in s_data['sales']:
            if item.get('image'):
                all_img_urls.append(item['image'])
    for item in all_sold_out_feed:
        if item.get('image'): all_img_urls.append(item['image'])
    for item in all_restocked_feed:
        if item.get('image'): all_img_urls.append(item['image'])
    for item in all_new_arrival_feed:
        if item.get('image'): all_img_urls.append(item['image'])

    preload_images(all_img_urls)

    # Convert image URLs to embedded Base64 data URIs
    for s_data in combined_data.values():
        for item in s_data['sales']:
            if item.get('image'):
                item['image'] = get_base64_image(item['image'])
        for item in s_data['sold_out']:
            if item.get('image'):
                item['image'] = get_base64_image(item['image'])
        for item in s_data['restocked_items']:
            if item.get('image'):
                item['image'] = get_base64_image(item['image'])
        for item in s_data['new_arrival_items']:
            if item.get('image'):
                item['image'] = get_base64_image(item['image'])

    for item in all_sold_out_feed:
        if item.get('image'): item['image'] = get_base64_image(item['image'])
    for item in all_restocked_feed:
        if item.get('image'): item['image'] = get_base64_image(item['image'])
    for item in all_new_arrival_feed:
        if item.get('image'): item['image'] = get_base64_image(item['image'])

    # Pre-generate CSS-only selections for all stores (5 Filter Tabs per store)
    css_filtering_rules = ""
    radio_triggers_html = ""
    for key in combined_data.keys():
        radio_triggers_html += f"""
        <input type="radio" name="filter-{key}" id="filter-all-{key}" class="filter-radio" checked>
        <input type="radio" name="filter-{key}" id="filter-sales-{key}" class="filter-radio">
        <input type="radio" name="filter-{key}" id="filter-soldout-{key}" class="filter-radio">
        <input type="radio" name="filter-{key}" id="filter-restock-{key}" class="filter-radio">
        <input type="radio" name="filter-{key}" id="filter-newarrival-{key}" class="filter-radio">
        """
        css_filtering_rules += f"""
        #filter-all-{key}:checked ~ .container #sec-{key} .filter-group .all-btn,
        #filter-sales-{key}:checked ~ .container #sec-{key} .filter-group .sales-btn,
        #filter-soldout-{key}:checked ~ .container #sec-{key} .filter-group .soldout-btn,
        #filter-restock-{key}:checked ~ .container #sec-{key} .filter-group .restock-btn,
        #filter-newarrival-{key}:checked ~ .container #sec-{key} .filter-group .newarrival-btn {{
            background-color: var(--tab-active-bg);
            color: var(--primary);
            border-color: var(--primary);
        }}
        
        #filter-sales-{key}:checked ~ .container #sec-{key} table tbody tr:not([data-category="sale"]),
        #filter-sales-{key}:checked ~ .container #sec-{key} .mobile-only-cards .mobile-card:not([data-category="sale"]) {{
            display: none !important;
        }}
        
        #filter-soldout-{key}:checked ~ .container #sec-{key} table tbody tr:not([data-category="sold-out"]),
        #filter-soldout-{key}:checked ~ .container #sec-{key} .mobile-only-cards .mobile-card:not([data-category="sold-out"]) {{
            display: none !important;
        }}
        
        #filter-restock-{key}:checked ~ .container #sec-{key} table tbody tr:not([data-category="restock"]),
        #filter-restock-{key}:checked ~ .container #sec-{key} .mobile-only-cards .mobile-card:not([data-category="restock"]) {{
            display: none !important;
        }}
        
        #filter-newarrival-{key}:checked ~ .container #sec-{key} table tbody tr:not([data-category="new-arrival"]),
        #filter-newarrival-{key}:checked ~ .container #sec-{key} .mobile-only-cards .mobile-card:not([data-category="new-arrival"]) {{
            display: none !important;
        }}
        """

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="referrer" content="no-referrer">
    <title>Multi-Store Network Operations & Sales Dashboard ({title_date})</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #0b070f;
            --card-bg: #140d1a;
            --primary: #c9ab81;
            --accent: #dfc29a;
            --text: #f3eff7;
            --text-muted: #9c91a4;
            --border: #291d30;
            --danger: #ff5a5f;
            --success: #06d6a0;
            --info: #00b4d8;
            --purple: #9b5de5;
            --tab-active-bg: #22172b;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Outfit', sans-serif;
        }}
        
        body {{
            background-color: var(--bg-color);
            color: var(--text);
            padding: 0.8rem 0.4rem;
            min-height: 100vh;
        }}
        
        @media(min-width: 768px) {{
            body {{
                padding: 1.5rem 1rem;
            }}
        }}
        
        .container {{
            max-width: 1280px;
            margin: 0 auto;
        }}
        
        header {{
            display: flex;
            flex-direction: column;
            gap: 0.8rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 1.2rem;
            margin-bottom: 1.2rem;
        }}
        
        @media(min-width: 768px) {{
            header {{
                flex-direction: row;
                justify-content: space-between;
                align-items: center;
                padding-bottom: 1.5rem;
                margin-bottom: 2rem;
            }}
        }}
        
        .logo-section h1 {{
            font-size: 1.8rem;
            font-weight: 700;
            color: var(--primary);
            text-transform: uppercase;
            letter-spacing: -0.5px;
        }}
        
        .logo-section p {{
            color: var(--text-muted);
            font-size: 0.85rem;
            margin-top: 0.2rem;
        }}
        
        .date-badge {{
            align-self: flex-start;
            background: linear-gradient(135deg, var(--primary), var(--accent));
            color: #120917;
            font-weight: 600;
            padding: 0.4rem 0.8rem;
            border-radius: 50px;
            font-size: 0.8rem;
        }}
        
        @media(min-width: 768px) {{
            .date-badge {{
                align-self: auto;
                font-size: 0.95rem;
                padding: 0.6rem 1.2rem;
            }}
        }}
        
        /* Navigation Links */
        .navigation-grid {{
            display: flex;
            gap: 0.4rem;
            margin-bottom: 1.5rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 0.8rem;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }}
        
        .nav-link {{
            background-color: var(--card-bg);
            border: 1px solid var(--border);
            color: var(--text-muted);
            text-decoration: none;
            padding: 0.5rem 0.9rem;
            font-size: 0.85rem;
            font-weight: 500;
            border-radius: 8px;
            white-space: nowrap;
            transition: all 0.2s;
        }}
        
        .nav-link:hover, .nav-link.active-indicator {{
            color: var(--primary);
            border-color: var(--primary);
            background-color: var(--tab-active-bg);
        }}
        
        .section-separator {{
            height: 1px;
            background-color: var(--border);
            margin: 2.5rem 0;
            position: relative;
        }}
        
        .section-separator::after {{
            content: "✦ ✦ ✦";
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background-color: var(--bg-color);
            padding: 0 1rem;
            color: var(--primary);
            font-size: 0.8rem;
            letter-spacing: 4px;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 0.8rem;
            margin-bottom: 1.5rem;
        }}
        
        .stat-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1rem;
        }}
        
        .stat-card h3 {{
            color: var(--text-muted);
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 0.4rem;
        }}
        
        .stat-card .val {{
            font-size: 1.5rem;
            font-weight: 700;
        }}
        
        .stat-card .val.gold {{
            color: var(--primary);
        }}
        
        .store-performance-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.8rem 0;
            border-bottom: 1px solid var(--border);
        }}
        
        .store-performance-row:last-child {{
            border-bottom: none;
        }}
        
        .store-perf-info h4 a {{
            color: var(--text);
            text-decoration: none;
            font-weight: 600;
            font-size: 0.95rem;
        }}
        
        .store-perf-info h4 a:hover {{
            color: var(--primary);
        }}
        
        .store-perf-info p {{
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 0.1rem;
        }}
        
        .store-perf-revenue {{
            text-align: right;
            font-weight: 700;
            color: var(--primary);
            font-size: 1rem;
        }}
        
        .sold-out-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
            gap: 0.8rem;
            margin-bottom: 1.2rem;
        }}
        
        .sold-out-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 0.8rem;
            display: flex;
            align-items: center;
            gap: 0.8rem;
            position: relative;
        }}
        
        .sold-out-card img {{
            width: 65px;
            height: 65px;
            object-fit: cover;
            border-radius: 8px;
            border: 1px solid var(--border);
            flex-shrink: 0;
        }}
        
        .sold-out-info {{
            flex-grow: 1;
            overflow: hidden;
        }}
        
        .sold-out-info h4 {{
            font-size: 0.85rem;
            font-weight: 600;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        
        .sold-out-info p {{
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 0.1rem;
        }}
        
        .sold-out-info .price {{
            color: var(--primary);
            font-weight: 600;
            margin-top: 0.15rem;
            font-size: 0.8rem;
        }}
        
        .store-badge {{
            position: absolute;
            top: 0.4rem;
            right: 0.4rem;
            background-color: var(--border);
            color: var(--primary);
            font-size: 0.6rem;
            font-weight: 600;
            padding: 0.15rem 0.4rem;
            border-radius: 4px;
        }}
        
        .panel {{
            background-color: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 1rem;
            overflow: hidden;
        }}
        
        .panel-title {{
            font-size: 1.1rem;
            font-weight: 600;
            margin-bottom: 1rem;
        }}
        
        .table-header {{
            display: flex;
            flex-direction: column;
            gap: 0.8rem;
            margin-bottom: 1rem;
        }}
        
        @media(min-width: 768px) {{
            .table-header {{
                flex-direction: row;
                justify-content: space-between;
                align-items: center;
            }}
        }}
        
        .filter-radio {{
            display: none !important;
        }}
        
        .filter-group {{
            display: flex;
            background-color: var(--bg-color);
            border: 1px solid var(--border);
            padding: 0.2rem;
            border-radius: 8px;
            gap: 0.2rem;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }}
        
        .filter-label {{
            padding: 0.4rem 0.8rem;
            font-size: 0.8rem;
            font-weight: 500;
            color: var(--text-muted);
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.15s;
            white-space: nowrap;
            border: 1px solid transparent;
        }}
        
        .filter-label:hover {{
            color: var(--text);
        }}
        
        .search-bar {{
            background-color: var(--bg-color);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 0.5rem 0.8rem;
            color: var(--text);
            font-size: 0.85rem;
            width: 100%;
            outline: none;
        }}
        
        @media(min-width: 768px) {{
            .search-bar {{
                width: 240px;
            }}
        }}
        
        .search-bar:focus {{
            border-color: var(--primary);
        }}
        
        .desktop-only-table {{
            display: none;
            width: 100%;
            border-collapse: collapse;
        }}
        
        @media(min-width: 768px) {{
            .desktop-only-table {{
                display: table;
            }}
        }}
        
        th {{
            text-align: left;
            padding: 0.7rem;
            color: var(--text-muted);
            font-weight: 500;
            font-size: 0.8rem;
            border-bottom: 1px solid var(--border);
        }}
        
        td {{
            padding: 0.7rem;
            border-bottom: 1px solid var(--border);
            vertical-align: middle;
            font-size: 0.85rem;
        }}
        
        tr:hover td {{
            background-color: rgba(201, 171, 129, 0.01);
        }}
        
        .product-cell {{
            display: flex;
            align-items: center;
            gap: 0.8rem;
        }}
        
        .product-cell img {{
            width: 75px;
            height: 75px;
            object-fit: cover;
            border-radius: 8px;
            border: 1px solid var(--border);
            flex-shrink: 0;
        }}
        
        .product-details a {{
            color: var(--text);
            text-decoration: none;
            font-weight: 500;
            font-size: 0.95rem;
        }}
        
        .product-details a:hover {{
            color: var(--primary);
        }}
        
        .product-details span {{
            display: block;
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 0.2rem;
        }}
        
        .event-badge {{
            display: inline-block;
            font-size: 0.7rem;
            font-weight: 600;
            padding: 0.2rem 0.4rem;
            border-radius: 4px;
            text-transform: uppercase;
        }}
        
        .event-badge.sale {{
            background-color: rgba(6, 214, 160, 0.15);
            color: var(--success);
        }}
        
        .event-badge.restock {{
            background-color: rgba(201, 171, 129, 0.15);
            color: var(--primary);
        }}
        
        .event-badge.new-arrival {{
            background-color: rgba(59, 130, 246, 0.15);
            color: #3b82f6;
        }}
        
        .event-badge.sold-out {{
            background-color: rgba(255, 90, 95, 0.15);
            color: var(--danger);
        }}
        
        .timestamp {{
            font-size: 0.8rem;
            color: var(--text-muted);
        }}
        
        .price-col {{
            font-weight: 600;
            color: var(--primary);
        }}
        
        /* Mobile View Pinterest/Instagram 1:1 Aspect Ratio Cards */
        .mobile-only-cards {{
            display: flex;
            flex-direction: column;
            gap: 1.2rem;
        }}
        
        @media(min-width: 768px) {{
            .mobile-only-cards {{
                display: none;
            }}
        }}
        
        .mobile-card {{
            background-color: var(--bg-color);
            border: 1px solid var(--border);
            border-radius: 14px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            width: 100%;
        }}
        
        .mobile-card-image-wrapper {{
            position: relative;
            width: 100%;
            padding-top: 100%;
            background-color: #100a16;
            border-bottom: 1px solid var(--border);
        }}
        
        .mobile-card-image-wrapper img {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
        
        .mobile-card-body {{
            padding: 1rem;
            display: flex;
            flex-direction: column;
            gap: 0.8rem;
        }}
        
        .mobile-card-details h4 {{
            font-size: 0.95rem;
            font-weight: 600;
            line-height: 1.3;
            margin-bottom: 0.2rem;
        }}
        
        .mobile-card-details span {{
            display: block;
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 0.1rem;
        }}
        
        .mobile-card-stats {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-top: 1px solid var(--border);
            padding-top: 0.6rem;
            margin-top: 0.1rem;
        }}
        
        .mobile-card-price {{
            font-size: 1rem;
            font-weight: 700;
            color: var(--primary);
        }}
        
        .store-header-title {{
            font-size: 1.3rem;
            font-weight: 700;
            color: var(--primary);
            border-left: 4px solid var(--primary);
            padding-left: 0.6rem;
            margin-bottom: 1.2rem;
        }}
        
        {css_filtering_rules}
    </style>
</head>
<body>
    <!-- Hidden Radio Triggers Placed at TOP of Body for 100% Mobile CSS Tab Compatibility -->
    {radio_triggers_html}

    <div class="container" id="top">
        <header>
            <div class="logo-section">
                <h1>Network Operations</h1>
                <p>Consolidated Daily Sales & Operations Dashboard (IST)</p>
            </div>
            <div class="date-badge">🗓️ {title_date}</div>
        </header>
        
        <!-- Zero-JS Navigation Grid -->
        <div class="navigation-grid">
            <a href="#top" class="nav-link active-indicator">🌎 Overview</a>
            {"".join([f'''
            <a href="#sec-{key}" class="nav-link">🏬 {cfg['name']}</a>
            ''' for key, cfg in combined_data.items()])}
        </div>
        
        <!-- OVERVIEW TAB -->
        <div id="overview" style="margin-bottom: 2.5rem;">
            <div class="stats-grid">
                <div class="stat-card">
                    <h3>Network Revenue</h3>
                    <div class="val gold">₹{total_network_revenue:,.2f}</div>
                </div>
                <div class="stat-card">
                    <h3>Units Sold</h3>
                    <div class="val">{total_network_qty}</div>
                </div>
                <div class="stat-card">
                    <h3>Sold-Out Items</h3>
                    <div class="val" style="color: var(--danger);">{total_network_sold_out}</div>
                </div>
                <div class="stat-card">
                    <h3>Units Restocked</h3>
                    <div class="val" style="color: var(--info);">{total_network_restocked}</div>
                </div>
                <div class="stat-card">
                    <h3>New Arrivals</h3>
                    <div class="val" style="color: var(--purple);">{total_network_new_arrivals}</div>
                </div>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr; gap: 1.5rem;">
                <div class="panel">
                    <div class="panel-title">🏬 Store Performance Breakdown</div>
                    {"".join([f'''
                    <div class="store-performance-row">
                        <div class="store-perf-info">
                            <h4><a href="#sec-{key}" style="color: var(--text); text-decoration: none;">{store['name']}</a></h4>
                            <p>{store['qty']} sold | {store['restocked']} restocked | {store['new_arrivals']} new</p>
                        </div>
                        <div class="store-perf-revenue">₹{store['revenue']:,.2f}</div>
                    </div>
                    ''' for key, store in combined_data.items()])}
                </div>
                
                {f'''<div class="panel">
                    <div class="panel-title">🚨 Recent Network Sold-Outs</div>
                    <div class="sold-out-grid">''' + "".join([f'''
                        <div class="sold-out-card">
                            <img src="{item['image']}" alt="{item['title']}">
                            <div class="sold-out-info">
                                <h4>{item['title']}</h4>
                                <span style="font-size: 0.75rem; color: var(--primary); font-weight: 500; display: block; margin-top: 0.15rem;">{item['store']}</span>
                                <div class="price">₹{item['price']:,.2f}</div>
                            </div>
                            <div class="store-badge" style="background-color: rgba(255, 90, 95, 0.2); color: var(--danger);">Sold Out</div>
                        </div>
                    ''' for item in all_sold_out_feed]) + f'''
                    </div>
                </div>''' if all_sold_out_feed else ''}
                
                {f'''<div class="panel">
                    <div class="panel-title">📦 Recent Network Restocks</div>
                    <div class="sold-out-grid">''' + "".join([f'''
                        <div class="sold-out-card">
                            <img src="{item['image']}" alt="{item['title']}">
                            <div class="sold-out-info">
                                <h4>{item['title']}</h4>
                                <span style="font-size: 0.75rem; color: var(--primary); font-weight: 500; display: block; margin-top: 0.15rem;">{item['store']}</span>
                                <div class="price">₹{item['price']:,.2f} (Restocked: +{item['qty']})</div>
                            </div>
                            <div class="store-badge" style="background-color: rgba(0, 180, 216, 0.2); color: var(--info);">Restocked</div>
                        </div>
                    ''' for item in all_restocked_feed]) + f'''
                    </div>
                </div>''' if all_restocked_feed else ''}

                {f'''<div class="panel">
                    <div class="panel-title">✨ Recent Network New Arrivals</div>
                    <div class="sold-out-grid">''' + "".join([f'''
                        <div class="sold-out-card">
                            <img src="{item['image']}" alt="{item['title']}">
                            <div class="sold-out-info">
                                <h4>{item['title']}</h4>
                                <span style="font-size: 0.75rem; color: var(--primary); font-weight: 500; display: block; margin-top: 0.15rem;">{item['store']}</span>
                                <div class="price">₹{item['price']:,.2f}</div>
                            </div>
                            <div class="store-badge" style="background-color: rgba(155, 93, 229, 0.2); color: var(--purple);">New Arrival</div>
                        </div>
                    ''' for item in all_new_arrival_feed]) + f'''
                    </div>
                </div>''' if all_new_arrival_feed else ''}
            </div>
        </div>
        
        <!-- INDIVIDUAL STORE SECTIONS -->
        {"".join([f'''
        <div class="section-separator"></div>
        
        <div id="sec-{key}">
            <h2 class="store-header-title">🏬 {store['name']} Performance</h2>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <h3>Store Revenue</h3>
                    <div class="val gold">₹{store['revenue']:,.2f}</div>
                </div>
                <div class="stat-card">
                    <h3>Units Sold</h3>
                    <div class="val">{store['qty']}</div>
                </div>
                <div class="stat-card">
                    <h3>Sold Out Items</h3>
                    <div class="val" style="color: var(--danger);">{len(store['sold_out'])}</div>
                </div>
                <div class="stat-card">
                    <h3>Restocked Items</h3>
                    <div class="val" style="color: var(--info);">{store['restocked']}</div>
                </div>
                <div class="stat-card">
                    <h3>New Arrivals</h3>
                    <div class="val" style="color: var(--purple);">{store['new_arrivals']}</div>
                </div>
            </div>
            
            {f'''<div style="margin-bottom: 1.5rem;">
                <div class="panel-title" style="margin-bottom: 0.8rem;">🚨 Sold Out Items ({len(store['sold_out'])})</div>
                <div class="sold-out-grid">''' + "".join([f'''
                    <div class="sold-out-card">
                        <img src="{item['image']}" alt="{item['title']}">
                        <div class="sold-out-info">
                            <h4>{item['title']}</h4>
                            <p>SKU: {item['sku']}</p>
                            <div class="price">₹{item['price']:,.2f}</div>
                        </div>
                        <div class="store-badge" style="background-color: rgba(255, 90, 95, 0.2); color: var(--danger);">Sold Out</div>
                    </div>
                ''' for item in store['sold_out']]) + f'''
                </div>
            </div>''' if store['sold_out'] else ''}
            
            {f'''<div style="margin-bottom: 1.5rem;">
                <div class="panel-title" style="margin-bottom: 0.8rem;">📦 Restocked Items ({len(store['restocked_items'])})</div>
                <div class="sold-out-grid">''' + "".join([f'''
                    <div class="sold-out-card">
                        <img src="{item['image']}" alt="{item['title']}">
                        <div class="sold-out-info">
                            <h4>{item['title']}</h4>
                            <p>SKU: {item['sku']}</p>
                            <div class="price">₹{item['price']:,.2f} (Restocked: +{item['qty']})</div>
                        </div>
                        <div class="store-badge" style="background-color: rgba(0, 180, 216, 0.2); color: var(--info);">Restocked</div>
                    </div>
                ''' for item in store['restocked_items']]) + f'''
                </div>
            </div>''' if store['restocked_items'] else ''}

            {f'''<div style="margin-bottom: 1.5rem;">
                <div class="panel-title" style="margin-bottom: 0.8rem;">✨ New Arrival Items ({len(store['new_arrival_items'])})</div>
                <div class="sold-out-grid">''' + "".join([f'''
                    <div class="sold-out-card">
                        <img src="{item['image']}" alt="{item['title']}">
                        <div class="sold-out-info">
                            <h4>{item['title']}</h4>
                            <p>SKU: {item['sku']}</p>
                            <div class="price">₹{item['price']:,.2f}</div>
                        </div>
                        <div class="store-badge" style="background-color: rgba(155, 93, 229, 0.2); color: var(--purple);">New Arrival</div>
                    </div>
                ''' for item in store['new_arrival_items']]) + f'''
                </div>
            </div>''' if store['new_arrival_items'] else ''}

            <div class="panel">
                <div class="table-header">
                    <div class="panel-title" style="margin-bottom: 0;">📋 Store Operations History</div>
                    
                    <!-- Labels linked to top-level radio triggers -->
                    <div class="filter-group">
                        <label for="filter-all-{key}" class="filter-label all-btn">All ({len(store['sales'])})</label>
                        <label for="filter-sales-{key}" class="filter-label sales-btn">Sales ({len([i for i in store['sales'] if i['event'] == 'Sale'])})</label>
                        <label for="filter-soldout-{key}" class="filter-label soldout-btn">Sold Outs ({len(store['sold_out'])})</label>
                        <label for="filter-restock-{key}" class="filter-label restock-btn">Restocks ({len(store['restocked_items'])})</label>
                        <label for="filter-newarrival-{key}" class="filter-label newarrival-btn">New Arrivals ({len(store['new_arrival_items'])})</label>
                    </div>
                    
                    <input type="text" id="search-{key}" onkeyup="filterSearch(this, '{key}')" class="search-bar" placeholder="Search product, SKU...">
                </div>
                
                <!-- Desktop Table View -->
                <table class="desktop-only-table">
                    <thead>
                        <tr>
                            <th>Time (IST)</th>
                            <th>Product & Details</th>
                            <th>Event</th>
                            <th>Qty</th>
                            <th>Price</th>
                            <th>Stock Level</th>
                        </tr>
                    </thead>
                    <tbody id="body-{key}">
                        {"".join([f'''
                        <tr data-category="{item['event'].lower().replace(' ', '-')}">
                            <td class="timestamp">{item['timestamp']}</td>
                            <td>
                                <div class="product-cell">
                                    <img src="{item['image']}" alt="{item['title']}">
                                    <div class="product-details">
                                        <a href="{item['url']}" target="_blank">{item['title']}</a>
                                        <span>SKU: {item['sku']} | Variant: {item['variant']}</span>
                                    </div>
                                </div>
                            </td>
                            <td>
                                <span class="event-badge {item['event'].lower().replace(' ', '-')}">{item['event']}</span>
                            </td>
                            <td>{item['qty']}</td>
                            <td class="price-col">₹{item['price']:,.2f}</td>
                            <td class="timestamp">{item['old']} ➡️ {item['new']}</td>
                        </tr>
                        ''' for item in store['sales']])}
                    </tbody>
                </table>
                
                <!-- Mobile View Cards -->
                <div class="mobile-only-cards" id="cards-{key}">
                    {"".join([f'''
                    <div class="mobile-card" data-category="{item['event'].lower().replace(' ', '-')}">
                        <div class="mobile-card-image-wrapper">
                            <img src="{item['image']}" alt="{item['title']}">
                        </div>
                        <div class="mobile-card-body">
                            <div class="mobile-card-details">
                                <h4><a href="{item['url']}" target="_blank" style="color: var(--text); text-decoration: none;">{item['title']}</a></h4>
                                <span>SKU: {item['sku']} | Variant: {item['variant']}</span>
                                <span style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.3rem;">🕒 {item['timestamp']} (IST)</span>
                            </div>
                            <div class="mobile-card-stats">
                                <div>
                                    <span class="event-badge {item['event'].lower().replace(' ', '-')}">{item['event']}</span>
                                    <span style="margin-left: 0.5rem; color: var(--text-muted);">Qty: {item['qty']}</span>
                                </div>
                                <div>
                                    <span class="mobile-card-price">₹{item['price']:,.2f}</span>
                                    <span style="margin-left: 0.5rem; color: var(--text-muted);">({item['old']} ➡️ {item['new']})</span>
                                </div>
                            </div>
                        </div>
                    </div>
                    ''' for item in store['sales']])}
                </div>
            </div>
            
            <div style="margin-top: 1.5rem; text-align: center;">
                <a href="#top" style="color: var(--primary); text-decoration: none; font-size: 0.85rem; font-weight: 500;">▲ Back to Top</a>
            </div>
        </div>
        ''' for key, store in combined_data.items()])}
        
    </div>
    
    <script>
        function filterSearch(inputEl, key) {{
            const filterText = inputEl.value.toLowerCase();
            const rows = document.querySelectorAll('#body-' + key + ' tr');
            rows.forEach(row => {{
                row.style.display = row.textContent.toLowerCase().includes(filterText) ? '' : 'none';
            }});
            const cards = document.querySelectorAll('#cards-' + key + ' .mobile-card');
            cards.forEach(card => {{
                card.style.display = card.textContent.toLowerCase().includes(filterText) ? '' : 'none';
            }});
        }}
    </script>
</body>
</html>
"""
    
    with open(output_html, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"Patched Unified Dashboard Report generated successfully at: {output_html}")

if __name__ == "__main__":
    generate_unified_report("24h")
    now_utc = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    now_ist = now_utc + datetime.timedelta(hours=5, minutes=30)
    generate_unified_report(now_ist.strftime('%Y-%m-%d'))
