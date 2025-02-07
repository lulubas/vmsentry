from logger import Logger
from config import ConfigLoader, Config
from monitor import Monitor
from apscheduler.schedulers.blocking import BlockingScheduler

# Main Application
class MonitoringTool:
    def __init__(self):
        self.logger = Logger.load_logger()
        logger.info("Initializing MonitoringTool...")
        self.config = ConfigLoader.load_config()
        self.monitor = Monitor(self.logger, self.config)
        self.scheduler = BlockingScheduler()

    def start(self):
        """Starts the monitoring process."""
        self.scheduler.add_job(self.monitor.check_all_hosts, 'interval', minutes=self.config.monitoring_interval)
        self.scheduler.start()

if __name__ == "__main__":
    tool = MonitoringTool()
    tool.start()