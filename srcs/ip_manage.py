import logging
from datetime import datetime, timedelta
import subprocess
from utils import is_valid_ip, read_lines_from_file, extract_timestamp_from_log, write_lines_to_file


# Get the list of IPs blocked in iptables and return their rule number
def list_iptables_ips(chain='OUTGOING_MAIL'):
	blocked_ips = {}
	try:
		# Fetch the iptables rules afor the relevant chain (and rule number)
		iptables_rules_output = subprocess.check_output(f'iptables -n -L {chain} --line-numbers', shell=True)
		iptables_rules = iptables_rules_output.decode()

		# Flag we will use to indicate that we reached the rules
		start_looking = False

		# Split by lines and iterate over them to check if the IP is in any line.
		for line in iptables_rules.split('\n'):
			fields = line.split()
			# If the line starts with 'num', it means the next lines will contain the IPs
			if fields and fields[1] == 'LOG':
				start_looking = True
				continue 

			#Check that the line contains the IP field then add the key/value to the dictionnary
			if start_looking:
				if len(fields) > 4:
					rule_number = fields[0]
					ip = fields[4]
					if not is_valid_ip(ip) or not rule_number:
						raise ValueError(f"Wrong IP or rule number in iptables ({line})")
					blocked_ips[ip] = int(rule_number)

	except Exception as e:
		logging.error(f"Error fetching IPs in iptables: {e}")
		raise

	return blocked_ips

# Get the list of IPs blocked in iptables and return their rule number
def list_entries_ips (file_path = '/etc/vmsentry/logs/IP.list'):
	list_ips = {}
	try:
		#Read the IP list file
		entries = read_lines_from_file(file_path)

		for entry in entries:
			ip = read_ip_entry(entry)
			time = extract_timestamp_from_log(entry)
			if not is_valid_ip(ip) or not time:
				raise ValueError(f"Wrong IP or timestamp in IP.list ({entry})")
			list_ips[ip] = time
			
		return list_ips

	except Exception as e:
		logging.error(f'Error getting blocked IP entries: {e}')
		raise

# Exctract the IP address from the IP.list log entries
def read_ip_entry(entry):
	fields = entry.split()
	if len(fields) >= 2:
		ip = fields[3].strip()
		if not is_valid_ip(ip):
			raise ValueError(f"{ip} is not a valid address")
		return ip

#Function to unblock a specific IP address from iptables
def unblock_ip_iptables(ip, chain = 'OUTGOING_MAIL'):
	try:
		list_ip = list_iptables_ips(chain)
		#Exctract the rule number for the IP to unblock
		rule_number = list_ip.get(ip, None)
		if not rule_number:
			logging.error(f"{ip} not found in {chain}")
			return

		#Remove the iptables rule for the desired IP address and check the exit status
		unblock_command = f'iptables -D {chain} {rule_number}'
		result = subprocess.run(unblock_command, shell=True, check=True)
		if result.returncode == 0:
			logging.info(f"{ip} removed from iptables {chain}.")
		else:
			logging.error(f"Unblocking failed for IP {ip}. Command returned {result.returncode}.")
	
	except Exception as e:
		logging.error(f"Unknown error while unblocking {ip}: {e}.")
		raise

#Function to remove the entry of a specific IP address from IP.list
def unblock_ip_entries(ip, file_path = '/etc/vmsentry/logs/IP.list'):
	try:
		entries = read_lines_from_file(file_path)
		filtered_entries = []
		found_flag = False

		for entry in entries:
			if ip != read_ip_entry(entry):
				filtered_entries.append(entry)
			else:
				found_flag = True
				logging.info(f"{ip} removed from {file_path}")
		
		write_lines_to_file(file_path, filtered_entries)

	except Exception as e:
		logging.error(f"An error occurred while removing {ip} from IP.list: {e}.")
		raise

	if not found_flag:
		logging.error(f"{ip} not found in {file_path}")
		return

# Check if the IP address is already blocked or limited in iptables
def is_ip_blocked(ip, chain='OUTGOING_MAIL'):
	#Fetch all the IP addresses from IP 
	
	iptables_ip = set(list_iptables_ips().keys())
	entries_ip = set(list_entries_ips().keys())

	if ip in iptables_ip or ip in entries_ip:
		return True
	else:
		return False

# Unblocks an IP address (both in iptables and IP.list)
def	unblock_ip (ip, chain = 'OUTGOING_MAIL'):
	unblock_ip_iptables(ip, chain)
	unblock_ip_entries(ip)

#Unblocks all the IPs currently present in the chain
def flush_chain(chain = 'OUTGOING_MAIL'):
	#Get the list of the currently blocked IPs
	list_ip = list_iptables_ips(chain)
	try: 
		#iterate over each key (IP address) and unblock it
		for ip in list_ip.keys():
			unblock_ip(ip, chain)
		logging.info(f"{chain} flushed successfully.")

	except Exception as e:
		logging.info(f"An error occurred flushing the iptables chain: {e}")
		raise

# Block an IP address in both iptables and in the IP.list file
def block_ip(ip, reason):
	if is_ip_blocked(ip) is False:
		try:
			#Blocking IP by adding an iptables rule
			block_command = f'iptables -A OUTGOING_MAIL -s {ip} -j LOG_AND_DROP'
			result = subprocess.run(block_command, shell=True, check=True)
			if result.returncode == 0:
				logging.info(f"Added LOG_AND_DROP rule for {ip}.")
				#Logging IP Entry to IP.list file
				logging.getLogger('entries').info(f"{ip} blocked: {reason}")
			else:
				logging.error(f"Blocking failed for {ip}. Command returned {result.returncode}.")

		except Exception as e:
			logging.error(f"Error blocking IP {ip}: {e}")
	else:
		logging.info(f"{ip} already blocked. Skipping.")
		return

# # Limit IP address port 25 access when the threshold is reached
# def limit_ip(ip, hash_limit_min, hash_limit_burst):
#     try:
#         block_command_1 = f'iptables -I OUTGOING_MAIL 2 -s {ip} -p tcp --dport 25 -j LOG_AND_DROP'
#         block_command_2 = f'iptables -I OUTGOING_MAIL 2 -s {ip} -p tcp --dport 25 -m hashlimit --hashlimit {hash_limit_min}/min --hashlimit-burst {hash_limit_burst} --hashlimit-mode srcip --hashlimit-name smtp_limit -j ACCEPT'
#         subprocess.run(block_command_1, shell=True)
#         subprocess.run(block_command_2, shell=True)
#         logging.info(f"IP {ip} access to port 25 has been rate limited.")
#     except Exception as e:
#         logging.error(f"Error limiting IP {ip}: {str(e)}")