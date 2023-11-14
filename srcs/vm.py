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
                        block_ip(ip, connections, unique_ips)
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