"""
Extract from medium.com "using-python-to-send-telegram-messages-in-3-simple-steps"

2. Getting your chat ID

In Telegram, every chat has a chat ID, and we need this chat ID to send Telegram messages using Python.

    Send your Telegram bot a message (any random message)
    Run this Python script to find your chat ID

import requests
TOKEN = "YOUR TELEGRAM BOT TOKEN"
url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
print(requests.get(url).json())

This script calls the getUpdates function, which kinda checks for new messages. We can find our chat ID from the returned JSON (the one in red)

Note: if you don’t send your Telegram bot a message, your results might be empty.

3. Copy and paste the chat ID into our next step
3. Sending your Telegram message using Python

Copy and paste 1) your Telegram bot token and 2) your chat ID from the previous 2 steps into the following Python script. (And do customize your message too)

import requests
TOKEN = "YOUR TELEGRAM BOT TOKEN"
chat_id = "YOUR CHAT ID"
message = "hello from your telegram bot"
url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={chat_id}&text={message}"
print(requests.get(url).json()) # this sends the message
"""
