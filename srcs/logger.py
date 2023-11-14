import logging
from datetime import datetime, timedelta
from utils import read_lines_from_file, write_lines_to_file, extract_timestamp_from_log

#Setting up the log handler
def setup_logging(__version__):
	log_retention = 30
	log_filename = '/etc/vmsentry/logs/vmsentry.log'
	entries_log_filename = '/etc/vmsentry/logs/IP.list'

	#Set up loggers
	formatter = logging.Formatter('%(asctime)s %(message)s', datefmt="%b %d %H:%M:%S")

	# Main logger
	logger = logging.getLogger()
	logger.setLevel(logging.INFO)
	handler = logging.FileHandler(log_filename)
	handler.setFormatter(formatter)
	logger.addHandler(handler)

	# Logger for IP entries
	entries_logger = logging.getLogger('entries')
	entries_handler = logging.FileHandler(entries_log_filename)
	entries_handler.setFormatter(formatter)
	entries_logger.addHandler(entries_handler)

	# StreamHandler to write logs to stdout
	stream_handler = logging.StreamHandler()
	stream_handler.setFormatter(formatter)
	logger.addHandler(stream_handler)

	logging.info(f"===== VM SENTRY ({__version__}) =====")
	logging.info("VMSentry logger setup successfully") 

	# Rotate logs  
	try:
		rotated = rotate_main_logs(log_filename, log_retention)
		logging.info(f"Logs older than {log_retention} days were deleted ({rotated} lines)")
	
	except Exception as e:
		logging.error(f'Error while rotating logs: {e}')
		raise

# Rotate main logs based on their timestamp
def rotate_main_logs(file_path, retention):
	logs = read_lines_from_file(file_path)
	filtered_logs = []
	lines_deleted = 0

	for log in logs:
		timestamp = extract_timestamp_from_log(log)
		if not timestamp or (datetime.now() - timestamp > timedelta(days=retention)):
			lines_deleted += 1
			continue
		filtered_logs.append(log)

	write_lines_to_file(file_path, filtered_logs)

	return (lines_deleted)