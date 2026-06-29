import asyncio
import os
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
        send_verizon_sms("🟢 System online. WorldSoccerShop monitor is actively tracking your sizes!", subject="Daily Status")
        last_heartbeat_date = current_date

async def check_world_soccer_shop(browser_context, product_url, target_size):
    print(f"Opening WorldSoccerShop page to scan for Size: {target_size.upper()}...")
    page = await browser_context.new_page()
    
    try:
        # Load the live page
        await page.goto(product_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000) # Wait for inventory scripts to finish loading
        
        clean_target = target_size.strip().upper()
        
        # 1. LIVE ELEMENT SCAN: Pull every interactive sizing element on the live screen
        size_buttons = await page.query_selector_all("button, label, .size-option, [data-automation-id*='size']")
        stock_confirmed = False
        element_found = False
        
        for button in size_buttons:
            btn_text = (await button.inner_text()).strip().upper()
            
            # Match "S", "SMALL", or "ADULT S" fields on screen
            is_match = (
                btn_text == clean_target or 
                (clean_target == "S" and btn_text == "SMALL") or
                btn_text == f"ADULT {clean_target}"
            )
            
            if is_match:
                element_found = True
                is_disabled = await button.get_attribute("disabled")
                is_aria_disabled = await button.get_attribute("aria-disabled")
                classes = await button.get_attribute("class") or ""
                
                # Check if the element contains any out-of-stock indicators
                oos_indicators = ["disabled", "oos", "out-of-stock", "unavailable", "strike", "disabled-option"]
                has_oos_class = any(indicator in classes.lower() for indicator in oos_indicators)
                
                if not is_disabled and is_aria_disabled != "true" and not has_oos_class:
                    stock_confirmed = True
                    print(f"🎯 LIVE STOCK CONFIRMED! Size {clean_target} button is active and clickable.")
                    break
                else:
                    print(f"👁️ Size {clean_target} button found, but it is currently GRAYED OUT / DISABLED.")

        # 2. FINAL EVALUATION: Only trigger the alert if the size is active and buyable
        if element_found and stock_confirmed:
            alert = f"🔥 WorldSoccerShop: Size {clean_target} is IN STOCK and buyable! Order here: {product_url}"
            print(f"✅ Success: {alert}")
            send_verizon_sms(alert)
        elif element_found and not stock_confirmed:
            print(f"❌ Size {clean_target} is currently sold out (grayed out on screen).")
        else:
            print(f"❌ Could not find any visual layout elements for size {clean_target} on the page.")
            
    except Exception as e:
        print(f"⚠️ Scraping execution error: {e}")
    finally:
        await page.close()

async def main():
    wss_jersey_url = "https://www.worldsoccershop.com/shop/details/men-s-replica-nike-usmnt-home-jersey-2026_A1128887"
    desired_size = "S" # Change this string to "S", "M", "L", or "XL" to swap targets
    
    print("🚀 WorldSoccerShop page-source metadata monitor online.")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        while True:
            check_morning_heartbeat()
            print(f"\n--- Verifying WorldSoccerShop Inventory Snapshot [{time.strftime('%I:%M:%S %p')}] ---")
            await check_world_soccer_shop(context, wss_jersey_url, desired_size)
            print("Snapshot clear. Pausing for 5 minutes...\n")
            await asyncio.sleep(300) 

if __name__ == "__main__":
    asyncio.run(main())