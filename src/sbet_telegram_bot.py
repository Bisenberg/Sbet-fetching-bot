
from datetime import datetime
import os, time, hashlib, json, pathlib, logging, requests, sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.wait import WebDriverWait
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("sbet_telegram_bot")

load_dotenv()

def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        logger.error("Missing required environment variable: %s", name)
        sys.exit(1)
    return value

TELEGRAM_TOKEN = require_env('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = require_env('TELEGRAM_CHAT_ID')
LOGIN_URL = require_env('LOGIN_URL')
SBET_URL = require_env('SBET_URL')
LOGIN_USER = require_env('SBET_USER')
LOGIN_PASS = require_env('SBET_PWD')
MATCH_ARRAY = ['SennuM40','U15 pojat', 'U14 pojat', 'U13 pojat','U12 pojat', 'U11 pojat', 'U10 pojat', 'U9 pojat', 'U8 pojat', 
            'U9 pojat', 'U8 pojat', 'U14 tytöt', 'U13 tytöt', 'U12 tytöt', 'U11 tytöt', 'U10 tytöt', 'U9 tytöt', 'U8 tytöt']

INFO_LINES = 7
WAIT_SECONDS = 10
TELEGRAM_MAX_LENGTH = 4096

SEEN_FILE = pathlib.Path('seen_matches.json')

USERNAME_ID = "ContentPlaceHolder1_LoginForm_UserName"
PASSWORD_ID = "ContentPlaceHolder1_LoginForm_Password"
SIGNIN_ID = "ContentPlaceHolder1_LoginForm_SignInButton"
GRID_ID = "ContentPlaceHolder1_MatchListGrid"
# Rows that do NOT contain the "forward" icon, selected in one query.
ROW_XPATH = (
    f"//*[@id='{GRID_ID}']//tr"
    "[not(.//i[contains(@class, 'glyphicon-forward')])]"
)

def load_seen():
    if SEEN_FILE.exists():
        with open(SEEN_FILE, 'r', encoding='utf-8') as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(seen), f)

def filter_new_matches(matches, seen):
    new_matches = []
    for match in matches:
        match_hash = hashlib.md5(match.encode('utf-8')).hexdigest()
        if match_hash not in seen:
            new_matches.append(match)
            seen.add(match_hash)
    return new_matches

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
        resp.raise_for_status()

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Telegram message")
        raise
    logger.info("Telegram message sent")

def login_and_fetch():
    options = Options()
    options.add_argument("-headless")
    driver = webdriver.Firefox(options=options)
    try:
        driver.get(LOGIN_URL)
        driver.find_element(By.XPATH, '//*[@id="ContentPlaceHolder1_LoginForm_UserName"]')\
            .send_keys(LOGIN_USER)
        driver.find_element(By.XPATH, '//*[@id="ContentPlaceHolder1_LoginForm_Password"]')\
            .send_keys(LOGIN_PASS)
        driver.find_element(By.XPATH, '//*[@id="ContentPlaceHolder1_LoginForm_SignInButton"]')\
            .click()
        time.sleep(2)  
        driver.get(SBET_URL)
        time.sleep(2)

        listings = driver.find_elements(By.CSS_SELECTOR, '#ContentPlaceHolder1_MatchListGrid tr')
        logger.info(f'Listings found: {len(listings)}')
        found = []
        for idx, listing in enumerate(listings):
            forward_icon = listing.find_elements(
                By.CSS_SELECTOR,
                'i.glyphicon.glyphicon-forward'
            )
            if forward_icon:
                logger.info(f"Skipping row {idx}: Forward icon found")
                continue
            text = listing.text
            logger.info(f'Row {idx}: {text}')
            for item in MATCH_ARRAY:
                if item in text:
                    logger.info(f"Match found for '{item}' in row {idx}")
                    found.append(text)
                    break
        if found:
            filtered = parse_matches(found)
            return filtered
        else:
            print('No matches found.')
    finally:
        driver.quit()

def parse_matches(found):
    messages = []
    for item in found:
        lines = item.splitlines()

        info_lines = lines[:7]
        message = '\n'.join(info_lines)
        messages.append(message)
    logger.info(f'Parsed messages: {messages}')
    return messages

def scheduled_job():
    matches = login_and_fetch()
    if matches:
        logger.info("Suitable options found:")
        for idx, msg in enumerate(matches, 1):
            logger.info(f"{idx}. {msg}")
        user_input = input("Send these matches as a Telegram message? (y/n): ").strip().lower()
        if user_input == 'y':
            combined_message = '\n\n'.join(matches)
            send_telegram_message(combined_message)
            logger.info("Message sent.")
        else:
            logger.info("Message not sent.")

def main():
    scheduled_job() 
    scheduler = BackgroundScheduler()
    scheduler.add_job(scheduled_job, 'interval', hours=1,
                    max_instances=1, coalesce=True, next_run_time=datetime.now())
    scheduler.start()

    print('Bot started. Press Ctrl+C to exit.')

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        scheduler.shutdown()
        print('Bot stopped.')

if __name__ == "__main__":
    main()