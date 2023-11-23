import logging
import argparse
from init_config import Config
from ip_manage import flush_chain, block_ip, unblock_ip
from utils import is_valid_ip, empty_file
from update import update_vmsentry
from vm_info import get_vm_info

#Handler function for arguments passed via CL
def handle_commands(__version__, config: Config, args_raw):
	#Set the different variables needed for the CL commands
	log_dir = '/etc/vmsentry/logs/'
	log_files = [
		'iptables_all_25.log',
		'iptables_dropped_25.log',
		'vmsentry.log'
	]

	#Flag to check if an action was taken
	action_taken = False

	#Use the argparse library to to handle each argument and its function
	try:
		parser = argparse.ArgumentParser(description='VM Sentry monitors port 25 and block IP with unusual traffic')
		
		#--flush-logs should empty all .log files (except install.log) 
		parser.add_argument('--flush-logs', action='store_true', help='Flush log files')
		#--flush-ip should flush all ip whithin the main OUTGOING_MAIL chain (will be updated to flush different chains)
		parser.add_argument('--flush-chain', action='store_true', help='Flush the main chain entirely')
		#--flush-all should flush all logs and ip
		parser.add_argument('--flush-all', action='store_true', help='Flush log files and IP chain')
		#--update should update the script and required files to the latest version (git)
		parser.add_argument('--block-ip', '-b', type=str, help='Block specific IP')
		#--flush-all should flush all logs and ip
		parser.add_argument('--unblock-ip', '-u', type=str, help='Unblock a specific IP')
		#--flush-all should flush all logs and ip
		parser.add_argument('--list', action='store_true', help='Print the current version of VMSentry')
		#--update should update the script and required files to the latest version (git)
		parser.add_argument('--version', action='store_true', help='Print the current version of VMSentry')
		#--update should update the script and required files to the latest version (git)
		parser.add_argument('--update', action='store_true', help='Update to the newest version')

		#Create the argsparser object
		args = parser.parse_args(args_raw)
		
		if args.flush_logs:
			flush_logs(log_files, log_dir)
			action_taken = True

		if args.flush_chain:
				flush_chain()
				action_taken = True

		if args.flush_all:
			flush_chain()
			flush_logs(log_files, log_dir)
			action_taken = True

		if args.block_ip:
			#If it does not come with an additional argument
			if args.block_ip is True:
				logging.error(f"Please specify an IP address to block")
			#If it does come with an additional argument
			else:
				ip_to_block = args.block_ip
				if is_valid_ip(ip_to_block):
					block_ip(ip_to_block, "Manually added via CLI")
				else:
					logging.error(f"{ip_to_block} is not a valid IP address")
			action_taken = True

		if args.unblock_ip:
			#If it does not come with an additional argument
			if args.unblock_ip is True:
				logging.error(f"Please specify an IP address to unblock")
			#If it does come with an additional argument
			else:
				ip_to_unblock = args.unblock_ip
				if is_valid_ip(ip_to_unblock):
					unblock_ip(ip_to_unblock)
				else:
					logging.error(f"{ip_to_unblock} is not a valid IP address")
			action_taken = True

		if args.list:
			get_vm_info(config)
			action_taken = True

		if args.version:
			print(f"VMSentry Version {__version__}")
			action_taken = True
		
		if args.update:
			update_vmsentry()
			action_taken = True

	except Exception as e:
		logging.error(f"Error while handling command: {e}")
		raise
	
	return action_taken

#Go through each log file and empty it
def flush_logs(log_files, log_dir):
	for log_file in log_files:
		file_path = f"{log_dir}{log_file}"
		try:
			empty_file(file_path)
			logging.info(f"{file_path} emptied.")
		except Exception as e:
			logging.error(f"An error occurred while emptying {log_file}: {e}")
			raise
	logging.info("Logs flushed successfully")