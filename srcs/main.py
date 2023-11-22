__version__ = '1.0.0'

import logging
import sys
from logger import setup_logging
from init_config import Config, load_config
from init_checks import init_checks
from args import handle_commands
from vm_info import get_vm_info
from action import trigger_limits

def main():
	try:
		setup_logging(__version__)
		config = load_config()
		init_checks(config)
		if handle_commands(__version__, config, sys.argv[1:]):
			return
		vms = get_vm_info(config)
		trigger_limits(vms, config)
		logging.info("Program run successfull. Exiting")

	except Exception as e:
		logging.error(f"Program exited with error: {e}")
		sys.exit(1)

if __name__ == '__main__':
	main()


