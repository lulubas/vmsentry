import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import logging
from init_config import Config

#Send a mail notification using smtplib and a remote smtp server
def send_mail_notification(vm, config: Config):
	try:
		# Create the message
		msg = MIMEMultipart()
		msg['From'] = config.from_email_addr
		msg['To'] = config.to_recipient
		msg['Subject'] = f"VMSentry {vm['name']} ({vm['ip']}) blocked"

		# Create the body of the message
		body = f"""
		Alert: VMSentry blocked Port 25 of the following VM:

		VM Name: {vm['name']}
		VM IP: {vm['ip']}
		SMTP Connections: {vm['smtp_connections']}
		Unique Destination IPs: {len(vm['unique_dst_ips'])}
		"""

		# Attach the body with the msg instance
		msg.attach(MIMEText(body, 'plain'))

		# Create SMTP session with smtplib
		# Replace smtp_host and email_password accordingly
		with smtplib.SMTP(config.from_smtp_host, config.from_smtp_port) as server:
			server.starttls()
			server.login(config.from_email_addr, config.from_email_pw)
			text = msg.as_string()
			server.sendmail(config.from_email_addr, config.to_recipient, text)

		logging.info(f"Email sent successfully to {config.to_recipient} ({vm['name']}/{vm['ip']}).")

	except Exception as e:
		logging.error(f"Failed to send email: {e}")

def send_telegram_notification(vm, config: Config):
	try:
		# Create the message
		message = f"""
		Alert: VMSentry blocked Port 25 of the following VM:

		VM Name: {vm['name']}
		VM IP: {vm['ip']}
		SMTP Connections: {vm['smtp_connections']}
		Unique Destination IPs: {len(vm['unique_dst_ips'])}
		"""

		# Send the message through Telegram
		url = f"https://api.telegram.org/bot{config.telegram_api}/sendMessage"
		payload = {
			'chat_id': config.telegram_chat_id,
			'text': message
		}
		response = requests.post(url, json=payload)

		if response.status_code == 200:
			logging.info(f"Telegram message sent successfully ({vm['name']}/{vm['ip']})")
		else:
			logging.error(f"Failed to send Telegram message: {response.text}")

	except Exception as e:
		logging.error(f"Failed to send Telegram message: {e}")