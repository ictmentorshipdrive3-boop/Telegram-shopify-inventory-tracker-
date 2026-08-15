import os
import subprocess
import sys

REPO_URL = "https://github.com/ictmentorshipdrive3-boop/Telegram-shopify-inventory-tracker-"
SUITE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SUITE_DIR, "data")

def sync_data():
    print("==================================================")
    print("  SYNCING LATEST 24/7 TRACKING LOGS FROM GITHUB   ")
    print("==================================================")
    
    if os.path.exists(os.path.join(DATA_DIR, ".git")):
        print(f"Updating existing repository in: {DATA_DIR}")
        try:
            res = subprocess.run(["git", "pull", "origin", "main"], cwd=DATA_DIR, check=True, capture_output=True, text=True)
            print(res.stdout)
            print("[+] Successfully pulled latest tracking logs!")
        except Exception as e:
            print(f"Error updating repo via git pull: {e}")
    else:
        print(f"Cloning tracking repository into: {DATA_DIR}")
        try:
            res = subprocess.run(["git", "clone", REPO_URL, DATA_DIR], check=True, capture_output=True, text=True)
            print(res.stdout)
            print("[+] Successfully cloned repository!")
        except Exception as e:
            print(f"Error cloning repository: {e}")

    # Also check parent downloads repo if present
    parent_repo = os.path.join(os.path.dirname(SUITE_DIR), "shopify-inventory-tracker-github")
    if os.path.exists(os.path.join(parent_repo, ".git")):
        try:
            subprocess.run(["git", "pull", "origin", "main"], cwd=parent_repo, capture_output=True, text=True)
        except Exception:
            pass

if __name__ == '__main__':
    sync_data()
