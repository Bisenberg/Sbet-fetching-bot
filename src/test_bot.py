import logging
import requests
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("Missing Telegram configuration")

def send_telegram_message(text):
    """Send a message via Telegram bot.
    
    Args:
        text: Message text to send
    
    Raises:
        requests.exceptions.RequestException: If the request fails
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        response = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
        response.raise_for_status()
        result = response.json()
        if not result.get("ok"):
            raise RuntimeError(
                f"Telegram API error: {result.get('description', 'Unknown error')}"
            )
        logger.info("Telegram API is reachable")
        return result["result"]
    except requests.exceptions.Timeout:
        logger.error("Telegram API request timed out")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Telegram message: {e}")
        raise

def test_send_telegram_message():
    test_text = "Test message from unit test"
    try:
        send_telegram_message(test_text)
        logger.info("Telegram message sent successfully in test.")
    except Exception as e:
        logger.exception(f"Failed to send Telegram message in test: {e}")
        raise

if __name__ == "__main__":

    test_send_telegram_message()