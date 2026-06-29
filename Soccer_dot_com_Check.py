import asyncio
import os
import re
import smtplib
import time
from email.mime.text import MIMEText

from dotenv import load_dotenv
from playwright.async_api import async_playwright

# Load your secure credentials
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
    current_time = time.strftime('%H:%M')

    if current_time == "08:00" and last_heartbeat_date != current_date:
        print("☀️ Sending daily system status text...")
        send_verizon_sms("🟢 System online. Soccer.com monitor is actively tracking your sizes!", subject="Daily Status")
        last_heartbeat_date = current_date

async def check_soccer_com(browser_context, item_name, product_url, target_size):
    print(f"Scanning {item_name} for Size: {target_size.upper()}...")
    page = await browser_context.new_page()
    
    try:
        # Load the raw page source structure
        await page.goto(product_url, wait_until="domcontentloaded", timeout=60000)
        page_source = await page.content()
        
        clean_target = target_size.strip().upper()
        
        # Build the pattern matching regex based on the server-side JSON data injection layout
        # This scans the page source code specifically for: "values":"Adult S" or "values":"Adult XL"
        data_pattern = rf'"values"\s*:\s*"Adult\s+{clean_target}"'
        
        if re.search(data_pattern, page_source):
            # To completely verify live inventory status, we make sure the size choice isn't marked 
            # out of stock inside the inventory listing attributes array
            oos_pattern = rf'"values"\s*:\s*"Adult\s+{clean_target}".*?"inventory"\s*:\s*0'
            
            if re.search(oos_pattern, page_source, re.IGNORECASE):
                print(f"❌ {item_name}: Size {clean_target} data found, but inventory is strictly 0.")
            else:
                alert = f"🔥 Soccer.com dropped {item_name} in Size {clean_target}! Order here: {product_url}"
                print(f"✅ IN STOCK: {alert}")
                send_verizon_sms(alert)
        else:
            print(f"❌ {item_name}: Size {clean_target} catalog descriptor block is missing from the source.")
            
    except Exception as e:
        print(f"⚠️ Soccer.com Tracking Error on {item_name}: {e}")
    finally:
        await page.close()

async def main():
    # Define your tracking array targets
    tracking_targets = [
        {
            "name": "Replica Home Jersey",
            "url": "https://www.soccer.com/shop/details/men-s-replica-nike-usmnt-home-jersey-2026_A1128887",
            "size": "XL"  # Your test target size
        },
        {
            "name": "Authentic Home Jersey",
            "url": "https://www.soccer.com/shop/details/men-s-authentic-nike-usmnt-home-jersey-2026_A1128882",
            "size": "XL" # Your actual hunting target size
        }
    ]
    
    print("🚀 Soccer.com dual-jersey monitor online.")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        while True:
            check_morning_heartbeat()
            print(f"\n--- Checking Soccer.com Inventory Loop [{time.strftime('%I:%M:%S %p')}] ---")
            
            for target in tracking_targets:
                await check_soccer_com(context, target["name"], target["url"], target["size"])
                
            print("All items checked. Sleeping for 15 minutes...\n")
            await asyncio.sleep(900) 

if __name__ == "__main__":
    asyncio.run(main())