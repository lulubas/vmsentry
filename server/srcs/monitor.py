from config import Config
import os
import requests
import json
from datetime import datetime, timedelta


# Monitor Class
class Monitor:
    def __init__(self, logger, config: Config):
        self.logger = logger
        self.logger.info("Initializing KVM SMTP Monitor...")
        self.config = config
        self.host_file = "../conf/host.names"
        self.blocked_file = "blocked_ips.json"
        self.hosts = self.load_hosts()
        self.blocked_ips = self.load_blocked_ips()

    def load_hosts(self):
        """Loads the list of remote hosts from the host file."""
                
        if not os.path.exists(self.host_file):
            self.logger.error(f"Host file {self.host_file} not found.")
            return {}

        hosts = {}
        with open(self.host_file, "r") as f:
            for line in f:
                parts = line.strip().split(" ")
                if len(parts) == 2:
                    hosts[parts[0]] = parts[1].strip('"')
                else:
                    self.logger.error(f"Invalid entry in host file: {line.strip()}")
        return hosts

    def load_blocked_ips(self):
        """Loads a record of blocked IPs with timestamps."""
        blocked_ips = {}
        if os.path.exists(self.blocked_file):
            with open(self.blocked_file, "r") as f:
                try:
                    blocked_ips = json.load(f)
                except json.JSONDecodeError:
                    self.logger.warning("Blocked IPs file is corrupted. Starting from blank")
        return blocked_ips

    def save_blocked_ips(self):
        """Saves the blocked IPs with timestamps."""
        with open(self.blocked_file, "w") as f:
            json.dump(self.blocked_ips, f, indent=2)
    
    def check_all_hosts(self):
        """Calls for monitoring and action dispatchers on hosts"""
        #Iterates over each host to fetch SMTP data
        for host in self.hosts:
            try:
                smtp_data = self.fetch_smtp_activity(host)

                #iterates over each IP that has SMTP traffic and take actions if necessary
                for ip, stats in smtp_data.items():
                    to_suspend = False
                    
                    if stats["total_packets"] > self.config.smtp_packets_limit:
                        self.logger.info(f"{ip} exceeds packet limit: {stats['total_packets']} > {self.config.smtp_packets_limit}")
                        to_suspend = True
                    
                    if stats["syn_packets"] > self.config.smtp_connections_limit:
                        self.logger.info(f"{ip} exceeds connections limit: {stats['syn_packets']} > {self.config.smtp_connections_limit}")
                        to_suspend = True
                    
                    if stats["unique_dst"] > self.config.smtp_unique_dst_limit:
                        self.logger.info(f"{ip} exceeds unique destinations limit: {stats['unique_dst']} > {self.config.smtp_unique_dst_limit}")
                        to_suspend = True
                    
                    if to_suspend:
                        self.suspend_ip(host, ip)
        
                #Delete IPs that reached their TTL
                for ip in list(self.blocked_ips.keys()):
                    if self.should_unsuspend(ip):
                        self.logger.info(f"{host}: IP {ip} blocked for more than {self.config.block_duration} hours. Unsuspending.")
                        self.unsuspend_ip(host, ip)

            except Exception as e:
                self.logger.error(f"{host}: Failed to fetch SMTP data: {e}")
        
                
    def fetch_smtp_activity(self, host):
        """Checks SMTP statistics for a specific host."""
        url = f"http://{host}:5000/smtp_stats"

        self.logger.info(f"Checking SMTP stats from {url}")
        
        #Fetch data from remote server endpoint and raise if status not 200
        try:
            response = requests.get(url, timeout=self.config.http_timeout)
            response.raise_for_status()  # Automatically raises an exception for non-200 responses
        except requests.RequestException as e:
            raise Exception(f"Failed to reach {url}: {e}")

        data = response.json()
        self.logger.info(f"{host} SMTP_INFO API Response: {data}")

        #Stop execution if remote server returned error
        if (data.get("status") != "OK"):
            raise Exception(f"Remote server failed to return SMTP logs : {data.get('message')}")

        smtp_data = data.get("data", {})
        return smtp_data


    def suspend_ip(self, host, ip):
        """Suspends an IP and logs the response."""

        #Return if IP already blocked
        if ip in self.blocked_ips:
            self.logger.info(f"IP {ip} is already blocked (date: {self.blocked_ips[ip]})")
            return
        
        url = f"http://{host}:5000/suspend_ip/{ip}"
        self.logger.info(f"Suspending IP from {url}")

        try:
            response = requests.get(url, timeout=self.config.http_timeout)
            response.raise_for_status()  # Automatically raises an exception for non-200 responses
        except requests.RequestException as e:
            raise Exception(f"Failed to reach {url}: {e}")

        data = response.json() 
        self.logger.info(f"Suspend API Response: {data}")

        #Stop execution if remote server returned error
        if (data.get("status") != "OK"):
            raise Exception(f"Remote server failed to suspend IP {ip} : {data.get("message")}")
        self.logger.info(f"IP {ip} has been suspended")

        #Add the blocked IP and timestamp to the tracker file
        self.blocked_ips[ip] = datetime.now().isoformat()
        self.save_blocked_ips()
        self.logger.info(f"IP {ip} has been added to the blocked IP logfile")

    def should_unsuspend(self, ip):
        """Checks if an IP should be unblocked based on time."""
        if ip not in self.blocked_ips:
            return False
        try:
            blocked_time = datetime.fromisoformat(self.blocked_ips[ip])
        except ValueError:  # Handles corrupted timestamps
            self.logger.warning(f"Corrupted timestamp for {ip}, removing from blocked list.")
            self.blocked_ips.pop(ip, None)
            self.save_blocked_ips()
            return False
        
        max_age = timedelta(hours=self.config.block_duration)
        return datetime.now() >= (blocked_time + max_age)

    def unsuspend_ip(self, host, ip):
        """Unsuspends an IP and logs the response."""
        if ip not in self.blocked_ips:
            self.logger.info(f"IP {ip} does not appear currently blocked (logfile)")
            return

        url = f"http://{host}:5000/unsuspend_ip/{ip}"
        self.logger.info(f"Unuspending IP from {url}")

        try:
            response = requests.get(url, timeout=self.config.http_timeout)
            response.raise_for_status()  # Automatically raises an exception for non-200 responses
        except requests.RequestException as e:
            raise Exception(f"Failed to reach {url}: {e}")

        data = response.json() 
        self.logger.info(f"Suspend API Response: {json.dumps(data)}")

        #Stop execution if remote server returned error
        if (data.get("status") != "OK"):
            raise Exception(f"Remote server failed to suspend IP {ip} : {data.get("message")}")
        self.logger.info(f"IP {ip} has been unsuspended")

        #Removed the blocked IP and timestamp to the tracker file
        self.blocked_ips.pop(ip, None)
        self.save_blocked_ips()
