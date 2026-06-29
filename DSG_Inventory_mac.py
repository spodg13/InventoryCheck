import time

# from bs4 import BeautifulSoup
import bs4
import re
import requests
import schedule
import os
from playsound import playsound
from twilio.rest import Client

Instock = False


# import secrets  # from secrets.py in this folder
def get_page_html(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/83.0.4103.116 Safari/537.36"}
    page = requests.get(url, headers=headers)
    return page.content


def check_item_in_stock(page_html):
    soup = bs4.BeautifulSoup(page_html, 'html.parser')
    out_of_stock_divs = soup.findAll(text=re.compile('^NOTIFY ME WHEN'))
    print(out_of_stock_divs)
    return len(out_of_stock_divs) != 0


def setup_twilio_client():
    twilio_account_sid = os.environ['twilio_account_sid']
    twilio_auth_token = os.environ['twilio_auth_token']
    return Client(twilio_account_sid, twilio_auth_token)


# numbers_to_message = ['+19168478711','+19165813044']
# for number in numbers_to_message:

def send_notification(msg):
    numbers_to_message = ['+19168478711']  # , '+19165813044', '+19169323845']
    for number in numbers_to_message:
        print(number)
        twilio_client = setup_twilio_client()
        twilio_client.messages.create(
            body=msg,
            from_='+19163475683',
            to=number
        )


def running_reminder():
    print("I'm working...")
    msg = "Dick's Sporting Goods: Daily Reminder" + chr(10) + "Barbell check still running every 5 minutes"
    send_notification(msg)


def check_inventory():
    url = "https://www.dickssportinggoods.com/p/fitness-gear-300-lbolympic-weight-set-16fgeu300lbstwth7brb/16fgeu300lbstwth7brb"
    # Basketball in stock Folsom url ="https://www.dickssportinggoods.com/p/wilson-official-encore-basketball-29-5
    # -19wilancrcmpst295bkb/19wilancrcmpst295bkb?Clearance=false"
    page_html = get_page_html(url)
    t = time.localtime()
    global Instock
    current_time = time.strftime("%b %d %Y, %I:%M:%S %p", t)
    if check_item_in_stock(page_html):
        # send_notification()
        print("Out of Stock")
        print(current_time)
        if Instock:
            msg = "No longer in stock, " + chr(10) + current_time
            send_notification(msg)
            Instock = False
    else:
        print("In stock")
        print(current_time)
        Instock = 1
        msg = "Brendon the barbell is in stock: " + chr(10) + current_time + chr(10) + url
        send_notification(msg)


schedule.every().day.at("13:13").do(running_reminder)
# playsound('/School_bell.mp3')
while True:
    check_inventory()
    schedule.run_pending()
    time.sleep(300)  # Wait (seconds) and try again
