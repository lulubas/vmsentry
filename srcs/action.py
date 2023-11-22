import logging
from ip_manage import is_ip_blocked, block_ip
from init_config import Config
from notification import send_mail_notification, send_telegram_notification

# Loop through all the VMs and block them is they reached the limits
def trigger_limits(vms, config: Config):

	count_action = 0

	#Go through each VPS and check their SMTP information
	for vm in vms:
		
		ip = vm['ip']

		#If IP is already blocked there is no need to block it again
		if is_ip_blocked(ip):
			continue

		#Create a flag to see if IP has triggered a limit
		to_block = False

		#Check if the SMTP connexions limit is reached	
		if vm['smtp_connections'] >= config.smtp_connections_limit:
			to_block = True
			logging.info(f"{ip} has reached its SMTP connextions limit: {vm['smtp_connections']}/{config.smtp_connections_limit} within the last {config.timeframe} hours")

		#Check if the Unique IPs limit is reached
		if len(vm['unique_dst_ips']) >= config.unique_ips_limit:
			to_block = True
			logging.info(f"{ip} has reached its Unique IPs limit: {vm['unique_dst_ips']}/{config.unique_ips_limit} within the last {config.timeframe} hours")

		#If one of the limits was reached block the VM IP and send an email (if mail notification enabled)
		if to_block and config.block_ip:
			count_action += 1
			block_ip(ip, f"{vm['smtp_connections']} connections/ {len(vm['unique_dst_ips'])} unique IPs")
			if config.send_email:
				send_mail_notification(vm, config)
			if config.send_telegram:
				send_telegram_notification(vm, config)
	
	logging.info(f"Run completed. {count_action} action(s) taken")