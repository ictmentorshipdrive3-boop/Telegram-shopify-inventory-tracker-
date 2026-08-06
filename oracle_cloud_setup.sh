#!/bin/bash
# ==============================================================================
# Oracle Cloud 24/7 Shopify Multi-Store Inventory Tracker Setup Script
# ==============================================================================

set -e

echo "======================================================================"
echo "🚀 STARTING AUTOMATED 24/7 SHOPIFY TRACKER SETUP ON ORACLE CLOUD"
echo "======================================================================"

# 1. Update system packages
echo "[1/5] Updating system packages..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv git curl wget

# 2. Clone/pull repository
REPO_DIR="$HOME/shopify-inventory-tracker"
if [ -d "$REPO_DIR" ]; then
    echo "[2/5] Repository already exists. Pulling latest code..."
    cd "$REPO_DIR"
    git pull origin main
else
    echo "[2/5] Cloned repository from GitHub..."
    git clone https://github.com/ictmentorshipdrive3-boop/Telegram-shopify-inventory-tracker-.git "$REPO_DIR"
    cd "$REPO_DIR"
fi

# 3. Install Python dependencies
echo "[3/5] Installing Python dependencies..."
sudo apt-get install -y python3-pip python3-pandas python3-requests python3-openpyxl

# 4. Create 24/7 Continuous Loop Script
cat << 'EOF' > run_continuous_loop.py
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

INTERVAL_SECONDS = 300  # Run every 5 minutes (Change to 120 for 2-minute checks)

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
EOF

# 5. Create Systemd Service for 24/7 Auto-Restart & Background Execution
echo "[4/5] Creating 24/7 systemd background service..."
SERVICE_FILE="/etc/systemd/system/shopify-tracker.service"

sudo bash -c "cat << EOF > $SERVICE_FILE
[Unit]
Description=24/7 Shopify Inventory Tracker Service
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$REPO_DIR
Environment=\"TELEGRAM_BOT_TOKEN=8711658844:AAEtDHYsx8Mpb5v3LA8vB-v9piJzHGIkHKg\"
Environment=\"TELEGRAM_CHAT_ID=-5393248315\"
ExecStart=/usr/bin/python3 $REPO_DIR/run_continuous_loop.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF"

echo "[5/5] Enabling and starting service..."
sudo systemctl daemon-reload
sudo systemctl enable shopify-tracker.service
sudo systemctl restart shopify-tracker.service

echo "======================================================================"
echo "✅ SETUP COMPLETE! YOUR 24/7 TRACKER IS NOW RUNNING IN ORACLE CLOUD"
echo "  Check Service Status: sudo systemctl status shopify-tracker.service"
echo "  View Real-time Logs:  sudo journalctl -u shopify-tracker.service -f"
echo "======================================================================"
