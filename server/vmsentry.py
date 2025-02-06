import logging
import requests
import os
import sys
import json
import time
from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
from dataclasses import dataclass

# Configure logging (Only write to file, no console output)
LOG_FILE = "vmsentry.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, mode="a")]  # Append mode
)

# Configuration Loader
@dataclass
class Config:
    smtp_packet_threshold: int
    smtp_conn_threshold: int
    smtp_unique_dst_threshold: int
    telegram_api: str
    telegram_chat_id: str
    monitoring_interval: int
    http_timeout: int
    host_file: str  # File containing KVM server hostnames
    suspend_api_url: str  # API endpoint for suspending IPs
    unsuspend_api_url: str  # API endpoint for unsuspending IPs

class ConfigLoader:
    @staticmethod
    def load_config():
        logging.info("Loading configuration...")
        return Config(
            smtp_packet_threshold=5000,
            smtp_conn_threshold=100,
            smtp_unique_dst_threshold=50,
            telegram_api="7611133288:AAGnvY6HLAD-uvGKZEF5iMlrcRymkMdWhSU",
            telegram_chat_id="6995825953",
            monitoring_interval=15,
            http_timeout=20,
            host_file="host.names",
            suspend_api_url="http://{}/suspend_ip",
            unsuspend_api_url="http://{}/unsuspend_ip"
        )

# Monitor Class
class Monitor:
    def __init__(self, config: Config):
        logging.info("Initializing KVM SMTP Monitor...")
        self.config = config
        self.hosts = self.load_hosts()

    def load_hosts(self):
        """Loads the list of KVM servers from the host file."""
        if not os.path.exists(self.config.host_file):
            logging.error(f"Host file {self.config.host_file} not found.")
            return []

        hosts = {}
        with open(self.config.host_file, "r") as f:
            for line in f:
                parts = line.strip().split(" ")
                if len(parts) == 2:
                    hosts[parts[0]] = parts[1].strip('"')
                else:
                    logging.error(f"Invalid entry in host file: {line.strip()}")
        return hosts

    def check_smtp_activity(self, host, friendly_name):
        """Checks SMTP statistics for a specific host."""
        api_url = f"http://{host}:5000/smtp_stats"
        logging.info(f"Checking SMTP stats from {api_url}")

        try:
            start_time = time.time()
            response = requests.get(api_url, timeout=self.config.http_timeout)
            response_time = round(time.time() - start_time, 3)

            if response.status_code != 200:
                logging.warning(f"{friendly_name}: SMTP check failed - HTTP {response.status_code} (Response Time: {response_time}s)")
                return {"alerts": f"{friendly_name}: SMTP check failed - HTTP {response.status_code}", "response_time": response_time}

            data = response.json()
            smtp_data = data.get("data", {})
            logging.info(f"{friendly_name}: Raw SMTP Data: {json.dumps(smtp_data, indent=2)}")

            alert_message = []
            for vps_ip, stats in smtp_data.items():
                if stats["total_packets"] > self.config.smtp_packet_threshold:
                    alert_message.append(f"{friendly_name} ({vps_ip}): High SMTP traffic detected ({stats['total_packets']} packets).")
                    self.suspend_ip(host, vps_ip)
                if stats["syn_packets"] > self.config.smtp_conn_threshold:
                    alert_message.append(f"{friendly_name} ({vps_ip}): High SMTP connections ({stats['syn_packets']} SYNs).")
                    self.suspend_ip(host, vps_ip)
                if stats["unique_dst"] > self.config.smtp_unique_dst_threshold:
                    alert_message.append(f"{friendly_name} ({vps_ip}): High unique mail servers contacted ({stats['unique_dst']}).")
                    self.suspend_ip(host, vps_ip)

            return {"alerts": " | ".join(alert_message) if alert_message else None, "raw_data": smtp_data, "response_time": response_time}

        except requests.exceptions.RequestException as e:
            response_time = round(time.time() - start_time, 3)
            logging.error(f"{friendly_name}: SMTP check request failed after {response_time}s: {e}")
            return {"alerts": f"{friendly_name}: SMTP check request failed: {e}", "response_time": response_time}

    def suspend_ip(self, host, ip):
        """Suspends an IP by sending a request to the API endpoint."""
        logging.info(f"Suspending IP {ip} on {host}")
        url = self.config.suspend_api_url.format(host)
        requests.post(url, json={"ip": ip})

    def unsuspend_ip(self, host, ip):
        """Unsuspends an IP by sending a request to the API endpoint."""
        logging.info(f"Unsuspending IP {ip} on {host}")
        url = self.config.unsuspend_api_url.format(host)
        requests.post(url, json={"ip": ip})

# Main Application
class MonitoringTool:
    def __init__(self, test_mode=False, fetch_mode=False):
        logging.info(f"Initializing MonitoringTool... Test mode: {test_mode}, Fetch mode: {fetch_mode}")
        self.config = ConfigLoader.load_config()
        self.monitor = Monitor(self.config)
        self.scheduler = BlockingScheduler()
        self.test_mode = test_mode
        self.fetch_mode = fetch_mode

    def run_checks(self):
        """Runs monitoring checks for all KVM hosts."""
        logging.info("Running SMTP monitoring checks...")
        for host, friendly_name in self.monitor.hosts.items():
            result = self.monitor.check_smtp_activity(host, friendly_name)
            if self.fetch_mode or self.test_mode:
                self.send_telegram(f"Stats for {friendly_name} ({host}):\n{json.dumps(result, indent=2)}")
            elif result.get("alerts"):
                self.send_telegram(result["alerts"])

    def send_telegram(self, message):
        """Sends alerts via Telegram."""
        try:
            url = f"https://api.telegram.org/bot{self.config.telegram_api}/sendMessage"
            payload = {"chat_id": self.config.telegram_chat_id, "text": message}
            requests.post(url, json=payload)
        except Exception as e:
            logging.error(f"Failed to send Telegram message: {e}")

    def start(self):
        """Starts the monitoring process."""
        if self.fetch_mode:
            self.run_checks()
        else:
            self.scheduler.add_job(self.run_checks, 'interval', minutes=self.config.monitoring_interval)
            self.run_checks()
            self.scheduler.start()

if __name__ == "__main__":
    test_mode = "--test" in sys.argv
    fetch_mode = "--fetch" in sys.argv
    tool = MonitoringTool(test_mode, fetch_mode)
    tool.start()
