import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
 
import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
 
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("sbet_bot")
 
load_dotenv() 
 
 
def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        logger.error("Missing required environment variable: %s", name)
        sys.exit(1)
    return value
 
 
TELEGRAM_TOKEN = require_env("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = require_env("TELEGRAM_CHAT_ID")
LOGIN_URL = require_env("LOGIN_URL")
SBET_URL = require_env("SBET_URL")
LOGIN_USER = require_env("SBET_USER")
LOGIN_PASS = require_env("SBET_PWD")
 
MATCH_TERMS = (
    "SennuM40",
    "U15 pojat", "U14 pojat", "U13 pojat", "U12 pojat",
    "U11 pojat", "U10 pojat", "U9 pojat", "U8 pojat",
    "U14 tytöt", "U13 tytöt", "U12 tytöt", "U11 tytöt",
    "U10 tytöt", "U9 tytöt", "U8 tytöt",
)
_MATCH_TERMS_FOLDED = tuple(term.casefold() for term in MATCH_TERMS)
 
INFO_LINES = 7               
WAIT_SECONDS = 15             
TELEGRAM_MAX_LEN = 4096
SEEN_FILE = Path(__file__).with_name("seen.json")
 
USERNAME_ID = "ContentPlaceHolder1_LoginForm_UserName"
PASSWORD_ID = "ContentPlaceHolder1_LoginForm_Password"
SIGNIN_ID = "ContentPlaceHolder1_LoginForm_SignInButton"
GRID_ID = "ContentPlaceHolder1_MatchListGrid"

# Rows that do NOT contain the forward icon.
ROW_XPATH = (
    f"//*[@id='{GRID_ID}']//tr"
    "[not(.//i[contains(@class, 'glyphicon-forward')])]"
)
 
 
class LoginError(RuntimeError):
    pass
 
 
def send_telegram_message(text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException:
        logger.error("Failed to send Telegram message")
        raise
    logger.info("Telegram message sent")
 
 
def chunk_messages(messages: list[str], sep: str = "\n\n") -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    current_len = 0
    for msg in messages:
        msg = msg[:TELEGRAM_MAX_LEN]
        added = len(msg) + (len(sep) if current else 0)
        if current and current_len + added > TELEGRAM_MAX_LEN:
            chunks.append(current)
            current, current_len, added = [], 0, len(msg)
        current.append(msg)
        current_len += added
    if current:
        chunks.append(current)
    return chunks
 
def _digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()
 
 
def load_seen() -> set[str]:
    try:
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return set()
    except (json.JSONDecodeError, OSError):
        logger.warning("Could not read %s, starting with an empty seen-list", SEEN_FILE)
        return set()
 
 
def save_seen(seen: set[str]) -> None:
    tmp = SEEN_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(sorted(seen)), encoding="utf-8")
    tmp.replace(SEEN_FILE)
 
 

def make_driver() -> webdriver.Firefox:
    options = Options()
    options.add_argument("-headless")
    return webdriver.Firefox(options=options)
 
 
def login(driver: webdriver.Firefox, wait: WebDriverWait) -> None:
    driver.get(LOGIN_URL)
    wait.until(EC.presence_of_element_located((By.ID, USERNAME_ID)))
    driver.find_element(By.ID, USERNAME_ID).send_keys(LOGIN_USER)
    driver.find_element(By.ID, PASSWORD_ID).send_keys(LOGIN_PASS)
    button = driver.find_element(By.ID, SIGNIN_ID)
    button.click()
    try:
        # A successful login navigates away, so the old button goes stale.
        wait.until(EC.staleness_of(button))
    except TimeoutException as exc:
        raise LoginError("Login page did not navigate after sign-in") from exc
 
 
def fetch_rows() -> list[str]:
    driver = make_driver()
    try:
        wait = WebDriverWait(driver, WAIT_SECONDS)
        login(driver, wait)
 
        driver.get(SBET_URL)
        try:
            wait.until(EC.presence_of_element_located((By.ID, GRID_ID)))
        except TimeoutException as exc:
            if driver.find_elements(By.ID, USERNAME_ID):
                raise LoginError("Redirected back to the login form") from exc
            raise
 
        rows = driver.find_elements(By.XPATH, ROW_XPATH)
        logger.info("Rows considered: %d", len(rows))
        return [row.text for row in rows]
    finally:
        driver.quit()
 
 
def is_match(text: str) -> bool:
    folded = text.casefold()
    return any(term in folded for term in _MATCH_TERMS_FOLDED)
 
 
def parse_match(row_text: str) -> str:
    return "\n".join(row_text.splitlines()[:INFO_LINES])
 
 
def find_matches() -> list[str]:
    return [parse_match(text) for text in fetch_rows() if text.strip() and is_match(text)]
 

_login_alert_sent = False
 
 
def run_check(dry_run: bool = False) -> None:
    global _login_alert_sent
    try:
        matches = find_matches()
        _login_alert_sent = False
    except LoginError as exc:
        logger.error("Login failed: %s", exc)
        if not _login_alert_sent and not dry_run:
            try:
                send_telegram_message(f"SBET bot: login failed ({exc}). Check credentials/site.")
                _login_alert_sent = True  # don't repeat the alert every hour
            except requests.exceptions.RequestException:
                pass
        return
    except Exception:
        logger.exception("Fetching matches failed")
        return
 
    seen = load_seen()
    new = [m for m in matches if _digest(m) not in seen]
    logger.info("Matches: %d total, %d new", len(matches), len(new))
    if not new:
        return
 
    if dry_run:
        for i, msg in enumerate(new, 1):
            logger.info("[dry-run] new match %d:\n%s", i, msg)
        return
 
    for chunk in chunk_messages(new):
        try:
            send_telegram_message("\n\n".join(chunk))
        except requests.exceptions.RequestException:
            logger.error("Stopping; unsent matches will be retried on the next run")
            break
        seen.update(_digest(m) for m in chunk)
        save_seen(seen)
 
 
def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="print new matches without sending or marking them seen")
    parser.add_argument("--once", action="store_true", help="run a single check and exit")
    args = parser.parse_args()
 
    logger.info("Starting (%d match terms, dry_run=%s)", len(MATCH_TERMS), args.dry_run)
 
    if args.once:
        run_check(dry_run=args.dry_run)
        return
 
    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_check,
        "interval",
        hours=1,
        kwargs={"dry_run": args.dry_run},
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(), 
    )
    logger.info("Scheduler running. Press Ctrl+C to exit.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
 
 
if __name__ == "__main__":
    main()
 