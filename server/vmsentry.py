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

class ConfigLoader:
    @staticmethod
    def load_config():
        logging.info("Loading configuration...")
        return Config(
            smtp_packet_threshold=5000,  # Max allowed packets per VPS
            smtp_conn_threshold=100,  # Max SMTP connections (SYN packets)
            smtp_unique_dst_threshold=50,  # Max unique mail servers contacted
            telegram_api="7611133288:AAGnvY6HLAD-uvGKZEF5iMlrcRymkMdWhSU",
            telegram_chat_id="6995825953",
            monitoring_interval=20,  # In minutes
            http_timeout=20,  # Alert sent if response time is 75% of timeout
            host_file="host.names"  # File containing hostnames
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

        with open(self.config.host_file, "r") as f:
            return [line.strip() for line in f if line.strip()]

    def check_smtp_activity(self, host):
        """Checks SMTP statistics for a specific host."""
        api_url = f"http://{host}:5000/smtp_stats"
        logging.info(f"Checking SMTP stats from {api_url}")

        try:
            start_time = time.time()  # Start time before request
            response = requests.get(api_url, timeout=self.config.http_timeout)
            response_time = round(time.time() - start_time, 3)  # Measure response duration (seconds)

            if response.status_code != 200:
                logging.warning(f"{host}: SMTP check failed - HTTP {response.status_code} (Response Time: {response_time}s)")
                return {
                    "alerts": f"{host}: SMTP check failed - HTTP {response.status_code}",
                    "response_time": response_time
                }

            data = response.json()
            if data.get("status") != "OK":
                logging.warning(f"{host}: Flask API error: {data.get('error', 'Unknown Error')}")
                return {
                    "alerts": f"{host}: Flask API error: {data.get('error', 'Unknown Error')}",
                    "response_time": response_time
                }

            smtp_data = data.get("data", {})
            logging.info(f"{host}: Raw SMTP Data: {json.dumps(smtp_data, indent=2)}")

            alert_message = []

            for vps_ip, stats in smtp_data.items():
                if stats["total_packets"] > self.config.smtp_packet_threshold:
                    alert_message.append(f"{host} ({vps_ip}): High SMTP traffic detected ({stats['total_packets']} packets).")
                if stats["syn_packets"] > self.config.smtp_conn_threshold:
                    alert_message.append(f"{host} ({vps_ip}): High SMTP connections ({stats['syn_packets']} SYNs).")
                if stats["unique_dst"] > self.config.smtp_unique_dst_threshold:
                    alert_message.append(f"{host} ({vps_ip}): High unique mail servers contacted ({stats['unique_dst']}).")

            return {
                "alerts": " | ".join(alert_message) if alert_message else None,
                "raw_data": smtp_data,
                "response_time": response_time
            }

        except requests.exceptions.RequestException as e:
            response_time = round(time.time() - start_time, 3)
            logging.error(f"{host}: SMTP check request failed after {response_time}s: {e}")
            return {
                "alerts": f"{host}: SMTP check request failed: {e}",
                "response_time": response_time
            }

# Main Application
class MonitoringTool:
    def __init__(self, test_mode=False):
        logging.info(f"Initializing MonitoringTool... Test mode: {test_mode}")
        self.config = ConfigLoader.load_config()
        self.monitor = Monitor(self.config)
        self.scheduler = BlockingScheduler()
        self.test_mode = test_mode

    def run_checks(self):
        """Runs monitoring checks for all KVM hosts."""
        logging.info("Running SMTP monitoring checks...")
        for host in self.monitor.hosts:
            result = self.monitor.check_smtp_activity(host)

            # Extract alerts and raw data
            health_alert = result.get("alerts")
            raw_data = result.get("raw_data")
            response_time = result.get("response_time")

            if self.test_mode:
                message = f"Test Mode: SMTP Data for {host}\nResponse time ={response_time}s\n{json.dumps(raw_data, indent=2)}"
                logging.info(f"Test Mode - Sending full data via Telegram for {host}")
                self.send_telegram(message)

            if health_alert:
                logging.info(f"Sending SMTP alert via Telegram for {host}")
                self.send_telegram(health_alert)

        # After each check, clear old logs
        self.clear_old_logs()

    def send_telegram(self, message):
        """Sends alerts via Telegram."""
        try:
            url = f"https://api.telegram.org/bot{self.config.telegram_api}/sendMessage"
            payload = {"chat_id": self.config.telegram_chat_id, "text": message}
            response = requests.post(url, json=payload)

            if response.status_code != 200:
                logging.error(f"Telegram API error: {response.status_code}, Response: {response.text}")
        except Exception as e:
            logging.error(f"Failed to send Telegram message: {e}")

    def clear_old_logs(self):
        """Deletes log entries older than 7 days without affecting new logs."""
        if not os.path.exists(LOG_FILE):
            return

        seven_days_ago = datetime.now() - timedelta(days=7)
        log_lines = []

        with open(LOG_FILE, "r") as file:
            for line in file:
                try:
                    log_timestamp = datetime.strptime(line.split(" | ")[0], "%Y-%m-%d %H:%M:%S")
                    if log_timestamp >= seven_days_ago:
                        log_lines.append(line)
                except ValueError:
                    log_lines.append(line)  # Keep any malformed lines

        # Write back only recent logs (without replacing file instantly)
        with open(LOG_FILE, "w") as file:
            file.writelines(log_lines)

    def start(self):
        """Starts the monitoring process."""
        logging.info(f"Starting KVM SMTP Monitoring Tool (Test Mode: {self.test_mode})...")
        self.scheduler.add_job(self.run_checks, 'interval', minutes=self.config.monitoring_interval)
        self.run_checks()  # Run immediately before scheduling starts
        self.scheduler.start()

if __name__ == "__main__":
    logging.info("Starting the KVM MonitoringTool application...")

    test_mode = "--test" in sys.argv

    try:
        tool = MonitoringTool(test_mode)
        tool.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Shutting down the MonitoringTool...")
        tool.scheduler.shutdown()
