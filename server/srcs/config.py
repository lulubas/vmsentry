from logger import logger
import configparser
import os
from dataclasses import dataclass

# Configuration
CONFIG_FILE = "../conf/vmsentry.conf"


@dataclass
class Config:
    smtp_packet_limit: int
    smtp_conn_limit: int
    smtp_unique_dst_limit: int
    monitoring_interval: int
    http_timeout: int
    block_duration: int
    telegram_api: str
    telegram_chat_id: str

class ConfigLoader:
    @staticmethod
    def load_config():
        try :
            #Create the config object and read from the config file
            config = configparser.ConfigParser()
            config.read(CONFIG_FILE)

            conf = Config(
                smtp_packets_limit=int(config.get('Limits', 'smtp_packets_limit')),
                smtp_connections_limit=int(config.get('Limits', 'smtp_connections_limit')),
                smtp_unique_dst_limit=int(config.get('Limits', 'smtp_unique_dst_limit')),
                monitoring_interval=int(config.get('Monitoring', 'monitoring_interval')),
                http_timeout=int(config.get('Monitoring', 'http_timeout')),
                block_duration=int(config.get('Monitoring', 'block_duration')),
                telegram_api=int(config.get('Notification', 'telegram_api')),
                telegram_chat_id=int(config.get('Notification', 'telegram_chat_id')),
            )

            # Check that each configurations fits into the pre-determined limits
            limits = {
                'smtp_packets_limit': (1, 100000),
                'smtp_connections_limit': (1, 100000),
                'smtp_unique_dst_limit': (1, 100000),
                'monitoring_interval': (1, 100000),
                'http_timeout': (1, 100),
                'block_duration': (1, 1000),
            }

            for limit, (low, high) in limits.items():
                value = getattr(conf, limit)
                if not (low <= value <= high):
                    raise ValueError(f"The value for {limit} ({value}) is not within the allowed range ({low}-{high}).")

        except Exception as e:
            logging.error(f"Error while parsing configuration: {e}")
            raise

		logging.info('Configuration file successfully loaded.')