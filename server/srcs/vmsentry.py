from logger import Logger
from config import ConfigLoader
from monitor import Monitor
import sys
from apscheduler.schedulers.blocking import BlockingScheduler
 
# Main Application
class MonitoringTool:
    def __init__(self, logger, test_mode = False):
        self.logger = logger
        self.logger.info("Initializing MonitoringTool...")
        self.config = ConfigLoader.load_config()
        self.monitor = Monitor(self.logger, self.config)
        self.monitor.check_all_hosts(test_mode)
        self.scheduler = BlockingScheduler()


    def start(self):
        """Starts the monitoring process."""
        self.scheduler.add_job(self.monitor.check_all_hosts, 'interval', minutes=self.config.monitoring_interval)
        self.scheduler.start()

if __name__ == "__main__":

    logger = Logger.load_logger()
    test_mode = "--test" in sys.argv
    tool = MonitoringTool(logger, test_mode)
    if test_mode == True:
        logger.info("#Test Mode: Scheduler won't be activated. Program will only run once.")
    else:
        tool.start()