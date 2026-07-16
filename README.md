# Shopify Inventory Tracker (GitHub Actions Edition)

This repository is configured to run an automated inventory and sales tracker for **The Amethyst Store** (or any Shopify store) every 15 minutes using GitHub Actions. It polls the store, updates the logs, and sends instant **Telegram notifications with images and prices** whenever an item sells out!

---

## 🛠️ Step-by-Step Setup Guide

Follow these simple steps to deploy this tracker to your own GitHub account:

### 1. Create a Telegram Bot (For Notifications)
1. Open Telegram and search for the `@BotFather`.
2. Send the command `/newbot` and follow the instructions to name your bot.
3. Save the **HTTP API Bot Token** provided by `@BotFather` (looks like `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`).
4. Start a conversation with your new bot (click the link `@your_bot_name` and press **Start**).

### 2. Find Your Telegram Chat ID
1. Search for `@userinfobot` on Telegram.
2. Send any message to it, and it will reply with your **Id** (a number like `987654321`).
3. Copy this **Id**.

### 3. Create a GitHub Repository
1. Go to [github.com](https://github.com/) and create a new **Private** repository (e.g., `shopify-inventory-tracker`).
2. Do **not** initialize it with a README, `.gitignore`, or license.

### 4. Push This Directory to GitHub
Open a terminal (command prompt or PowerShell) in this folder and run:

```bash
# Initialize git repository
git init

# Add all files
git add .

# Commit baseline configuration
git commit -m "Initialize shopify inventory tracker"

# Rename branch to main
git branch -M main

# Add your GitHub remote URL (replace with your repository link)
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/shopify-inventory-tracker.git

# Push files to GitHub
git push -u origin main
```

### 5. Add GitHub Repository Secrets
To keep your Telegram bot credentials secure, add them as GitHub Secrets:
1. Go to your repository page on GitHub.
2. Click on **Settings** (top tabs) -> **Secrets and variables** (left menu) -> **Actions**.
3. Click the green **New repository secret** button.
4. Add the following secrets:
   * **Name**: `TELEGRAM_BOT_TOKEN`  
     **Value**: (Paste your Bot Token from `@BotFather`)
   * **Name**: `TELEGRAM_CHAT_ID`  
     **Value**: (Paste your Telegram ID from `@userinfobot`)

---

## 🚀 How It Runs
* **Automated Schedule**: GitHub Actions will automatically run the script every **15 minutes** using the cron schedule.
* **Telegram Alerts**: Whenever an item is found to be sold out, your Telegram bot will instantly message you a photo, product name, price/rate, and a link to the page.
* **Persistent Logs**: All inventory data changes are saved to `theamethyststore_com_live_sales_log.csv` and committed back to your repository automatically.
