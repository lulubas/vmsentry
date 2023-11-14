import logging
import hashlib
import requests
import os

#Update VMSentry with the latest files available on Github
def update_vmsentry():
	base_url = "https://raw.githubusercontent.com/lulubas/vmsentry/main/"
	srcs_dir = '/etc/vmsentry/srcs/'
	config_ini = '/etc/vmsentry/config.ini'

	#get list of all .py files to update in the srcs directory
	files_to_update = generate_file_paths(srcs_dir, config_ini)

	for file_path in files_to_update:
		#Iterates over file names and add the base directory when necessary
		file_name = os.path.basename(file_path)
		url = base_url + ('srcs/' if file_path != config_ini else '') + file_name
		
		try :
			#Fetch corresponding file from GitHub
			response = requests.get(url, headers={'Cache-Control': 'no-cache'})
			response.raise_for_status()
			remote_file = response.content

			# Calculate remote file hash
			remote_hash = calculate_hash(remote_file)

			# Calculate local file hash
			with open(file_path, 'rb') as f:
				local_file = f.read()
			local_hash = calculate_hash(local_file)

			#If the Hashes match, no need to update the file
			if local_hash == remote_hash:
					logging.info(f"{file_name} is already up-to-date.")
					continue
			
			#Wrtie changes to the file 
			with open(file_path, 'wb') as f:
				f.write(remote_content)
				logging.info(f"{file_name} has been updated.")
			
		except Exception as e:
			logging.error(f"Failed to update {file_name}: {e}")
			raise
		
	logging.info("Update Completed.")

#function to generate absolute filepaths of the files to update
def generate_file_paths(srcs_dir, config_file):
	files_to_update = [os.path.join(srcs_dir, f) for f in os.listdir(srcs_dir) if f.endswith('.py')]
	files_to_update.append(config_file)
	return files_to_update
	

def calculate_hash(file_content):
	return hashlib.sha256(file_content).hexdigest()