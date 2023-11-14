import logging
import subprocess
from init_config import Config
from datetime import datetime, timedelta
from ip_manage import list_iptables_ips, list_entries_ips, unblock_ip_iptables, unblock_ip_entries, unblock_ip

# Running initial checks to ensure VM Sentry can run smoothly
def init_checks(config: Config):
	deleted_count = 0
	#Check that iptables chains are valid and that they match IP.list entries
	check_chains()
	check_ip_match()

	#Remove IPs that were blocked for more than block_timelimit hours
	current_time = datetime.now()
	list_ips = list_entries_ips()

	for ip, timestamp in list_ips.items():
		if (current_time - timestamp) > timedelta(hours=config.block_timelimit):
			unblock_ip(ip)
			deleted_count += 1
			logging.info(f'{ip} unblocked after reaching its TTL ({config.block_timelimit} hours)')
	
	logging.info(f'Expired IPs have been removed ({deleted_count} removed)')
	logging.info(f'==INITIALISATION COMPLETED==')

# Checks that the required chains and their required rules exist
def check_chains():
	required_rules = {
		'OUTGOING_MAIL': [
			'-A OUTGOING_MAIL -j LOG --log-prefix "[VMS#0] Logged: "',
		],
		'LOG_AND_DROP': [
			'-A LOG_AND_DROP -j LOG --log-prefix "[VMS#1] Dropped: "',
			'-A LOG_AND_DROP -j DROP',
		]
	}

	for chain, rules in required_rules.items():
		if not is_chain_exists(chain):
			logging.error(f"{chain} chain does not exist.")
			raise
		if not are_rules_present(chain, rules):
			logging.error(f"One or more required rules in {chain} do not exist.")
			raise
	
	logging.info("Iptables chains and relevant rules exist")

# Checks if the chain currently exists in iptables
def is_chain_exists(chain):
	# Search for a specific chain. If it does not exist it return an error
	check_command = f'iptables -L {chain}'
	result = subprocess.run(check_command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
	if result.returncode == 0:
		return True
	else:
		return False

# Check that all the required rules for a specific chain exist
def are_rules_present(chain, rules):
	# Get rules as a string and check that required rules are a substring of it. For now does not check position of the rules.
	try:
		current_rules = subprocess.check_output(f'iptables -S {chain}', shell=True).decode()
		return all(rule in current_rules for rule in rules)

	except subprocess.CalledProcessError as e:
		logging.error(f"Failed to get rules for {chain}. Error message: {e.output.decode()}")

	except Exception as e:
		logging.error(f"An unexpected error occurred while getting rules for {chain}: {e}")

	return False

#Checks consistency between entries in IP.list file and iptables
def check_ip_match():
	iptables_ip = set(list_iptables_ips().keys())
	entries_ip = set(list_entries_ips().keys())

	# Fetch the IP addresses in entries list and iptables
	in_both = iptables_ip & entries_ip
	only_in_iptables = iptables_ip - in_both
	only_in_entries = entries_ip - in_both

	#Unblock orphans IPs from iptables
	for ip in only_in_iptables:
		unblock_ip_iptables(ip)

	#Unblock orphans IPs from the entries log
	for ip in only_in_entries:
		unblock_ip_entries(ip)
	
	logging.info(f"iptables and IP.list are matching")