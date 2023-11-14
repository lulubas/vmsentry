__version__ = '1.0.0'

import logging
import sys
import argparse
from logger import setup_logging
from init_config import Config, load_config
from init_checks import init_checks
from args import handle_commands

# import subprocess
# import re
# import collections
# import smtplib
# from email.mime.multipart import MIMEMultipart
# from email.mime.text import MIMEText

#Main function#
def main():
	try:
		setup_logging(__version__)
		config = load_config()
		init_checks(config)
		handle_commands(__version__, sys.argv[1:])

		# logging.info("Fetching VM names and IP addresses")
		# vms = get_vms()
		# running_vms = get_running_vms(vms)
		# vm_ips = get_vm_ips(running_vms)
		# logging.info(f'Fetching successfull. Total VPS: {len(vms)}, {len(running_vms)} running')

		# logging.info(f"Parsing logs file more recent than {timeframe} hours")
		# connections, unique_ips = parse_logs(timeframe)
		# logging.info("Logs parsed successfully")

		# logging.info("Taking actions against IP addresses over quotas...")
		# handle_ip(config.mode, connections, unique_ips, config.smtp_threshold, config.unique_ips_threshold, config.hash_limit_min, hash_limit_burst, from_addr, to_addr, send_mail)
		
		# logging.info("Removing IPs from iptables if they expired")
		# expire_ip(block_timelimit)        
		# logging.info("Program run successfull. Exiting")

	except Exception as e:
		logging.error(f"Program exited with error: {e}")
		sys.exit(1)

if __name__ == '__main__':
	main()
