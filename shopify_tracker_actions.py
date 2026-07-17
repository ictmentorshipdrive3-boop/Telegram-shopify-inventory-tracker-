import time
import datetime
import os
import csv
import json
import argparse
import base64
import requests
from urllib.parse import urlparse
import re

def clean_string(val):
    if not isinstance(val, str):
        return val
    return re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', val)

def get_store_domain(url_str):
    if not url_str.startswith('http://') and not url_str.startswith('https://'):
        url_str = 'https://' + url_str
    parsed = urlparse(url_str)
    domain = parsed.netloc
    if domain.startswith('www.'):
        domain = domain[4:]
    return domain

def harvest_storefront_token(domain):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        r = requests.get(f"https://www.{domain}/", headers=headers, timeout=15)
        html = r.text
        tokens = re.findall(r'"storefrontAccessToken":"([a-f0-9]{32})"', html)
        tokens_js = re.findall(r'storefrontAccessToken\s*:\s*["\']([a-f0-9]{32})["\']', html)
        tokens_raw = re.findall(r'accessToken["\']?\s*:\s*["\']([a-f0-9]{32})["\']', html, re.IGNORECASE)
        found = tokens + tokens_js + tokens_raw
        if found:
            return found[0]
    except Exception as e:
        print(f"Token harvest error: {e}")
        
    # Fallback tokens for known stores
    fallbacks = {
        'theamethyststore.com': 'eab767e550e9011899a582d53084a6c2',
        'kanshijewels.com': '9a3eed2b46c608cf9357de80d28fac47',
        'kushals.com': '4642b1e870d93fd7e6588208b13000bc',
        'dulhanjewels.com': '2a836df2b82846963a38b5ef407d6018',
        'rasasilver.com': 'fdd5c64e457d4d94593093bb17734bfe',
        'muskanjewel.com': 'ece39a0ad683230d3ffd3737c38c3145'
    }
    clean_domain = domain.lower()
    if clean_domain.startswith('www.'):
        clean_domain = clean_domain[4:]
    if clean_domain in fallbacks:
        print(f"Using fallback Storefront Access Token for {clean_domain}: {fallbacks[clean_domain]}")
        return fallbacks[clean_domain]
        
    return None

def post_graphql_query(url, headers, payload, max_retries=5):
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=25)
            if r.status_code == 429:
                time.sleep(6 * attempt)
                continue
            if r.status_code == 200:
                data = r.json()
                errors = data.get('errors', [])
                throttled = False
                for err in errors:
                    ext_code = err.get('extensions', {}).get('code')
                    msg = err.get('message', '').lower()
                    if ext_code == 'THROTTLED' or 'throttle' in msg:
                        throttled = True
                        break
                if throttled:
                    time.sleep(7 * attempt)
                    continue
                return data
        except Exception:
            time.sleep(3)
    return None

def fetch_current_inventory(domain, token, collection_handle=None):
    url = f"https://{domain}/api/2023-07/graphql.json"
    headers = {
        'X-Shopify-Storefront-Access-Token': token,
        'Content-Type': 'application/json'
    }
    
    if collection_handle:
        query = """
        query getCollectionProducts($cursor: String, $handle: String!) {
          collection(handle: $handle) {
            products(first: 250, after: $cursor) {
              pageInfo {
                hasNextPage
                endCursor
              }
              edges {
                node {
                  title
                  handle
                  images(first: 1) {
                    edges {
                      node {
                        url
                      }
                    }
                  }
                  variants(first: 100) {
                    edges {
                      node {
                        id
                        title
                        sku
                        price {
                          amount
                        }
                        availableForSale
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
    else:
        query = """
        query getAllProducts($cursor: String) {
          products(first: 250, after: $cursor) {
            pageInfo {
              hasNextPage
              endCursor
            }
            edges {
              node {
                title
                handle
                images(first: 1) {
                  edges {
                    node {
                      url
                    }
                  }
                }
                variants(first: 100) {
                  edges {
                    node {
                      id
                      title
                      sku
                      price {
                        amount
                      }
                      availableForSale
                    }
                  }
                }
              }
            }
          }
        }
        """
    
    active_variants = []
    out_of_stock_variants = []
    cursor = None
    has_next = True
    
    while has_next:
        variables = {"cursor": cursor}
        if collection_handle:
            variables["handle"] = collection_handle
            
        payload = {'query': query, 'variables': variables}
        data = post_graphql_query(url, headers, payload)
        if not data:
            break
            
        if collection_handle:
            products_conn = data.get('data', {}).get('collection', {}).get('products', {})
        else:
            products_conn = data.get('data', {}).get('products', {})
            
        if not products_conn:
            break
            
        edges = products_conn.get('edges', [])
        for edge in edges:
            node = edge['node']
            p_title = node['title']
            p_handle = node['handle']
            
            # Extract first image URL
            image_url = None
            img_edges = node.get('images', {}).get('edges', [])
            if img_edges:
                image_url = img_edges[0]['node']['url']
            
            for v_edge in node.get('variants', {}).get('edges', []):
                v_node = v_edge['node']
                global_id = v_node['id']
                try:
                    decoded = base64.b64decode(global_id).decode('utf-8')
                    variant_id = int(decoded.split('/')[-1])
                except Exception:
                    variant_id = global_id
                    
                v_info = {
                    'product_title': p_title,
                    'product_handle': p_handle,
                    'variant_id': str(variant_id),
                    'global_id': global_id,
                    'variant_title': v_node['title'],
                    'sku': v_node['sku'],
                    'price': float(v_node['price']['amount']),
                    'url': f"https://www.{domain}/products/{p_handle}?variant={variant_id}",
                    'image_url': image_url
                }
                
                if v_node.get('availableForSale', False):
                    active_variants.append(v_info)
                else:
                    v_info['stock'] = 0
                    out_of_stock_variants.append(v_info)
                    
        page_info = products_conn.get('pageInfo', {})
        has_next = page_info.get('hasNextPage', False)
        cursor = page_info.get('endCursor', None)
        
    print(f"Catalog fetched: {len(active_variants)} active, {len(out_of_stock_variants)} out of stock.")
    
    # Check stocks via cart API
    mutation = """
    mutation cartCreate($input: CartInput!) {
      cartCreate(input: $input) {
        cart {
          lines(first: 250) {
            edges {
              node {
                quantity
                merchandise {
                  ... on ProductVariant {
                    id
                  }
                }
              }
            }
          }
        }
      }
    }
    """
    
    stock_results = {}
    batch_size = 90
    for i in range(0, len(active_variants), batch_size):
        batch = active_variants[i:i+batch_size]
        lines = [{'merchandiseId': v['global_id'], 'quantity': 9999} for v in batch]
        variables = {"input": {"lines": lines}}
        
        data = post_graphql_query(url, headers, {'query': mutation, 'variables': variables})
        if data:
            cart_data = data.get('data', {}).get('cartCreate', {}).get('cart', {})
            if cart_data:
                quantities = {}
                for edge in cart_data.get('lines', {}).get('edges', []):
                    node = edge['node']
                    g_id = node['merchandise']['id']
                    qty = node['quantity']
                    quantities[g_id] = qty
                for v in batch:
                    stock_results[v['variant_id']] = quantities.get(v['global_id'], 0)
            else:
                for v in batch: stock_results[v['variant_id']] = -1
        else:
            for v in batch: stock_results[v['variant_id']] = -1
        time.sleep(1.5)
        
    current_inventory = {}
    
    # Process active
    for v in active_variants:
        stock = stock_results.get(v['variant_id'], 0)
        if stock > 0:
            current_inventory[v['variant_id']] = {
                'product_title': clean_string(v['product_title']),
                'variant_title': clean_string(v['variant_title']),
                'sku': clean_string(v['sku']),
                'price': v['price'],
                'stock': stock,
                'url': v['url'],
                'image_url': v['image_url']
            }
            
    # Process out of stock
    for v in out_of_stock_variants:
        current_inventory[v['variant_id']] = {
            'product_title': clean_string(v['product_title']),
            'variant_title': clean_string(v['variant_title']),
            'sku': clean_string(v['sku']),
            'price': v['price'],
            'stock': 0,
            'url': v['url'],
            'image_url': v['image_url']
        }
        
    return current_inventory

def send_telegram_notification(bot_token, chat_id, item, event_type, qty, old_stock, new_stock):
    product_title = item['product_title']
    variant_title = item['variant_title']
    sku = item['sku'] or 'N/A'
    price = item['price']
    url = item['url']
    image_url = item.get('image_url')
    
    if event_type == 'Sold Out':
        emoji = "🚨"
        header = "SOLD OUT!"
    else:
        emoji = "🛍️"
        header = "NEW SALE!"
        
    caption = f"{emoji} <b>{header}</b> {emoji}\n\n" \
              f"<b>Product:</b> {product_title}\n" \
              f"<b>Variant:</b> {variant_title}\n" \
              f"<b>SKU:</b> {sku}\n" \
              f"<b>Price:</b> ₹{price:,.2f}\n" \
              f"<b>Quantity Sold:</b> {qty}\n" \
              f"<b>Stock Update:</b> {old_stock} ➡️ {new_stock}\n\n" \
              f"🔗 <a href='{url}'>View on Store</a>"
              
    if image_url:
        photo_url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
        payload = {
            'chat_id': chat_id,
            'photo': image_url,
            'caption': caption,
            'parse_mode': 'HTML'
        }
        try:
            r = requests.post(photo_url, json=payload, timeout=12)
            if r.status_code == 200:
                print(f"Telegram photo notification sent for {event_type.lower()}: {product_title}")
                return
            else:
                print(f"Failed to send Telegram photo: HTTP {r.status_code} {r.text}")
        except Exception as e:
            print(f"Telegram photo exception: {e}")
            
    # Text fallback
    text_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': caption,
        'parse_mode': 'HTML',
        'disable_web_page_preview': False
    }
    try:
        r = requests.post(text_url, json=payload, timeout=12)
        if r.status_code == 200:
            print(f"Telegram text notification sent for {event_type.lower()}: {product_title}")
        else:
            print(f"Failed to send Telegram text: HTTP {r.status_code} {r.text}")
    except Exception as e:
        print(f"Telegram text exception: {e}")

def send_telegram_status_ok(bot_token, chat_id):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    caption = f"ℹ️ <b>Shopify Tracker Status</b>\n\n" \
              f"<b>Status:</b> Active (No stock changes detected)\n" \
              f"<b>Timestamp:</b> {timestamp}"
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': caption,
        'parse_mode': 'HTML',
        'disable_notification': True,
        'disable_web_page_preview': True
    }
    try:
        r = requests.post(url, json=payload, timeout=12)
        if r.status_code == 200:
            print("Telegram status update sent (no changes).")
    except Exception as e:
        print(f"Telegram status exception: {e}")

def main():
    parser = argparse.ArgumentParser(description="Shopify Actions Tracking Engine")
    parser.add_argument("--url", required=True, help="Base Shopify URL")
    parser.add_argument("--collection", help="Optional collection handle filter")
    parser.add_argument("--output-dir", default=".", help="Directory for cache & log")
    args = parser.parse_args()
    
    domain = get_store_domain(args.url)
    suffix = f"_{args.collection}" if args.collection else ""
    cache_path = os.path.join(args.output_dir, f"{domain.replace('.', '_')}{suffix}_live_cache.json")
    log_path = os.path.join(args.output_dir, f"{domain.replace('.', '_')}{suffix}_live_sales_log.csv")
    
    # Read Secrets from environment
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        print("Warning: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variables are not set. Notification steps will be skipped.")
        
    # Initialize Log CSV if not exists
    if not os.path.exists(log_path):
        with open(log_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Timestamp', 'Product Title', 'Variant Title', 'SKU', 'Price', 'Event Type', 'Quantity', 'Previous Stock', 'Current Stock', 'Product URL'])
            
    # Load Cache
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"Loaded cache baseline with {len(cache)} products.")
        except Exception as e:
            print(f"Error loading cache: {e}")
            
    token = harvest_storefront_token(domain)
    if not token:
        print("Error: Could not harvest storefront access token.")
        return
        
    current = fetch_current_inventory(domain, token, args.collection)
    if not current:
        print("Error: Failed to fetch current inventory.")
        return
        
    if not cache:
        # First run: Save current as cache and exit (setup baseline)
        print("No cache file found. Saving current inventory as baseline. Alerts will trigger starting on the next execution.")
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(current, f, indent=2)
        return
        
    changes = []
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Compare
    for vid, item in current.items():
        new_stock = item['stock']
        if vid in cache:
            old_stock = cache[vid]['stock']
            if old_stock > new_stock:
                qty_sold = old_stock - new_stock
                event = 'Sold Out' if new_stock == 0 else 'Sale'
                changes.append({
                    'event': event, 'qty': qty_sold, 'old': old_stock, 'new': new_stock, 'item': item
                })
            elif new_stock > old_stock:
                qty_added = new_stock - old_stock
                changes.append({
                    'event': 'Restock', 'qty': qty_added, 'old': old_stock, 'new': new_stock, 'item': item
                })
        else:
            if new_stock > 0:
                changes.append({
                    'event': 'New Arrival', 'qty': new_stock, 'old': 0, 'new': new_stock, 'item': item
                })
                
    # Check for deleted/missing variants in current state
    for vid, item in cache.items():
        if vid not in current and item['stock'] > 0:
            changes.append({
                'event': 'Sold Out', 'qty': item['stock'], 'old': item['stock'], 'new': 0, 'item': item
            })
            
    # Process updates
    if changes:
        print(f"Detected {len(changes)} changes.")
        with open(log_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for c in changes:
                evt, qty, old, new, it = c['event'], c['qty'], c['old'], c['new'], c['item']
                print(f"  [{evt}] {it['product_title']} - Stock: {old} -> {new}")
                writer.writerow([
                    timestamp, it['product_title'], it['variant_title'], it['sku'], it['price'],
                    evt, qty, old, new, it['url']
                ])
                
                # Send telegram notification if it is a Sale or Sold Out event and tokens exist
                if evt in ['Sale', 'Sold Out'] and bot_token and chat_id:
                    send_telegram_notification(bot_token, chat_id, it, evt, qty, old, new)
    else:
        print("No changes detected.")
        if bot_token and chat_id:
            send_telegram_status_ok(bot_token, chat_id)
        
    # Save cache
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(current, f, indent=2)
    print("Inventory cache updated.")

if __name__ == '__main__':
    main()
