import logging
from datetime import datetime, timedelta
import ipaddress

# Read a file and return it as a list of strings
def read_lines_from_file(file_path, mode='r'):
	with open(file_path, mode) as file:
		return file.readlines()

# Read a file and return it as a single string
def read_content_from_file(file_path, mode='r'):
	with open(file_path, mode) as file:
		return file.read()

# Writes to a file with a list of lines provided (overwriting by default)
def write_lines_to_file(file_path, lines, mode='w'):
	with open(file_path, mode) as f:
		f.writelines(lines)

def write_content_to_file(file_path, content, mode='w'):
	with open(file_path, mode) as f:
		f.write(content)

# Empties a given file
def empty_file(file_path):
	with open(file_path, 'w') as f:
		pass

# Return a timestamp object from a log line
def extract_timestamp_from_log(log_line, log_time_format="%b %d %H:%M:%S"):
	try:
		# Strip out the date/hour from the log line
		timestamp_logstr = " ".join(log_line.split()[:3])

		#Add the year and construct the timestamp object
		current_year = datetime.now().year
		timestamp = datetime.strptime(f"{current_year} {timestamp_logstr}", f"%Y {log_time_format}")

		return timestamp

	except Exception as e:
		logging.error(f"Error while extracting timestamp from ({log_line}): {e}.")
		return None

# Checks if a string is a valid representation of an IP address
def is_valid_ip(ip_str):
	try:
		ipaddress.ip_address(ip_str)
		return True
	except ValueError:
		return False