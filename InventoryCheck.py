import time

from bs4 import BeautifulSoup
import requests
from twilio.rest import Client
from playsound import playsound

import secrets  # from secrets.py in this folder
def get_page_html(url):
    headers = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.116 Safari/537.36"}
    page = requests.get(url, headers=headers)
    return page.content


def check_item_in_stock(page_html):
    soup = BeautifulSoup(page_html, 'html.parser')
    out_of_stock_divs = soup.findAll("img", {"class": "oos-overlay hide"})
    return len(out_of_stock_divs) != 0

def setup_twilio_client():
    account_sid = secrets.ACCOUNT_SID
    auth_token = secrets.AUTH_TOKEN
    return Client(account_sid, auth_token)

def send_notification():
    twilio_client = setup_twilio_client()
    twilio_client.messages.create(
        body="Your item is available for purchase.",
        from_=secrets.TWILIO_FROM_NUMBER,
        to=secrets.MY_PHONE_NUMBER
    )
    while True:
        playsound('alarm.mp3')

def check_inventory():
    url = "https://www.costco.com/kitchenaid-professional-series-6-quart-bowl-lift-stand-mixer-with-flex-edge.product.100485356.html"
    page_html = get_page_html(url)
    if check_item_in_stock(page_html):
        send_notification()
    else:
        print("Out of stock still")

while True:
    check_inventory()
    time.sleep(60)  # Wait a minute and try again
