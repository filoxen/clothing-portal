import os

from dotenv import load_dotenv

load_dotenv()

ROBLOSECURITY_TOKEN = os.environ["ROBLOSECURITY_TOKEN"]
PUBLISHER_USER_ID = os.environ["PUBLISHER_USER_ID"]
SECRET_KEY = os.environ["SECRET_KEY"]
ROBLOX_PROXY = os.environ.get("ROBLOX_PROXY", "")
