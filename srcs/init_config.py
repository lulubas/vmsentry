import logging
import configparser
from dataclasses import dataclass

@dataclass
class Config:
	timeframe: int
	smtp_connexions_limit: int
	unique_ips_limit: int
	block_timelimit: int
	mode: str
	hash_limit_burst: int
	hash_limit_min: int
	from_addr: str
	to_addr: str
	send_mail: bool

# Loading configration file and variables and return a Config class object
def load_config() -> Config:
	try:
		#Create the config object using the configparser library
		config = configparser.ConfigParser()
		config.read('/etc/vmsentry/config.ini')

		# Use Config class to store the config.ini values
		conf = Config(
			timeframe=int(config.get('settings', 'timeframe')),
			smtp_connexions_limit=int(config.get('settings', 'smtp_connexions_limit')),
			unique_ips_limit=int(config.get('settings', 'unique_ips_limit')),
			block_timelimit=int(config.get('settings', 'block_timelimit')),
			mode=config.get('settings', 'mode'),
			hash_limit_burst=int(config.get('settings', 'hash_limit_burst')),
			hash_limit_min=int(config.get('settings', 'hash_limit_min')),
			send_mail=config.getboolean('email', 'send_email'),
			from_addr=config.get('email', 'from_addr'),
			to_addr=config.get('email', 'to_addr'),
		)

		# Check that each configurations fits into the pre-determined limits
		limits = {
			'timeframe': (1, 240),
			'smtp_connexions_limit': (1, 100000),
			'unique_ips_limit': (1, 10000),
			'block_timelimit': (1, 10000),
			'hash_limit_burst': (1, 2000),
			'hash_limit_min': (1, 2000),
		}

		for limit, (low, high) in limits.items():
			value = getattr(conf, limit)
			if not (low <= value <= high):
				raise ValueError(f"The value for {limit} ({value}) is not within the allowed range ({low}-{high}).")

		# Check if mode is valid
		if conf.mode not in ['monitor', 'block', 'limit']:
			raise ValueError("Invalid mode in configuration file.")

		# Check if email addresses are not empty
		if not all(addr for addr in [conf.from_addr, conf.to_addr]):
			raise ValueError("One or more email addresses are missing.")
		
		logging.info('Configuration file successfully loaded.')

	except (configparser.NoOptionError, configparser.NoSectionError, ValueError) as e:
		logging.error(f"Error in configuration file: {e}")
		raise

	except Exception as e:
		logging.error(f"Error while parsing configuration: {e}")
		raise

	return conf