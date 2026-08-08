import time
import subprocess
import datetime
import os

STORES = [
    {"name": "The Amethyst Store", "url": "https://www.theamethyststore.com"},
    {"name": "Rasa Silver", "url": "https://rasasilver.com"},
    {"name": "Daivik Jewels", "url": "https://daivik.in"},
    {"name": "Dulhan Jewels", "url": "https://www.dulhanjewels.com"},
    {"name": "Kanshi Jewels", "url": "https://kanshijewels.com"},
    {"name": "Muskan Jewel", "url": "https://muskanjewel.com"}
]

INTERVAL_SECONDS = 300  # Run every 5 minutes

def run_tracker_cycle():
    env_vars = os.environ.copy()
    env_vars["TELEGRAM_BOT_TOKEN"] = "8711658844:AAEtDHYsx8Mpb5v3LA8vB-v9piJzHGIkHKg"
    env_vars["TELEGRAM_CHAT_ID"] = "-5393248315"
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n[{now_str}] --- STARTING TRACKER CYCLE FOR ALL STORES ---")
    
    for store in STORES:
        try:
            print(f"  [+] Checking {store['name']} ({store['url']})...")
            subprocess.run([
                "python3", "shopify_tracker_actions.py",
                "--url", store['url'],
                "--output-dir", "."
            ], env=env_vars, check=False)
        except Exception as e:
            print(f"  [-] Error checking {store['name']}: {e}")
            
    # Commit and push changes to GitHub if any
    try:
        status = subprocess.check_output(["git", "status", "--porcelain"]).decode('utf-8')
        if status.strip():
            print("  [git] Inventory changes detected! Committing and pushing to GitHub...")
            subprocess.run(["git", "config", "user.name", "Oracle-Tracker-Bot"], check=False)
            subprocess.run(["git", "config", "user.email", "oracle-bot@users.noreply.github.com"], check=False)
            subprocess.run(["git", "add", "-A"], check=False)
            subprocess.run(["git", "commit", "-m", f"Auto-update inventory cache [{now_str}] [skip ci]"], check=False)
            subprocess.run(["git", "push", "origin", "main"], check=False)
        else:
            print("  [git] No inventory changes detected.")
    except Exception as e:
        print(f"  [-] Git push error: {e}")

if __name__ == '__main__':
    print("🚀 24/7 CONTINUOUS SHOPIFY TRACKER SERVICE ACTIVE")
    while True:
        run_tracker_cycle()
        print(f"😴 Sleeping for {INTERVAL_SECONDS} seconds until next cycle...")
        time.sleep(INTERVAL_SECONDS)
