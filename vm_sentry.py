import subprocess
import configparser
import re
import collections
from datetime import datetime, timedelta
import logging
from logging.handlers import TimedRotatingFileHandler
import sys
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

def setup_logging():
    log_filename = '/etc/vmsentry/logs/vmsentry.log'
    entries_log_filename = '/etc/vmsentry/logs/IP_entries.log'
    when = 'midnight'  # Rotate logs at midnight

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    handler = TimedRotatingFileHandler(log_filename, when=when, interval=7, backupCount=2)
    entries_handler = logging.FileHandler(entries_log_filename)

    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    handler.setFormatter(formatter)
    entries_handler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.addHandler(handler)

    action_logger = logging.getLogger('entries')
    action_logger.addHandler(entries_handler)

# Loading configration file and variables
def load_config():
    logging.info('Loading Configuration file')
    config = configparser.ConfigParser()
    config.read('/etc/vmsentry/config.ini')

    try:
        timeframe = int(config.get('settings', 'timeframe'))
        smtp_threshold = int(config.get('settings', 'smtp_threshold'))
        unique_ips_threshold = int(config.get('settings', 'unique_ips_threshold'))
        mode = config.get('settings', 'mode')
        hash_limit_min = int(config.get('settings', 'hash_limit_min'))
        hash_limit_burst = int(config.get('settings', 'hash_limit_burst'))
        from_addr = config.get('email', 'from_addr')
        to_addr = config.get('email', 'to_addr')
        send_mail = config.getboolean('email', 'send_email')

        # Check if values are positive for certain parameters
        if not all(value > 0 for value in [timeframe, smtp_threshold, unique_ips_threshold, hash_limit_min, hash_limit_burst]):
            raise ValueError("One or more config values are not positive integers.")

        # Check if mode is valid
        if mode not in ['monitor', 'block', 'limit']:
            raise ValueError("Invalid mode in configuration file.")

        # Check if email addresses are not empty
        if not all(addr for addr in [from_addr, to_addr]):
            raise ValueError("One or more email addresses are missing.")

    except (configparser.NoOptionError, configparser.NoSectionError, ValueError) as e:
        logging.error(f"Error in configuration file: {str(e)}. Exiting")
        sys.exit(1)
    
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}. Exiting")
        sys.exit(1)

    return timeframe, smtp_threshold, unique_ips_threshold, mode, hash_limit_min, hash_limit_burst, from_addr, to_addr, send_mail

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

# Parse iptables logs and extract SMTP connexions per IP and unique destination IPs  
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
            timestamp_str, log_message = line.split("kernel:", 1)
            timestamp_str = timestamp_str.strip().rsplit(" ", 1)[0]
            timestamp = datetime.strptime(timestamp_str + ' ' + str(datetime.now().year), "%b %d %H:%M:%S %Y")

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

# Compare the gathered data with the pre-defined thresholds and take the predetermined action
def handle_ip(mode, connections, unique_ips, smtp_threshold, unique_ips_threshold, hash_limit_min, hash_limit_burst, from_addr, to_addr, send_mail):
    action_taken = False
    if is_chain_exists('LOG_AND_DROP'):
        for ip in connections.keys():
            logging.info(f"{ip} has {connections[ip]} connexions for {len(unique_ips[ip])} unique IPs")
            if (connections[ip] > smtp_threshold or len(unique_ips[ip]) > unique_ips_threshold) and not is_ip_blocked(ip):
                action_taken = True
                if mode == 'monitor':
                    logging.info(f"[Monitor] Thresholds reached for {ip}")
                    logging.getLogger('entries').info(f"{ip} has reached the limits but remains unblocked ({connections[ip]} connexions/{len(unique_ips[ip])} unique IPs)")
                elif mode == 'block':
                    block_ip(ip)
                    logging.getLogger('entries').info(f"{ip} is blocked ({connections[ip]} connexions/{len(unique_ips[ip])} unique IPs)")
                elif mode == 'limit':
                    limit_ip(ip, hash_limit_min, hash_limit_burst)
                    logging.getLogger('entries').info(f"{ip} is limited to {hash_limit_min}/min connexions ({connections[ip]} connexions/{len(unique_ips[ip])} unique IPs)")
                if send_mail:
                    send_notification(ip, mode, connections, unique_ips, from_addr, to_addr)
    if not action_taken:
        logging.info("No action were taken during this run")

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

# Check if the iptables chain exists
def is_chain_exists(chain):
    try:
        subprocess.check_output(f'iptables -L {chain} -n', shell=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f'{chain} chain does not exist. Exiting')
        logging.error(f'Error message: {e.output.decode()}')
        raise

# Check if the IP address is already blocked or limited in iptables
def is_ip_blocked(ip, chain='OUTGOING_MAIL'):
    try:
        # Fetch iptables rules specifically for the relevant chain.
        iptables_rules_output = subprocess.check_output(f'iptables -n -L {chain}', shell=True)
        iptables_rules = iptables_rules_output.decode()

        # Split by lines and iterate over them to check if the IP is in any line.
        for line in iptables_rules.split('\n'):
            fields = line.split()
            if len(fields) > 3:  # Ensuring that source IP exists in the line
                if fields[3] == ip:  # Checking if source IP matches the IP we are looking for
                    logging.info(f"IP {ip} is already blocked or limited.")
                    return True

        return False

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

def flush_iptables(chain):
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

def handle_commands(argv):
    if len(argv) > 1:
        command = argv[1]
        if command in ["flush", "--flush"]:
            chain_name = 'OUTGOING_MAIL'  # Replace with the chain name you want to use
            flush_iptables(chain_name)
            return True
        # Add more commands here as elif conditions
        # elif command in ["another_command", "--another_command"]:
        #     another_function()
        #     return True
    return False

# Main function
def main():

    setup_logging()
    logging.info("=================================")
    logging.info("=====Starting to run VMsentry====")
    logging.info("=================================")
    timeframe, smtp_threshold, unique_ips_threshold, mode, hash_limit_min, hash_limit_burst, from_addr, to_addr, send_mail = load_config()
    logging.info("Config.ini file successfully loaded")

    if handle_commands(sys.argv):
        return

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
    logging.info("Program run successfull. Exiting")

if __name__ == '__main__':
    main()