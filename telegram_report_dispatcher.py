import os
import sys
import time
import datetime
import requests
import subprocess
import json

# Ensure local directory is on python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import generate_unified_report
import generate_kanshi_standalone

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8711658844:AAEtDHYsx8Mpb5v3LA8vB-v9piJzHGIkHKg")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-5393248315")

def send_telegram_text(text, chat_id=CHAT_ID):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        return r.json()
    except Exception as e:
        print(f"Error sending Telegram text: {e}")
        return None

def send_telegram_document(file_path, caption="", chat_id=CHAT_ID):
    if not os.path.exists(file_path):
        print(f"File not found for Telegram upload: {file_path}")
        return None
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    try:
        with open(file_path, 'rb') as doc:
            files = {'document': (os.path.basename(file_path), doc, 'text/html')}
            data = {
                'chat_id': chat_id,
                'caption': caption,
                'parse_mode': 'HTML'
            }
            r = requests.post(url, data=data, files=files, timeout=60)
            return r.json()
    except Exception as e:
        print(f"Error sending Telegram document: {e}")
        return None

def generate_and_dispatch_report(target_date_str, chat_id=CHAT_ID, prefix_title="DAILY SALES REPORT"):
    # Calculate IST Date
    now_utc = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    now_ist = now_utc + datetime.timedelta(hours=5, minutes=30)
    
    if target_date_str == 'today':
        target_date = now_ist.date()
    elif target_date_str == 'yesterday':
        target_date = (now_ist - datetime.timedelta(days=1)).date()
    else:
        try:
            target_date = datetime.datetime.strptime(target_date_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = (now_ist - datetime.timedelta(days=1)).date()

    target_date_formatted = target_date.strftime('%Y-%m-%d')
    date_title = target_date.strftime('%A, %B %d, %Y')
    suffix = target_date.strftime('%Y%m%d')

    print(f"[{datetime.datetime.now()}] Generating reports for {target_date_formatted}...")
    
    # 1. Compile Reports
    generate_unified_report.generate_unified_report(target_date_formatted)
    generate_kanshi_standalone.generate_kanshi_standalone(target_date_formatted)

    # 2. Locate generated files
    out_dirs = [
        os.path.join(current_dir, "reports"),
        current_dir,
        r"C:\Users\AMD\Downloads",
        os.path.expanduser("~/Downloads"),
        "/home/ubuntu/shopify-inventory-tracker"
    ]
    
    unified_html = None
    kanshi_html = None
    
    for d in out_dirs:
        u_candidate = os.path.join(d, f"multi_store_sales_report_{suffix}.html")
        k_candidate = os.path.join(d, f"kanshi_sales_report_{suffix}.html")
        if os.path.exists(u_candidate) and not unified_html:
            unified_html = u_candidate
        if os.path.exists(k_candidate) and not kanshi_html:
            kanshi_html = k_candidate

    # 3. Read summary metrics from data
    repo_dir = current_dir if os.path.exists(os.path.join(current_dir, "theamethyststore_com_live_sales_log.csv")) else os.path.join(current_dir, "data")
    
    stores_config = {
        'theamethyststore_com': {'name': 'The Amethyst Store', 'log': 'theamethyststore_com_live_sales_log.csv'},
        'rasasilver_com': {'name': 'Rasa Silver', 'log': 'rasasilver_com_live_sales_log.csv'},
        'daivik_in': {'name': 'Daivik Jewels', 'log': 'daivik_in_live_sales_log.csv'},
        'dulhanjewels_com': {'name': 'Dulhan Jewels', 'log': 'dulhanjewels_com_live_sales_log.csv'},
        'kanshijewels_com': {'name': 'Kanshi Jewels', 'log': 'kanshijewels_com_live_sales_log.csv'},
        'muskanjewel_com': {'name': 'Muskan Jewel', 'log': 'muskanjewel_com_live_sales_log.csv'}
    }

    import csv
    grand_sales = 0
    grand_qty = 0
    grand_revenue = 0.0
    grand_restocks = 0
    grand_new_arrivals = 0
    store_summaries = []

    for k, cfg in stores_config.items():
        log_file = os.path.join(repo_dir, cfg['log'])
        if not os.path.exists(log_file):
            continue
            
        raw_rows = []
        with open(log_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                title_lower = row.get('Product Title', '').lower()
                sku_lower = row.get('SKU', '').lower()
                try: qty_val = int(row.get('Quantity', 1))
                except: qty_val = 1
                if 'test' in title_lower or 'test' in sku_lower or qty_val >= 1000: continue
                try: dt_utc = datetime.datetime.strptime(row['Timestamp'], "%Y-%m-%d %H:%M:%S")
                except: continue
                dt_ist_row = dt_utc + datetime.timedelta(hours=5, minutes=30)
                if dt_ist_row.date() == target_date: raw_rows.append((row, dt_ist_row))

        flicker_indices = set()
        sales_indices = [(idx, dt_i, (r.get('Product Title', '').strip(), r.get('Variant Title', '').strip())) for idx, (r, dt_i) in enumerate(raw_rows) if r['Event Type'] in ['Sale', 'Sold Out']]
        restock_indices = [(idx, dt_i, (r.get('Product Title', '').strip(), r.get('Variant Title', '').strip())) for idx, (r, dt_i) in enumerate(raw_rows) if r['Event Type'] in ['Restock', 'New Arrival']]

        for s_idx, s_dt, s_key in sales_indices:
            for r_idx, r_dt, r_key in restock_indices:
                if r_idx not in flicker_indices and s_key == r_key and r_dt >= s_dt:
                    diff_mins = (r_dt - s_dt).total_seconds() / 60.0
                    if diff_mins <= 30.0:
                        flicker_indices.add(s_idx)
                        flicker_indices.add(r_idx)
                        break

        reconciled = [r for idx, (r, dt_i) in enumerate(raw_rows) if idx not in flicker_indices]
        s_sales = sum(1 for r in reconciled if r['Event Type'] in ['Sale', 'Sold Out'])
        s_qty = sum(int(r['Quantity']) for r in reconciled if r['Event Type'] in ['Sale', 'Sold Out'])
        s_rev = sum(float(r['Price']) * int(r['Quantity']) for r in reconciled if r['Event Type'] in ['Sale', 'Sold Out'])
        s_restocks = sum(int(r['Quantity']) for r in reconciled if r['Event Type'] == 'Restock')
        s_new = sum(int(r['Quantity']) for r in reconciled if r['Event Type'] == 'New Arrival')

        grand_sales += s_sales
        grand_qty += s_qty
        grand_revenue += s_rev
        grand_restocks += s_restocks
        grand_new_arrivals += s_new
        
        store_summaries.append(f"• <b>{cfg['name']}:</b> ₹{s_rev:,.2f} <i>({s_sales} sales, {s_qty} units)</i>")

    # Format Summary Message
    message = f"👑 <b>{prefix_title}</b>\n" \
              f"📅 <b>Date:</b> {date_title}\n\n" \
              f"💰 <b>Total Net Revenue:</b> ₹{grand_revenue:,.2f} (₹{grand_revenue/100000:.2f} Lakhs)\n" \
              f"🛍️ <b>Total Sales Events:</b> {grand_sales}\n" \
              f"📦 <b>Total Units Sold:</b> {grand_qty}\n" \
              f"🔄 <b>Restocked Units:</b> {grand_restocks}\n" \
              f"✨ <b>New Arrivals:</b> {grand_new_arrivals}\n\n" \
              f"🏬 <b>Store Performance Breakdown:</b>\n" + "\n".join(store_summaries) + "\n\n" \
              f"<i>📁 Full interactive HTML dashboards (with 100% offline photos) attached below:</i>"

    send_telegram_text(message, chat_id)

    # Attach documents
    if unified_html and os.path.exists(unified_html):
        send_telegram_document(unified_html, caption=f"📊 Multi-Store Network Sales Dashboard ({target_date_formatted})", chat_id=chat_id)
    if kanshi_html and os.path.exists(kanshi_html):
        send_telegram_document(kanshi_html, caption=f"💎 Kanshi Jewels Standalone Sales Dashboard ({target_date_formatted})", chat_id=chat_id)

    print(f"[+] Successfully generated and dispatched reports for {target_date_formatted} to Telegram!")

def run_dispatcher_loop():
    print("🚀 Telegram Automated Report Dispatcher & Bot Daemon Started!")
    last_dispatched_date = None
    last_update_id = 0

    while True:
        try:
            now_utc = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
            now_ist = now_utc + datetime.timedelta(hours=5, minutes=30)

            # 1. Midnight Daily Dispatch Check (At 00:01 AM IST)
            if now_ist.hour == 0 and now_ist.minute >= 1 and now_ist.date() != last_dispatched_date:
                print(f"[Midnight Trigger] Clock struck {now_ist.strftime('%I:%M %p')} IST. Generating yesterday's report...")
                generate_and_dispatch_report("yesterday", prefix_title="AUTOMATED DAILY SALES REPORT")
                last_dispatched_date = now_ist.date()

            # 2. Interactive Command Polling via getUpdates
            updates_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={last_update_id + 1}&timeout=5"
            try:
                res = requests.get(updates_url, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    for upd in data.get('result', []):
                        last_update_id = upd['update_id']
                        msg = upd.get('message', {})
                        text = msg.get('text', '').strip()
                        c_id = str(msg.get('chat', {}).get('id', CHAT_ID))

                        if not text:
                            continue

                        parts = text.split()
                        cmd = parts[0].lower()

                        if cmd in ['/yesterday', '/report_yesterday']:
                            send_telegram_text("⏳ Compiling yesterday's sales report... Please wait 10 seconds.", c_id)
                            generate_and_dispatch_report("yesterday", chat_id=c_id, prefix_title="ON-DEMAND SALES REPORT (YESTERDAY)")
                        elif cmd in ['/today', '/report_today']:
                            send_telegram_text("⏳ Compiling today's live sales report... Please wait 10 seconds.", c_id)
                            generate_and_dispatch_report("today", chat_id=c_id, prefix_title="ON-DEMAND SALES REPORT (TODAY)")
                        elif cmd == '/report' and len(parts) > 1:
                            target_arg = parts[1]
                            send_telegram_text(f"⏳ Compiling sales report for {target_arg}... Please wait 10 seconds.", c_id)
                            generate_and_dispatch_report(target_arg, chat_id=c_id, prefix_title=f"ON-DEMAND SALES REPORT ({target_arg})")
                        elif cmd in ['/help', '/start']:
                            help_text = "👋 <b>Shopify Inventory & Sales Intelligence Bot</b>\n\n" \
                                        "<b>Available Commands:</b>\n" \
                                        "• <code>/yesterday</code> - Generate & send yesterday's full sales report\n" \
                                        "• <code>/today</code> - Generate & send today's live real-time report\n" \
                                        "• <code>/report YYYY-MM-DD</code> - Generate report for a custom date (e.g. <code>/report 2026-08-14</code>)\n" \
                                        "• <code>/status</code> - Check tracker health & active status\n\n" \
                                        "<i>Automatic reports are sent every midnight at 12:01 AM IST!</i>"
                            send_telegram_text(help_text, c_id)
                        elif cmd == '/status':
                            status_text = f"🟢 <b>24/7 Cloud Tracker Status: ACTIVE</b>\n\n" \
                                          f"• <b>Server:</b> Oracle Cloud Always Free (24/7/365)\n" \
                                          f"• <b>Current Time (IST):</b> {now_ist.strftime('%A, %b %d, %Y %I:%M:%S %p')}\n" \
                                          f"• <b>Tracking Cycle:</b> Every 5 minutes\n" \
                                          f"• <b>Monitored Stores:</b> 6 Stores Active\n" \
                                          f"• <b>Midnight Dispatch:</b> Scheduled at 12:01 AM IST daily"
                            send_telegram_text(status_text, c_id)
            except Exception as e:
                pass

        except Exception as e:
            print(f"Dispatcher loop error: {e}")

        time.sleep(3)

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] != 'daemon':
        generate_and_dispatch_report(sys.argv[1])
    else:
        run_dispatcher_loop()
