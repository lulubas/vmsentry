from config import Config
import requests

#Notification Class
class Notification:
	def __init__(self, logger, config: Config):
		self.config = config
		self.logger = logger
		
	def send_message(self, message):
		"""Sends a notification message via Telegram."""
		url = f"https://api.telegram.org/bot{self.config.telegram_api}/sendMessage"
		payload = {
			'chat_id': self.config.telegram_chat_id,
			'text': message
		}
		
		try:
			response = requests.post(url, json=payload)
			response.raise_for_status()

		except requests.RequestException as e:
			raise Exception(f"Failed to send telegram message using url {url}: {e}")
		
		self.logger.info(f"Message '{message}' sent via telegram")