import csv
import json
import os
import re
import base64
import requests
import datetime

from concurrent.futures import ThreadPoolExecutor

image_b64_cache = {}

def fetch_single_image(url):
    if not url or url in image_b64_cache:
        return
    try:
        sep = '&' if '?' in url else '?'
        optimized_url = f"{url}{sep}format=jpg&width=200"
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
        if os.path.exists(c) and os.path.exists(os.path.join(c, "kanshijewels_com_live_sales_log.csv")):
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

def generate_kanshi_standalone(target_date_str=None):
    repo_dir = resolve_repo_dir()
    out_dir = resolve_output_dir()
    
    csv_path = os.path.join(repo_dir, "kanshijewels_com_live_sales_log.csv")
    cache_path = os.path.join(repo_dir, "kanshijewels_com_live_cache.json")
    
    if not os.path.exists(csv_path) or not os.path.exists(cache_path):
        print(f"Error: Required files are missing in {repo_dir}.")
        return
        
    with open(cache_path, 'r', encoding='utf-8') as f:
        cache = json.load(f)
        
    # Get current time in IST (UTC + 5:30)
    now_utc = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    now_ist = now_utc + datetime.timedelta(hours=5, minutes=30)
    
    is_24h = (target_date_str == "24h")
    
    if is_24h:
        title_date = f"Last 24 Hours (As of {now_ist.strftime('%A, %b %d, %Y %I:%M %p')} IST)"
        output_html = os.path.join(out_dir, "kanshi_sales_report_24h.html")
        cutoff_ist = now_ist - datetime.timedelta(hours=24)
    else:
        if target_date_str is None:
            today_ist = now_ist.date()
        else:
            today_ist = datetime.datetime.strptime(target_date_str, '%Y-%m-%d').date()
            
        title_date = today_ist.strftime('%A, %B %d, %Y (IST)')
        output_html = os.path.join(out_dir, f"kanshi_sales_report_{today_ist.strftime('%Y%m%d')}.html")
        
    sales = []
    sold_out_items = []
    restocked_items = []
    new_arrival_items = []
    total_revenue = 0.0
    total_qty_sold = 0
    total_restocked = 0
    total_new_arrivals = 0
    
    # First pass: gather raw data and convert UTC timestamps to IST
    raw_sales = []
    with open(csv_path, 'r', encoding='utf-8') as f:
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
                # Log files store UTC timestamps
                dt_utc = datetime.datetime.strptime(row['Timestamp'], "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue
            
            # Convert to IST (UTC + 5:30)
            dt_ist = dt_utc + datetime.timedelta(hours=5, minutes=30)
            
            # Filter based on 24h rolling window or specific IST date
            if is_24h:
                if dt_ist >= cutoff_ist:
                    raw_sales.append((row, dt_ist))
            else:
                if dt_ist.date() == today_ist:
                    raw_sales.append((row, dt_ist))
                    
    # Pre-pass reconciliation: filter out catalog flickers (false disappearances/reappearances)
    flicker_indices = set()
    sales_indices = []
    restock_indices = []

    for idx, (row, dt_ist) in enumerate(raw_sales):
        evt = row['Event Type']
        key = (row.get('Product Title', '').strip(), row.get('Variant Title', '').strip())
        if evt in ['Sale', 'Sold Out']:
            sales_indices.append((idx, dt_ist, key))
        elif evt in ['Restock', 'New Arrival']:
            restock_indices.append((idx, dt_ist, key))

    for s_idx, s_dt, s_key in sales_indices:
        for r_idx, r_dt, r_key in restock_indices:
            if r_idx not in flicker_indices and s_key == r_key and r_dt >= s_dt:
                diff_mins = (r_dt - s_dt).total_seconds() / 60.0
                if diff_mins <= 30.0:
                    flicker_indices.add(s_idx)
                    flicker_indices.add(r_idx)
                    break

    reconciled_raw_sales = [item for idx, item in enumerate(raw_sales) if idx not in flicker_indices]

    # Second pass: download images and build item data
    for row, dt_ist in reconciled_raw_sales:
        url = row['Product URL']
        variant_id = ""
        match = re.search(r'variant=(gid://shopify/ProductVariant/\d+)', url)
        if match:
            variant_id = match.group(1)
        
        image_url = ""
        if variant_id in cache:
            image_url = cache[variant_id].get('image_url', '')
        
        price = float(row['Price'])
        qty = int(row['Quantity'])
        evt = row['Event Type']
        
        item_data = {
            'dt_ist': dt_ist,
            'timestamp': dt_ist.strftime('%I:%M %p'), # e.g. '04:30 PM'
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
                sold_out_items.append(item_data)
            total_revenue += price * qty
            total_qty_sold += qty
        elif evt == 'Restock':
            restocked_items.append(item_data)
            total_restocked += qty
        elif evt == 'New Arrival':
            new_arrival_items.append(item_data)
            total_new_arrivals += qty

    # Sort sales chronologically (newest first) in IST
    sales.sort(key=lambda x: x['dt_ist'], reverse=True)
    
    # Preload and embed Base64 images
    raw_urls = [x['image'] for x in sales if x.get('image')]
    preload_images(raw_urls)
    
    for item in sales:
        item['image'] = get_base64_image(item['image'])

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="referrer" content="no-referrer">
    <title>Kanshi Jewels - Daily Performance Report ({title_date})</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #0c080e;
            --card-bg: #150f19;
            --primary: #c5a880; 
            --accent: #e2c08d;
            --text: #f0ecf4;
            --text-muted: #9f96a6;
            --border: #2c2033;
            --danger: #ff5e62;
            --success: #2ec4b6;
            --info: #00b4d8;
            --purple: #9b5de5;
            --tab-active-bg: #2b1c35;
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
            padding: 1rem 0.5rem;
            min-height: 100vh;
        }}
        
        @media(min-width: 768px) {{
            body {{
                padding: 2rem 1.5rem;
            }}
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        header {{
            display: flex;
            flex-direction: column;
            gap: 1rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 1.5rem;
            margin-bottom: 1.5rem;
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
            font-size: 2.2rem;
            font-weight: 700;
            letter-spacing: -0.5px;
            color: var(--primary);
            text-transform: uppercase;
        }}
        
        .logo-section p {{
            color: var(--text-muted);
            font-size: 0.95rem;
            margin-top: 0.2rem;
        }}
        
        .date-badge {{
            align-self: flex-start;
            background: linear-gradient(135deg, var(--primary), var(--accent));
            color: #120917;
            font-weight: 600;
            padding: 0.5rem 1rem;
            border-radius: 50px;
            font-size: 0.85rem;
        }}
        
        @media(min-width: 768px) {{
            .date-badge {{
                align-self: auto;
                font-size: 0.95rem;
                padding: 0.6rem 1.2rem;
            }}
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        
        .stat-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1.5rem;
        }}
        
        .stat-card h3 {{
            color: var(--text-muted);
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 0.5rem;
        }}
        
        .stat-card .val {{
            font-size: 2rem;
            font-weight: 700;
        }}
        
        .stat-card .val.gold {{
            color: var(--primary);
        }}
        
        .sold-out-wrapper {{
            margin-bottom: 2.5rem;
        }}
        
        .section-title {{
            font-size: 1.3rem;
            font-weight: 600;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        
        .sold-out-list {{
            display: flex;
            gap: 1rem;
            overflow-x: auto;
            padding-bottom: 0.8rem;
            scrollbar-width: thin;
            scrollbar-color: var(--border) transparent;
            -webkit-overflow-scrolling: touch;
        }}
        
        .sold-out-card {{
            flex: 0 0 280px;
            background-color: var(--card-bg);
            border: 1px solid var(--danger);
            border-radius: 12px;
            padding: 1rem;
            display: flex;
            align-items: center;
            gap: 1rem;
            position: relative;
        }}
        
        .sold-out-card img {{
            width: 90px;
            height: 90px;
            object-fit: cover;
            border-radius: 8px;
            border: 1px solid var(--border);
        }}
        
        .sold-out-info {{
            flex-grow: 1;
            overflow: hidden;
        }}
        
        .sold-out-info h4 {{
            font-size: 0.95rem;
            font-weight: 600;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        
        .sold-out-info p {{
            font-size: 0.8rem;
            color: var(--text-muted);
            margin-top: 0.2rem;
        }}
        
        .sold-out-info .price {{
            color: var(--primary);
            font-weight: 600;
            font-size: 0.9rem;
            margin-top: 0.2rem;
            display: block;
        }}
        
        .sold-out-badge {{
            position: absolute;
            top: 0.5rem;
            right: 0.5rem;
            background-color: var(--danger);
            color: white;
            font-size: 0.65rem;
            font-weight: 700;
            padding: 0.25rem 0.4rem;
            border-radius: 4px;
            text-transform: uppercase;
        }}
        
        .panel {{
            background-color: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1rem;
        }}
        
        @media(min-width: 768px) {{
            .panel {{
                padding: 1.5rem;
            }}
        }}
        
        .table-header {{
            display: flex;
            flex-direction: column;
            gap: 1rem;
            margin-bottom: 1.2rem;
        }}
        
        @media(min-width: 768px) {{
            .table-header {{
                flex-direction: row;
                justify-content: space-between;
                align-items: center;
            }}
        }}
        
        .search-bar {{
            background-color: var(--bg-color);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 0.6rem 1rem;
            color: var(--text);
            font-size: 0.9rem;
            width: 100%;
            outline: none;
        }}
        
        @media(min-width: 768px) {{
            .search-bar {{
                width: 250px;
            }}
        }}
        
        .search-bar:focus {{
            border-color: var(--primary);
        }}
        
        /* CSS-ONLY Tab Selection via Hidden Radio Inputs */
        .filter-radio {{
            display: none;
        }}
        
        .filter-group {{
            display: flex;
            gap: 0.3rem;
            background-color: var(--bg-color);
            padding: 0.25rem;
            border-radius: 8px;
            border: 1px solid var(--border);
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }}
        
        .filter-label {{
            background: none;
            border: 1px solid transparent;
            color: var(--text-muted);
            padding: 0.5rem 1rem;
            font-size: 0.85rem;
            font-weight: 500;
            cursor: pointer;
            border-radius: 6px;
            transition: all 0.15s;
            white-space: nowrap;
            text-align: center;
        }}
        
        .filter-label:hover {{
            color: var(--text);
        }}
        
        /* CSS selection highlighting when radios are checked */
        #filter-all:checked ~ .panel .filter-group .all-btn,
        #filter-sales:checked ~ .panel .filter-group .sales-btn,
        #filter-soldout:checked ~ .panel .filter-group .soldout-btn,
        #filter-restock:checked ~ .panel .filter-group .restock-btn,
        #filter-newarrival:checked ~ .panel .filter-group .newarrival-btn {{
            background-color: var(--tab-active-bg);
            color: var(--primary);
            border-color: var(--primary);
        }}
        
        /* Filter: Sales Only */
        #filter-sales:checked ~ .panel table tbody tr:not([data-category="sale"]),
        #filter-sales:checked ~ .panel .mobile-only-cards .mobile-card:not([data-category="sale"]) {{
            display: none !important;
        }}
        
        /* Filter: Sold Outs Only */
        #filter-soldout:checked ~ .panel table tbody tr:not([data-category="sold-out"]),
        #filter-soldout:checked ~ .panel .mobile-only-cards .mobile-card:not([data-category="sold-out"]) {{
            display: none !important;
        }}
        
        /* Filter: Restocks Only */
        #filter-restock:checked ~ .panel table tbody tr:not([data-category="restock"]),
        #filter-restock:checked ~ .panel .mobile-only-cards .mobile-card:not([data-category="restock"]) {{
            display: none !important;
        }}
        
        /* Filter: New Arrivals Only */
        #filter-newarrival:checked ~ .panel table tbody tr:not([data-category="new-arrival"]),
        #filter-newarrival:checked ~ .panel .mobile-only-cards .mobile-card:not([data-category="new-arrival"]) {{
            display: none !important;
        }}
        
        /* Desktop Table Layout */
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
            padding: 1rem;
            color: var(--text-muted);
            font-weight: 500;
            font-size: 0.85rem;
            border-bottom: 1px solid var(--border);
        }}
        
        td {{
            padding: 1rem;
            border-bottom: 1px solid var(--border);
            vertical-align: middle;
            font-size: 0.9rem;
        }}
        
        tr:hover td {{
            background-color: rgba(197, 168, 128, 0.01);
        }}
        
        .product-cell {{
            display: flex;
            align-items: center;
            gap: 1.2rem;
        }}
        
        .product-cell img {{
            width: 150px;
            height: 150px;
            object-fit: cover;
            border-radius: 12px;
            border: 1px solid var(--border);
        }}
        
        .product-details a {{
            color: var(--text);
            text-decoration: none;
            font-weight: 600;
            font-size: 1.05rem;
        }}
        
        .product-details a:hover {{
            color: var(--primary);
        }}
        
        .product-details span {{
            display: block;
            font-size: 0.85rem;
            color: var(--text-muted);
            margin-top: 0.4rem;
        }}
        
        .event-badge {{
            display: inline-block;
            font-size: 0.75rem;
            font-weight: 600;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            text-transform: uppercase;
        }}
        
        .event-badge.sale {{
            background-color: rgba(46, 196, 182, 0.15);
            color: var(--success);
        }}
        
        .event-badge.restock {{
            background-color: rgba(197, 168, 128, 0.15);
            color: var(--primary);
        }}
        
        .event-badge.new-arrival {{
            background-color: rgba(59, 130, 246, 0.15);
            color: #3b82f6;
        }}
        
        .event-badge.sold-out {{
            background-color: rgba(255, 94, 98, 0.15);
            color: var(--danger);
        }}
        
        .timestamp {{
            font-size: 0.85rem;
            color: var(--text-muted);
        }}
        
        .price-col {{
            font-weight: 600;
            color: var(--primary);
        }}
        
        /* Mobile Pinterest/Instagram Card list (Large 300px jewelry photos) */
        .mobile-only-cards {{
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }}
        
        @media(min-width: 768px) {{
            .mobile-only-cards {{
                display: none;
            }}
        }}
        
        .mobile-card {{
            background-color: var(--bg-color);
            border: 1px solid var(--border);
            border-radius: 16px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            width: 100%;
        }}
        
        .mobile-card-image-wrapper {{
            position: relative;
            width: 100%;
            padding-top: 100%; /* Perfect 1:1 Aspect Ratio square image */
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
            padding: 1.2rem;
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }}
        
        .mobile-card-details {{
            h4 {{
                font-size: 1.05rem;
                font-weight: 600;
                line-height: 1.4;
                margin-bottom: 0.3rem;
            }}
            span {{
                display: block;
                font-size: 0.8rem;
                color: var(--text-muted);
                margin-top: 0.1rem;
            }}
        }}
        
        .mobile-card-stats {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-top: 1px solid var(--border);
            padding-top: 0.8rem;
            margin-top: 0.2rem;
        }}
        
        .mobile-card-price {{
            font-size: 1.15rem;
            font-weight: 700;
            color: var(--primary);
        }}
    </style>
</head>
<body>
    <!-- Radio triggers at the top of container (5 Filter Tabs) -->
    <input type="radio" name="filter-kanshi" id="filter-all" class="filter-radio" checked>
    <input type="radio" name="filter-kanshi" id="filter-sales" class="filter-radio">
    <input type="radio" name="filter-kanshi" id="filter-soldout" class="filter-radio">
    <input type="radio" name="filter-kanshi" id="filter-restock" class="filter-radio">
    <input type="radio" name="filter-kanshi" id="filter-newarrival" class="filter-radio">

    <div class="container">
        <header>
            <div class="logo-section">
                <h1>Kanshi Jewels</h1>
                <p>Daily Operations & Inventory Report (IST)</p>
            </div>
            <div class="date-badge">🗓️ {title_date}</div>
        </header>
        
        <div class="stats-grid">
            <div class="stat-card">
                <h3>Store Revenue</h3>
                <div class="val gold">₹{total_revenue:,.2f}</div>
            </div>
            <div class="stat-card">
                <h3>Units Sold</h3>
                <div class="val">{total_qty_sold}</div>
            </div>
            <div class="stat-card">
                <h3>Items Sold Out</h3>
                <div class="val" style="color: var(--danger);">{len(sold_out_items)}</div>
            </div>
            <div class="stat-card">
                <h3>Units Restocked</h3>
                <div class="val" style="color: var(--info);">{total_restocked}</div>
            </div>
            <div class="stat-card">
                <h3>New Arrivals</h3>
                <div class="val" style="color: var(--purple);">{total_new_arrivals}</div>
            </div>
        </div>
        
        {f'''<div class="sold-out-wrapper">
            <h3 class="section-title">🚨 Completely Sold Out Items ({len(sold_out_items)})</h3>
            <div class="sold-out-list">''' + "".join([f'''
                <div class="sold-out-card">
                    <img src="{item['image']}" alt="{item['title']}">
                    <div class="sold-out-info">
                        <h4>{item['title']}</h4>
                        <p>SKU: {item['sku']}</p>
                        <span class="price">₹{item['price']:,.2f}</span>
                    </div>
                    <div class="sold-out-badge" style="background-color: rgba(255, 90, 95, 0.2); color: var(--danger);">Sold Out</div>
                </div>
            ''' for item in sold_out_items]) + f'''
            </div>
        </div>''' if sold_out_items else ''}
        
        {f'''<div class="sold-out-wrapper">
            <h3 class="section-title">📦 Restocked Items ({len(restocked_items)})</h3>
            <div class="sold-out-list">''' + "".join([f'''
                <div class="sold-out-card">
                    <img src="{item['image']}" alt="{item['title']}">
                    <div class="sold-out-info">
                        <h4>{item['title']}</h4>
                        <p>SKU: {item['sku']}</p>
                        <span class="price">₹{item['price']:,.2f} (Restocked: +{item['qty']})</span>
                    </div>
                    <div class="sold-out-badge" style="background-color: rgba(0, 180, 216, 0.2); color: var(--info);">Restocked</div>
                </div>
            ''' for item in restocked_items]) + f'''
            </div>
        </div>''' if restocked_items else ''}

        {f'''<div class="sold-out-wrapper">
            <h3 class="section-title">✨ New Arrival Items ({len(new_arrival_items)})</h3>
            <div class="sold-out-list">''' + "".join([f'''
                <div class="sold-out-card">
                    <img src="{item['image']}" alt="{item['title']}">
                    <div class="sold-out-info">
                        <h4>{item['title']}</h4>
                        <p>SKU: {item['sku']}</p>
                        <span class="price">₹{item['price']:,.2f}</span>
                    </div>
                    <div class="sold-out-badge" style="background-color: rgba(155, 93, 229, 0.2); color: var(--purple);">New Arrival</div>
                </div>
            ''' for item in new_arrival_items]) + f'''
            </div>
        </div>''' if new_arrival_items else ''}

        <div class="panel">
            <div class="table-header">
                <h3 class="section-title" style="margin-bottom: 0;">📋 Daily Operations Log</h3>
                
                <!-- Labels linked to hidden radio buttons (5 Filter Tabs) -->
                <div class="filter-group">
                    <label for="filter-all" class="filter-label all-btn">All ({len(sales)})</label>
                    <label for="filter-sales" class="filter-label sales-btn">Sales ({len([i for i in sales if i['event'] == 'Sale'])})</label>
                    <label for="filter-soldout" class="filter-label soldout-btn">Sold Outs ({len(sold_out_items)})</label>
                    <label for="filter-restock" class="filter-label restock-btn">Restocks ({len(restocked_items)})</label>
                    <label for="filter-newarrival" class="filter-label newarrival-btn">New Arrivals ({len(new_arrival_items)})</label>
                </div>
                
                <input type="text" id="search-box" onkeyup="filterSearch()" class="search-bar" placeholder="Search product, SKU...">
            </div>
            
            <!-- Desktop View Table (150px Large Photos) -->
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
                <tbody id="table-body">
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
                    ''' for item in sales])}
                </tbody>
            </table>
            
            <!-- Mobile View Cards (Pinterest/Instagram Full-Width 300px Jewelry Photos) -->
            <div class="mobile-only-cards" id="cards-container">
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
                ''' for item in sales])}
            </div>
        </div>
    </div>
    
    <script>
        // JS Fallback for text search only (Category filtering is handled 100% by CSS now!)
        function filterSearch() {{
            const filterText = document.getElementById('search-box').value.toLowerCase();
            
            // Filter desktop table rows
            const rows = document.querySelectorAll('#table-body tr');
            rows.forEach(row => {{
                row.style.display = row.textContent.toLowerCase().includes(filterText) ? '' : 'none';
            }});
            
            // Filter mobile cards
            const cards = document.querySelectorAll('#cards-container .mobile-card');
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
    print(f"Standalone Kanshi Jewels Dashboard Report generated at: {output_html}")

if __name__ == "__main__":
    # Generate rolling 24-hour window report in IST
    generate_kanshi_standalone("24h")
    
    # Generate daily reports in IST (for today and yesterday to handle early morning runs)
    now_utc = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    now_ist = now_utc + datetime.timedelta(hours=5, minutes=30)
    
    generate_kanshi_standalone(now_ist.strftime('%Y-%m-%d'))
    
    # Also generate for yesterday in IST if it's early morning (before 4 AM IST)
    if now_ist.hour < 4:
        yesterday_ist = now_ist - datetime.timedelta(days=1)
        generate_kanshi_standalone(yesterday_ist.strftime('%Y-%m-%d'))
