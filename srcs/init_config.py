import logging
import configparser
from dataclasses import dataclass

@dataclass
class Config:
	timeframe: int
	smtp_connections_limit: int
	unique_ips_limit: int
	block_timelimit: int
	block_ip: bool
	send_email: bool
	from_smtp_host: str
	from_smtp_port: int
	from_email_addr: str
	from_email_pw: str
	to_recipient: str
	send_telegram: bool
	telegram_api: str
	telegram_chat_id: str

# Loading configration file and variables and return a Config class object
def load_config() -> Config:
	try:
		#Create the config object using the configparser library
		config = configparser.ConfigParser()
		config.read('/etc/vmsentry/config.ini')

		# Use Config class to store the config.ini values
		conf = Config(
            timeframe=int(config.get('settings', 'timeframe')),
            smtp_connections_limit=int(config.get('settings', 'smtp_connections_limit')),
            unique_ips_limit=int(config.get('settings', 'unique_ips_limit')),
            block_timelimit=int(config.get('settings', 'block_timelimit')),
            block_ip=config.getboolean('settings', 'block_ip'),
            send_email=config.getboolean('email', 'send_email'),
            from_smtp_host=config.get('email', 'from_smtp_host'),
            from_smtp_port=int(config.get('email', 'from_smtp_port')),
            from_email_addr=config.get('email', 'from_email_addr'),
            from_email_pw=config.get('email', 'from_email_pw'),
            to_recipient=config.get('email', 'to_recipient'),
            send_telegram=config.getboolean('telegram', 'send_telegram'),
            telegram_api=config.get('telegram', 'telegram_api'),
            telegram_chat_id=config.get('telegram', 'telegram_chat_id')
        )

		# Check that each configurations fits into the pre-determined limits
		limits = {
			'timeframe': (1, 240),
			'smtp_connections_limit': (1, 100000),
			'unique_ips_limit': (1, 10000),
			'block_timelimit': (1, 10000),
		}

		for limit, (low, high) in limits.items():
			value = getattr(conf, limit)
			if not (low <= value <= high):
				raise ValueError(f"The value for {limit} ({value}) is not within the allowed range ({low}-{high}).")
		
		logging.info('Configuration file successfully loaded.')

	except (configparser.NoOptionError, configparser.NoSectionError, ValueError) as e:
		logging.error(f"Error in configuration file: {e}")
		raise

	except Exception as e:
		logging.error(f"Error while parsing configuration: {e}")
		raise

	return conf