import asyncio
import json
import os
import smtplib
import time
from email.mime.text import MIMEText

from dotenv import load_dotenv
from playwright.async_api import async_playwright

# Load secure credentials
load_dotenv()

SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
VERIZON_NUMBER = os.getenv("VERIZON_PHONE")
VERIZON_SMS_ADDRESS = f"{VERIZON_NUMBER}@vtext.com"

last_heartbeat_date = ""

def send_verizon_sms(message_body, subject="Jersey Alert"):
    try:
        msg = MIMEText(message_body)
        msg['From'] = SENDER_EMAIL
        msg['To'] = VERIZON_SMS_ADDRESS
        msg['Subject'] = subject

        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, VERIZON_SMS_ADDRESS, msg.as_string())
        server.quit()
        print(f"📱 Text message sent successfully: '{message_body}'")
    except Exception as e:
        print(f"❌ Failed to send text alert: {e}")

def check_morning_heartbeat():
    global last_heartbeat_date
    current_date = time.strftime('%Y-%m-%d')
    current_hour = time.strftime('%H')  # Pulls just the hour (e.g., "08")

    # If it is currently anywhere in the 8:00 AM hour block 
    # AND we haven't already sent a heartbeat text today
    if current_hour == "08" and last_heartbeat_date != current_date:
        print("☀️ Sending daily system status text...")
        send_verizon_sms(
            "🟢 System online. Nike monitor is actively tracking your sizes!", 
            subject="Daily Status"
        )
        # Lock it down for the rest of the day so it doesn't text you again 15 mins later
        last_heartbeat_date = current_date

async def check_nike_store(browser_context, item_name, product_url, target_size):
    print(f"Analyzing Nike backend pipeline for {item_name} (Size: {target_size.upper()})...")
    page = await browser_context.new_page()
    
    # Storage dictionary for capturing the target backend JSON string
    captured_data = {"json": None}
    
    # Event listener to catch Nike's background data threads as they pass by
    async def intercept_response(response):
        if "threads" in response.url or "product_feed" in response.url:
            try:
                text_data = await response.text()
                captured_data["json"] = json.loads(text_data)
            except Exception:
                pass

    page.on("response", intercept_response)
    
    try:
        # Navigate to the product page to trigger the API calls
        await page.goto(product_url, wait_until="networkidle", timeout=60000)
        
        # Give the network capture buffer a few extra moments to process the payload
        await page.wait_for_timeout(3000)
        
        if not captured_data["json"]:
            print(f"⚠️ Could not intercept raw API stream for {item_name}. Falling back to page source extraction lookup...")
            # Fallback block parsing raw page text if network interception was blocked
            content = await page.content()
            if f'"{target_size.upper()}"' in content and '"available":true' in content:
                print(f"🎯 Pattern Match Confirmed in static layer for {item_name} Size {target_size.upper()}!")
                alert = f"🔥 Nike Restock Alert: {item_name} in Size {target_size.upper()} detected active. Link: {product_url}"
                send_verizon_sms(alert)
                return
            else:
                print(f"❌ Size {target_size.upper()} is currently confirmed OUT OF STOCK via structural fallback scan.")
                return

        # Core logic: Process the intercepted API payload block
        try:
            products = captured_data["json"].get("objects", [captured_data["json"]])[0]
            skus = products.get("productInfo", [{}])[0].get("skus", [])
            available_skus = products.get("productInfo", [{}])[0].get("availableSkus", [])
            
            # Map SKU IDs to real human sizes
            sku_id_to_size = {}
            for item in skus:
                sku_id_to_size[item.get("id")] = item.get("nikeSize", "").upper()
                
            size_confirmed_in_stock = False
            for status in available_skus:
                sku_id = status.get("id")
                is_available = status.get("available", False)
                
                mapped_size = sku_id_to_size.get(sku_id, "")
                if mapped_size == target_size.upper() or f"M {target_size.upper()}" in mapped_size:
                    if is_available:
                        size_confirmed_in_stock = True
                        break

            if size_confirmed_in_stock:
                alert = f"🔥 Nike Live Restock: {item_name} in Size {target_size.upper()} IS IN STOCK! Buy now: {product_url}"
                print(f"✅ Success: {alert}")
                send_verizon_sms(alert)
            else:
                print(f"❌ Nike API Verification: {item_name} Size {target_size.upper()} is verified OUT OF STOCK.")
                
        except Exception as json_err:
            print(f"⚠️ Metadata extraction parsing fallback anomaly for {item_name}: {json_err}")
            # Double fallback check
            if f'"{target_size.upper()}"' in str(captured_data["json"]):
                print(f"✅ General fallback pattern hit for {item_name} ({target_size.upper()}). Check site immediately.")
            else:
                print(f"❌ {item_name} Size {target_size.upper()} data missing.")
                
    except Exception as e:
        print(f"⚠️ Nike Tracker Exception occurred on {item_name}: {e}")
    finally:
        await page.close()

async def main():
    tracking_targets = [
        {
            "name": "Replica Home Jersey",
            "url": "https://www.nike.com/t/usmnt-2026-stadium-home-mens-dri-fit-soccer-replica-jersey-udZjfuxa/IB5339-133",
            "size": "XL"
        },
        {
            "name": "Authentic Home Jersey",
            "url": "https://www.nike.com/t/usmnt-2026-match-home-mens-aero-fit-soccer-authentic-jersey-6KUd6sio/IB5183-133", 
            "size": "XL"
        },
        {
            "name": "Replica Away Jersey",
            "url": "https://www.nike.com/t/usmnt-2026-stadium-away-mens-dri-fit-soccer-jersey-udZjfuxa/IB5395-475", 
            "size": "XL"
        }
    ]
    
    print(f"🚀 Nike tracking module initialized with {len(tracking_targets)} items.")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Using a highly detailed real browser profile to sail straight past Akamai security screens
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1,
            is_mobile=False,
            has_touch=False
        )
        
        while True:
            check_morning_heartbeat()
            print(f"\n--- Checking Nike Store Snapshot [{time.strftime('%I:%M:%S %p')}] ---")
            
            for target in tracking_targets:
                await check_nike_store(context, target["name"], target["url"], target["size"])
                # 4-second polite staggered pause between tracking URLs to protect IP reputation
                await asyncio.sleep(4) 
            
            print("\nSnapshot complete for all items. Sleeping for 15 minutes...\n")
            await asyncio.sleep(1800) 

if __name__ == "__main__":
    asyncio.run(main())
    