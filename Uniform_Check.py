import os
import smtplib
import time
from email.mime.text import MIMEText

import requests
from dotenv import load_dotenv
from twilio.rest import Client

# ==========================================
# ⚙️ CONFIGURATION SETTINGS
# ==========================================

WATCHLIST = [
    {
        "store": "store.ussoccer.com",
        "handle": "usasmz2604-mens-nike-usmnt-2026-stripes-stadium-jersey",
        "size": "XL"
    },
    {
        "store": "store.ussoccer.com",
        "handle": "usasmz2604-mens-nike-usmnt-2026-stripes-stadium-jersey",
        "size": "L"
    },
    {
        "store": "store.ussoccer.com",
        "handle": "usasmz2601-mens-nike-usmnt-2026-stars-stadium-jersey",
        "size": "XL"
    },
    {
        "store": "store.ussoccer.com",
        "handle": "usasmz2601-mens-nike-usmnt-2026-stars-stadium-jersey",
        "size": "L"
    }
]

STORE_DOMAIN = "store.ussoccer.com"

load_dotenv()

def setup_twilio_client():
    """Safely initializes Twilio using your .env configuration file."""
    twilio_account_sid = os.environ['twilio_account_sid']
    twilio_auth_token = os.environ['twilio_auth_token']
    return Client(twilio_account_sid, twilio_auth_token)

TWILIO_PHONE_NUMBER = "+19163475683"   
YOUR_CELL_PHONE_TWILIO = "+19168478711" 

SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
VERIZON_NUMBER = os.getenv("VERIZON_PHONE")
VERIZON_SMS_ADDRESS = f"{VERIZON_NUMBER}@vtext.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# ==========================================
# 📱 RE-DEFINED GLOBAL & NOTIFICATION FUNCTIONS
# ==========================================

# Initializing here directly above functions keeps it cleanly in Python's global namespace
last_heartbeat_date = ""

def check_morning_heartbeat():
    global last_heartbeat_date
    current_date = time.strftime('%Y-%m-%d')
    current_hour = time.strftime('%H')  # Pulls just the hour block (e.g., "08")

    # Verify if it is in the 8:00 AM window and has not sent today
    if current_hour == "08" and last_heartbeat_date != current_date:
        print("☀️ Sending daily system status text...")
        # Fixed: Removed the 'subject' parameter because send_alerts() only accepts message_body
        send_alerts("🟢 System online. US Soccer monitor is actively tracking your sizes!")
        last_heartbeat_date = current_date

def send_alerts(message_body, subject="Stock Alert"):
    """Fires alerts to Twilio and Verizon simultaneously with distinct naming."""
    
    # --- Channel 1: Twilio API Text ---
    try:
        twilio_sms_runner = setup_twilio_client()
        twilio_sms_runner.messages.create(
            body=message_body,
            from_=TWILIO_PHONE_NUMBER,
            to=YOUR_CELL_PHONE_TWILIO
        )
        print("📱 Twilio premium SMS dispatched successfully!")
    except Exception as e:
        print(f"❌ Twilio Error: {e}")

    # --- Channel 2: Verizon Gateway ---
    msg = MIMEText(message_body)
    msg["From"] = SENDER_EMAIL
    msg["To"] = VERIZON_SMS_ADDRESS
    msg["Subject"] = subject
    
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, VERIZON_SMS_ADDRESS, msg.as_string())
        server.quit()
        print("📨 Verizon Gateway email dispatched successfully!")
    except Exception as e:
        print(f"❌ Verizon Gateway Error: {e}")

# ==========================================
# 🔍 CORE SCRAPER LOGIC
# ==========================================

def check_stock(store_domain, product_handle, target_size):
    url = f"https://{store_domain}/api/2024-07/graphql.json"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    
    graphql_query = """
    query getProductInventory($handle: String!) {
      product(handle: $handle) {
        title
        variants(first: 100) {
          edges {
            node {
              title
              availableForSale
            }
          }
        }
      }
    }
    """
    
    payload = {"query": graphql_query, "variables": {"handle": product_handle}}
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code != 200:
            print(f"⚠️ Shopify API error ({response.status_code})")
            return None
            
        res_data = response.json()
        product_data = res_data["data"]["product"]
        
        if not product_data:
            print(f"⚠️ Product handle '{product_handle}' not found.")
            return None
            
        product_title = product_data["title"]
        variants = product_data["variants"]["edges"]
        
        # 🔍 DEBUG BLOCK: Let's see exactly what Shopify calls these sizes!
        print(f"\n--- [DEBUG] Available text titles for {product_title}: ---")
        for edge in variants:
            print(f" -> Shopify Name: '{edge['node']['title']}' | Live Status: {'In Stock' if edge['node']['availableForSale'] else 'Sold Out'}")
        print("-------------------------------------------------------\n")
        
        for edge in variants:
            variant = edge["node"]
            
            if target_size.strip().lower() == variant["title"].strip().lower():
                return {
                    "title": product_title,
                    "actual_size_name": variant["title"],
                    "in_stock": variant["availableForSale"]
                }
                
    except Exception as e:
        print(f"⚠️ Error scanning {product_handle}: {e}")
    
    return None

# ==========================================
# 🔄 THE AUTOMATION LOOP
# ==========================================

if __name__ == "__main__":
    print(f"🚀 Starting monitor for {len(WATCHLIST)} items...")
    print("Checking every 15 minutes. Press Ctrl+C to stop.\n")
    
    # 900 seconds = 15 minutes
    INTERVAL_SECONDS = 900 
    
    while True:
        # Run the morning status check
        check_morning_heartbeat()

        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"--- [ Run Cycle: {current_time} ] ---")
        
        for item in WATCHLIST:
            print(f"Checking: {item['handle']} (Size: {item['size']})...")
            
            result = check_stock(item["store"], item["handle"], item["size"])
            
            if result:
                if result["in_stock"]:
                    item_url = f"https://{item['store']}/products/{item['handle']}"
                    alert_msg = f"🔥 IN STOCK: {result['title']} (Size: {result['actual_size_name']}) is available! {item_url}"
                    
                    print("🚨 MATCH FOUND! Sending notifications...")
                    send_alerts(alert_msg)
                else:
                    print("❌ Sold Out.")
            else:
                print("⏭️ Skipping due to an error fetching data.")
                
            time.sleep(2)
            
        print("Finished cycle. Sleeping for 15 minutes...\n")
        time.sleep(INTERVAL_SECONDS)