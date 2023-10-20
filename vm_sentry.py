import subprocess
import configparser
from dataclasses import dataclass
import re
import collections
from datetime import datetime, timedelta
import logging
import sys
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

@dataclass
class Config:
    timeframe: int
    block_timelimit: int
    smtp_threshold: int
    unique_ips_threshold: int
    mode: str
    hash_limit_min: int
    hash_limit_burst: int
    from_addr: str
    to_addr: str
    send_mail: bool

#Setting up the logger
def setup_logging():

    #Set the limit (days) for how long to keep logs
    log_limit = 30
    
    try:
        log_filename = '/etc/vmsentry/logs/vmsentry.log'
        entries_log_filename = '/etc/vmsentry/logs/IP_entries.log'
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s', datefmt="%b %d %H:%M:%S")

        # Setting up main logger
        handler = logging.FileHandler(log_filename)
        handler.setFormatter(formatter)
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)

        # Setting up logger for IP entries
        entries_handler = logging.FileHandler(entries_log_filename)
        entries_handler.setFormatter(formatter)
        action_logger = logging.getLogger('entries')
        action_logger.setLevel(logging.INFO)
        action_logger.addHandler(entries_handler)

        logging.info("VMSentry logger setup successfully") 

        # Rotating logs using a 30 days limit by default
        rotate_logs(log_filename, log_limit)
                    
        logging.info(f"Logs older than {log_limit} days were deleted")
    
    except Exception as e:
        raise RuntimeError(f"An error occurred while setting up the logger: {e}")
        
def rotate_logs(file_path, limit):
    try:
        #Open the log file to rotate and parse it
        with open(file_path, 'r') as f:
            logs = f.readlines()
        
        #Iterate over each log line and only keep the ones that do not need to rotate
        logs = [log for log in logs if not is_log_rotate(log, limit)]

        #Write the logs to the file (overriding)
        with open(file_path, 'w') as f:
            f.writelines(logs)

    except Exception as e:
        raise RuntimeError(f"An error occurred while rotating logs: {e}")

def is_log_rotate(log_line, limit, log_time_format="%b %d %H:%M:%S"):
    try:
        #Strip out the date/hour from the log line
        timestamp_logstr = " ".join(log_line.split()[:3])

        #Add the year and construct a timestamp object for the log
        current_year = datetime.now().year
        timestamp = datetime.strptime(f"{current_year} {timestamp_logstr}", f"%Y {log_time_format}")

        #Return True/False if the log is younger/older than the limit set (days)
        return datetime.now() - timestamp >= timedelta(days=limit)
    
    except Exception as e:
        logging.error(f"An error occurred while checking if log ({log_line}) has expired: {e}")
        return False

# Loading configration file and variables and return a Config class object
def load_config() -> Config:
    try:
        #Create the config object using the configparser library
        config = configparser.ConfigParser()
        config.read('/etc/vmsentry/config.ini')

        # Use Config class to store the config.ini values
        conf = Config(
            timeframe=int(config.get('settings', 'timeframe')),
            block_timelimit=int(config.get('settings', 'block_timelimit')),
            smtp_threshold=int(config.get('settings', 'smtp_threshold')),
            unique_ips_threshold=int(config.get('settings', 'unique_ips_threshold')),
            mode=config.get('settings', 'mode'),
            hash_limit_min=int(config.get('settings', 'hash_limit_min')),
            hash_limit_burst=int(config.get('settings', 'hash_limit_burst')),
            from_addr=config.get('email', 'from_addr'),
            to_addr=config.get('email', 'to_addr'),
            send_mail=config.getboolean('email', 'send_email')
        )

        # Check if values are positive for certain parameters
        if not all(value > 0 for value in [conf.timeframe, conf.block_timelimit, conf.smtp_threshold, conf.unique_ips_threshold, conf.hash_limit_min, conf.hash_limit_burst]):
            raise ValueError("One or more config values are not positive integers.")

        # Check if mode is valid
        if conf.mode not in ['monitor', 'block', 'limit']:
            raise ValueError("Invalid mode in configuration file.")

        # Check if email addresses are not empty
        if not all(addr for addr in [conf.from_addr, conf.to_addr]):
            raise ValueError("One or more email addresses are missing.")
        
        logging.info('Configuration file successfully loaded.')

    except (configparser.NoOptionError, configparser.NoSectionError, ValueError) as e:
        raise RuntimeError(f"Error in configuration file: {str(e)}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error: {str(e)}")

    return conf

def init_checks():
    required_chains = ['OUTGOING_MAIL', 'LOG_AND_DROP']
    if not all(is_chain_exists(chain) for chain in required_chains):
        raise RuntimeError("One or more required chains do not exist.")
    
# Check if the iptables chain exists
def is_chain_exists(chain):
    try:
        subprocess.check_output(f'iptables -L {chain} -n', shell=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f'{chain} chain does not exist. Exiting')
        logging.error(f'Error message: {e.output.decode()}')
        raise

# Fetch the list of all guest VMs
def get_vms():

    vms_output = subprocess.check_output('virsh list --all | grep -v -E \'^-|Id|^$\' | awk \'{print $2}\'', shell=True)
    vms = vms_output.decode().split('\n')
    vms = list(filter(None, vms))

    return vms

# Trim the list of VMs with only the running ones
def get_running_vms(vms):

    running_vms = []

    for vm in vms:
        try:
            state_output = subprocess.check_output('virsh domstate {}'.format(vm), shell=True)
            state = state_output.decode().strip()

            if state == 'running':
                running_vms.append(vm)

        except Exception as e:
            logging.error(f'Error fetching status for VM {vm}: {str(e)}. Skipping.')
            return
            
    return running_vms

# Associate VMs to their IP address
def get_vm_ips(running_vms):

    vm_ips = {}

    for vm in running_vms:
        try:
            mac_output = subprocess.check_output('virsh domiflist {} | awk \'{{ print $5}}\' | tail -2 | head -1'.format(vm), shell=True)
            mac = mac_output.decode().strip()
            ip_output = subprocess.check_output('ip neigh | grep {} | awk \'{{print $1}}\''.format(mac), shell=True)
            ip = ip_output.decode().strip()
            vm_ips[vm] = ip

        except Exception as e:
            logging.error(f'Error fetching IP for VM {vm}: {str(e)}. Skipping.')
            return
    
    if len(running_vms) != len(vm_ips):
        logging.error(f"Not all VMs have an associated IP address. VM: {len(running_vms)}, VMs with IP: {len(vm_ips)}. Exiting")
        sys.exit(1)

    return vm_ips

# Parse iptables logs and extract SMTP connections per IP and unique destination IPs  
def parse_logs(timeframe_hours):
    try:
        with open("/etc/vmsentry/logs/iptables_all_25.log") as f:
            lines = f.readlines()
        if not lines:
            logging.error('iptables_all_25.log file is empty. Please wait until logs start being generated. Exiting')
            sys.exit(1)
    except FileNotFoundError:
        logging.error('iptables_all_25.log file does not exist (yet). You might need to wait until logs are generated. Exiting.')
        sys.exit(1)
    except Exception as e:
        logging.error(f'Unexpected error when reading iptables_all_25.log: {str(e)}. Exiting.')
        sys.exit(1)

    pattern = r"SRC=(?P<src>\S+) DST=(?P<dst>\S+) .* DPT=25"
    timeframe = datetime.now() - timedelta(hours=timeframe_hours)
    connections = collections.defaultdict(int)
    unique_ips = collections.defaultdict(set)

    for line in lines:
        try:
            timestamp = parse_time(line)
            _, log_message = line.split("kernel:", 1)

            if timestamp > timeframe:
                match = re.search(pattern, log_message)
                if match:
                    src = match.group("src")
                    dst = match.group("dst")
                    connections[src] += 1
                    unique_ips[src].add(dst)
        except Exception as e:
            logging.error(f'Unexpected error while parsing the line "{line}": {str(e)}. Skipping.')
            continue

    return connections, unique_ips

def parse_time (string):
    try:
        timestamp_elements = string.split()[:3]  # Get first three elements
        timestamp_str = " ".join(timestamp_elements)
        timestamp = datetime.strptime(timestamp_str + ' ' + str(datetime.now().year), "%b %d %H:%M:%S %Y")
        return timestamp
    except Exception as e:
        logging.error(f"Could not extract timestamp: {e}")
        return None

# Compare the gathered data with the pre-defined thresholds and take the predetermined action
def handle_ip(mode, connections, unique_ips, smtp_threshold, unique_ips_threshold, hash_limit_min, hash_limit_burst, from_addr, to_addr, send_mail):
    action_taken = False

    # Fetch all VMs
    all_vms = get_vms()
    
    # Fetch running VMs
    running_vms = get_running_vms(all_vms)
    
    # Fetch IP addresses for running VMs
    running_vm_ips = get_vm_ips(running_vms)

    for vm in all_vms:
        if vm in running_vms:
            ip = running_vm_ips.get(vm, "N/A")
            if ip in connections:
                logging.info(f"{vm} ({ip}) | {connections[ip]} connections to {len(unique_ips[ip])} unique IPs")
                if (connections[ip] > smtp_threshold or len(unique_ips[ip]) > unique_ips_threshold) and not is_ip_blocked(ip):
                    action_taken = True
                    if mode == 'monitor':
                        logging.info(f"[Monitor] Thresholds reached for {ip}")
                        logging.getLogger('entries').info(f"{ip} has reached the limits but remains unblocked ({connections[ip]} connections/{len(unique_ips[ip])} unique IPs)")
                    elif mode == 'block':
                        block_ip(ip)
                        logging.getLogger('entries').info(f"{ip} is blocked ({connections[ip]} connections/{len(unique_ips[ip])} unique IPs)")
                    elif mode == 'limit':
                        limit_ip(ip, hash_limit_min, hash_limit_burst)
                        logging.getLogger('entries').info(f"{ip} is limited to {hash_limit_min}/min connections ({connections[ip]} connections/{len(unique_ips[ip])} unique IPs)")
                    if send_mail:
                        send_notification(ip, mode, connections, unique_ips, from_addr, to_addr)
            else:
                logging.info(f"{vm} ({ip}) | No connection logged")
        else:
            logging.info(f"{vm} : Not running")
            
    if not action_taken:
        logging.info("No actions were taken during this run")

# Send a mail notification when the threshold is reached
def send_notification(ip, mode, connections, unique_ips, from_addr, to_addr):
    try:
        msg = MIMEMultipart()
        msg['From'] = from_addr
        msg['To'] = to_addr
        msg['Subject'] = f'VMsentry Alert: IP {ip} exceeded threshold'
        
        body = f'IP: {ip}\nSMTP Connections: {connections[ip]}\nUnique IPs: {unique_ips[ip]}\nMode of action: {mode}'
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('localhost')
        server.sendmail(msg['From'], msg['To'], msg.as_string())
        server.quit()

        logging.info(f"Notification sent to {to_addr} for IP {ip}")

    except Exception as e:
        logging.error(f"Error sending notification: {str(e)}")

# Check if the IP address is already blocked or limited in iptables
def is_ip_blocked(ip, chain='OUTGOING_MAIL'):
    try:
        # Fetch iptables rules specifically for the relevant chain, with the rule number
        iptables_rules_output = subprocess.check_output(f'iptables -n -L {chain} --line-numbers', shell=True)
        iptables_rules = iptables_rules_output.decode()

        # Flag to indicate if we should start looking for IPs
        start_looking = False

        # Split by lines and iterate over them to check if the IP is in any line.
        for line in iptables_rules.split('\n'):
            fields = line.split()

             # If the line starts with 'num', it means the next lines will contain the IPs
            if fields and fields[0] == 'num':
                start_looking = True
                continue  # skip the current line

            if start_looking:
                if len(fields) > 4:  # Ensuring that source IP exists in the line
                    rule_number = fields[0]
                    rule_ip = fields[4]

                    if rule_ip == ip:  # Checking if source IP matches the IP we are looking for
                        logging.info(f"IP {ip} is currently blocked or limited.")
                        return int(rule_number)

        logging.info(f"IP {ip} is currently not blocked nor limited.")
        return 0

    except Exception as e:
        logging.error(f"Error checking if IP {ip} is blocked: {str(e)}. Exiting.")
        raise

# Block IP address port 25 access when the threshold is reached
def block_ip(ip):
    try:
        block_command = f'iptables -A OUTGOING_MAIL -s {ip} -j LOG_AND_DROP'
        subprocess.run(block_command, shell=True)
        logging.info(f"Blocking IP {ip}.")
    except Exception as e:
        logging.error(f"Error blocking IP {ip}: {str(e)}")

# Limit IP address port 25 access when the threshold is reached
def limit_ip(ip, hash_limit_min, hash_limit_burst):
    try:
        block_command_1 = f'iptables -I OUTGOING_MAIL 2 -s {ip} -p tcp --dport 25 -j LOG_AND_DROP'
        block_command_2 = f'iptables -I OUTGOING_MAIL 2 -s {ip} -p tcp --dport 25 -m hashlimit --hashlimit {hash_limit_min}/min --hashlimit-burst {hash_limit_burst} --hashlimit-mode srcip --hashlimit-name smtp_limit -j ACCEPT'
        subprocess.run(block_command_1, shell=True)
        subprocess.run(block_command_2, shell=True)
        logging.info(f"IP {ip} access to port 25 has been rate limited.")
    except Exception as e:
        logging.error(f"Error limiting IP {ip}: {str(e)}")

def expire_ip(block_timelimit):
    log_file_path = "/etc/vmsentry/logs/IP_entries.log"
    try:
        with open(log_file_path) as f:
            lines = f.readlines()
        if not lines:
            logging.info('No IP address seem blocked at the moment')
            return
    except FileNotFoundError:
        logging.error('IP_entries.log not found. You might need to wait until the first IP gets blocked for the file to generate')
        return
    except Exception as e:
        logging.error(f'Unexpected error when reading IP_entries.log: {str(e)}. Continuing.')
        return

    pattern = r"INFO (?P<ip>\S+) is"
    timeframe = datetime.now() - timedelta(hours=block_timelimit)

    for line in lines:
        try:
            timestamp = parse_time(line)

            if timestamp < timeframe:
                match = re.search(pattern, line)
                if match:
                    ip = match.group("ip")
                    unblock_ip(ip)
                    remove_line_from_file(log_file_path, line)  # remove the line from the file
        except Exception as e:
            logging.error(f' entry log "{line}": {str(e)}. Skipping.')
            continue
    return True

def remove_line_from_file(filename, line_to_remove):
    with open(filename, "r+") as f:
        lines = f.readlines()
        f.seek(0)  # move file pointer to the beginning of the file
        f.truncate(0)  # truncate the file to empty it

        for line in lines:
            if line.strip("\n") != line_to_remove.strip("\n"):
                f.write(line)

def unblock_ip(ip):
    rule_number = is_ip_blocked(ip)
    try:
        block_command = f'iptables -D OUTGOING_MAIL {rule_number}'
        result = subprocess.run(block_command, shell=True, check=True)  # Check exit status
        if result.returncode == 0:  # Successfully unblocked
            logging.info(f"Unblocked IP {ip}.")
        else:
            logging.error(f"Unblocking failed for IP {ip}. Command returned {result.returncode}.")
    except subprocess.CalledProcessError:
        logging.error(f"Error unblocking IP {ip}. Command failed.")
    except Exception as e:
        logging.error(f"Unexpected error unblocking IP {ip}: {str(e)}")

def flush_chain(chain):
    try:
        # Count the total number of LOG_AND_DROP entries
        result = subprocess.run(['iptables', '-n', '-L', chain], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        total_entries = result.stdout.count("LOG_AND_DROP")

        # Since we want to keep the first entry, we start removing from the second entry
        for _ in range(total_entries):
            subprocess.run(['iptables', '-D', 'OUTGOING_MAIL', '2'])

        logging.info("Successfully flushed iptables entries.")
    except Exception as e:
        logging.error(f"An error occurred: {e}")

def flush_logs(log_files, log_dir):
    for log_file in log_files:
        full_path = f"{log_dir}{log_file}"
        try:
            with open(full_path, 'w'):
                pass
            logging.info(f"Successfully emptied {log_file}.")
        except Exception as e:
            logging.error(f"An error occurred while emptying {log_file}: {e}")

def handle_commands(argv):
    chain_name = 'OUTGOING_MAIL'  # Replace with the chain name you want to use
    log_dir = '/etc/vmsentry/logs/'
    log_files = [
                'IP_entries.log',
                'iptables_all_25.log',
                'iptables_dropped_25.log',
                'vmsentry.log'
    ]
    if len(argv) > 1:
        command = argv[1]
        if command in ["flush-chain", "--flush-chain"]:
            logging.info(f"Flushing the chain{chain_name}")
            flush_chain(chain_name)
            sys.exit(1)
        elif command in ["flush-logs", "--flush-logs"]:
            logging.info("Flushing log files")
            flush_logs(log_files, log_dir)
            sys.exit(1)
        elif command in ["flush-all", "--flush-all"]:
            logging.info("Flushing log files and iptables chains")
            flush_chain(chain_name)
            flush_logs(log_files, log_dir)
            sys.exit(1)
    return False

# Main function
def main():
    try: 
        setup_logging()
        logging.info("==== Starting to run VMsentry ===")
        config = load_config()
        logging.info("Config.ini file successfully loaded")

        handle_commands(sys.argv)
        
        logging.info("Performing intial checks")
        init_checks()

        logging.info("Fetching VM names and IP addresses")
        vms = get_vms()
        running_vms = get_running_vms(vms)
        vm_ips = get_vm_ips(running_vms)
        logging.info(f'Fetching successfull. Total VPS: {len(vms)}, {len(running_vms)} running')

        logging.info(f"Parsing logs file more recent than {timeframe} hours")
        connections, unique_ips = parse_logs(timeframe)
        logging.info("Logs parsed successfully")

        logging.info("Taking actions against IP addresses over quotas...")
        handle_ip(mode, connections, unique_ips, smtp_threshold, unique_ips_threshold, hash_limit_min, hash_limit_burst, from_addr, to_addr, send_mail)
        
        logging.info("Removing IPs from iptables if they expired")
        expire_ip(block_timelimit)        
        logging.info("Program run successfull. Exiting")

    except RuntimeError as e:
        logging.error(f"Initial checks failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()