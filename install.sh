#!/bin/bash

# Perform initial checks
initial_checks() {

	#Check for root privileges
	[[ "$EUID" -ne 0 ]] && { echo "Please run as root"; exit 1; }
	echo "Script running as root."

	# Creating temporary folder for installation
	mkdir -p /tmp/vmsentry || { echo "Failed to create /tmp/vmsentry temporary directory"; exit 1; }

	# Set up logging
	SCRIPT_DIR="/etc/vmsentry"
	TEMP_DIR="/tmp/vmsentry"
	LOG_FILE="$TEMP_DIR/install.log"

	exec > >(tee -i $LOG_FILE)
	exec 2>&1
	echo "Logging setup successfully"

	# Check if VMsentry already installed and confirm overwriting
	if [ -d "$SCRIPT_DIR" ]; then
		echo "VMsentry seems already installed."
		read -p "Continuing will overwrite the current installation. Continue? (Y/n)" user_input
		if [ "${user_input,,}" == "y" ]; then
			echo "User chose to overwrite existing installation."
		else
			echo "Installation Aborted."
			exit 1
		fi
		
		# Delete all files and directories except for the logs folder
        find "$SCRIPT_DIR" -mindepth 1 -not -path "$SCRIPT_DIR/logs*" -exec rm -rf {} +
		echo "VMsentry directory successfully cleaned up (while keeping logs)."
	else
		echo "VMsentry is not yet installed. Continuing."
	fi

	#Detecting system OS using different methods
	OS=""
	if [ -f /etc/os-release ]; then
		. /etc/os-release
		OS=$NAME
		echo "OS detected from /etc/os-release: $OS"
	elif command -v lsb_release >/dev/null 2>&1; then
		OS=$(lsb_release -si)
		echo "OS detected from lsb_release:$OS"
	elif [ -f /etc/debian_version ]; then
		OS=Debian
		echo "OS detected from /etc/debian_version: $OS"
	elif [ -f /etc/redhat-release ]; then
		OS=Redhat
		echo "OS detected from /etc/redhat-release: $OS"
	else
		OS=$(uname -s)
		echo "OS detected from uname: $OS"
	fi

	# Trim leading and trailing whitespaces and convert to lowercase
	OS=$(echo "$OS" | awk '{$1=$1};1' | awk '{print tolower($0)}')

	# Check if the OS is supported and assign correct package manager, if not suported then exit
	case "$OS" in
		"ubuntu"|"debian")
			PKG_MANAGER="apt-get"
			;;
		"centos linux"|"almalinux"|"red hat enterprise linux")
			PKG_MANAGER="yum"
			;;
		*)
			echo "OS not supported: $OS. VMsentry only compatible with Ubuntu, Debian, CentOS, RHEL, and AlmaLinux. Exiting."
			exit 1
			;;
	esac
}

install_script() {
	# Check if unzip is installed and install it if it's not
	if ! command -v unzip &> /dev/null; then
		echo "Unzip could not be found. Installing it now..."
		$PKG_MANAGER install unzip -y >/dev/null || { echo "Failed to install unzip using $PKG_MANAGER"; exit 1; }
		echo "Unzip installed successfully"
	else
		echo "Unzip is installed"
	fi

	# Download the .zip file of the repository
	echo "Downloading VMsentry"
	wget https://github.com/lulubas/vmsentry/archive/refs/heads/main.zip -O /tmp/vmsentry/vmsentry.zip >/dev/null || { echo "Failed to download VMsentry" ; exit 1; }

	# Create /etc/vmsentry if it doesn't exist
	mkdir -p /etc/vmsentry || { echo "Failed to create /etc/vmsentry directory"; exit 1; }

	# Unzip the downloaded file
	echo "Unzipping VMsentry archive..."
	unzip -o /tmp/vmsentry/vmsentry.zip -d /tmp/vmsentry/ || { echo "Failed to unzip VMsentry archive"; exit 1; }

	# Move the contents to /etc/vmsentry
	echo "Moving VMsentry files..."
	mv /tmp/vmsentry/vmsentry-main/* /etc/vmsentry/ || { echo "Failed to move VMsentry files"; exit 1; }

	echo "VMsentry downloaded and set up successfully"
}

# Install python and pip if not already installed. This is also going to update the package manager
install_python() {
	#Check if Python3 is installed
	if ! command -v python3 &>/dev/null; then
		echo "Python3 is not yet installed. Installing it now..."
		$PKG_MANAGER install python3 -y || { echo "Failed to install Python3 using $PKG_MANAGER"; exit 1; }
		echo "python3 has been installed."
	else
		echo "python is installed."
	fi

	#Check if Pip3 is installed
	if ! command -v pip3 &>/dev/null; then
		echo "Pip3 is not yet installed. Installing it now..."
		$PKG_MANAGER install python3-pip -y || { echo "Failed to install Python3 using $PKG_MANAGER"; exit 1; }
		echo "pip3 has been installed."
	else
		echo "pip is installed."
	fi
}

# Define a function to check if an interface is a NAT interface.
# In this script, we're assuming that NAT interfaces have names that begin with "natbr".
is_interface() {
	local interface=$1
	local interface_pattern=${INTERFACE_PATTERN:-"natbr*"}
    [[ $interface == $interface_pattern ]]
}

# Setup iptables and required chains
install_iptables() {
	
	# Check if iptables is installed
	if ! command -v iptables &>/dev/null; then
		echo "iptables is not installed. Attempting to install it..."
		$PKG_MANAGER install iptables -y || { echo "Failed to install iptables using $PKG_MANAGER"; exit 1; }
	else
		echo "iptables is installed."
	fi
}

setup_chains() {
	# Setting up OUTGOING_MAIL chain
	if iptables -L OUTGOING_MAIL >/dev/null 2>&1; then
		echo 'OUTGOING_MAIL chain already exists. Skipping.' | tee -a $LOG_FILE
		read -p 'Flush the current OUTGOING_MAIL chain? This will remove IPs previously blocked  (Y/n)' user_input
			if [ "${user_input,,}" == "y" ]; then
				echo "Flushing OUTGOING_MAIL chain..." | tee -a $LOG_FILE
				iptables -F OUTGOING_MAIL || { echo 'An error occured while flushing OUTGOING_MAIL chain. Exiting.' | tee -a $LOG_FILE ; exit 1; }
				echo "Flushing OUTGOING_MAIL chain successfull" | tee -a $LOG_FILE
			else
				echo "Keeping OUTGOING_MAIL chain as is. Pursuing installation." | tee -a $LOG_FILE
			fi
	else
		echo "OUTGOING_MAIL chain does yet exist. Adding it." | tee -a $LOG_FILE
		iptables -N OUTGOING_MAIL || { echo 'An error occured while creating OUTGOING_MAIL chain. Exiting.' | tee -a $LOG_FILE ; exit 1; }
		echo "OUTGOING_MAIL created successfully" | tee -a $LOG_FILE
	fi
	
	#checking and adding the OUTGOING_MAIL LOG rule
	echo "Adding OUTGOING_MAIL LOG rule..." | tee -a $LOG_FILE
	if ! iptables -C OUTGOING_MAIL -j LOG --log-prefix "[VMS#0] Logged: " --log-level 4 >/dev/null 2>&1; then
		# If the rule doesn't exist, add it
		echo "Adding OUTGOING_MAIL rules..." | tee -a $LOG_FILE
		iptables -I OUTGOING_MAIL -j LOG --log-prefix "[VMS#0] Logged: " --log-level 4 || { echo 'An error occured while adding LOG rule to OUTGOING_MAIL chain. Exiting.' | tee -a $LOG_FILE ; exit 1; }
		echo "OUTGOING_MAIL chain created and LOG rule added" | tee -a $LOG_FILE
	else
		# If the rule does exist, print a message
		echo "The LOG rule already exists in the OUTGOING_MAIL chain. Pursuing..." | tee -a $LOG_FILE
	fi
	
	# Detecting main NAT network interfaces, redirecting port 25 traffic to OUTGOING_MAIL chain
	# Get the list of all network interfaces.
	interfaces=$(ls /sys/class/net)
	interface_found=0
	# Loop over all network interfaces.
	for interface in $interfaces; do
		# If this is a NAT interface, add the iptables rules.
		if is_nat_interface $interface; then
			interface_found=1
			echo "Detected NAT interface: $interface" | tee -a $LOG_FILE
			if ! iptables -C LIBVIRT_FWO -i $interface -p tcp --dport 25 -j OUTGOING_MAIL >/dev/null 2>&1; then
				echo "Rule does not exist for $interface. Adding it" | tee -a $LOG_FILE
				iptables -I LIBVIRT_FWO -i $interface -p tcp --dport 25 -j OUTGOING_MAIL || { echo 'An error occured while adding rule. Exiting.' | tee -a $LOG_FILE ; exit 1; }
				echo "Rule added successfully" | tee -a $LOG_FILE
			else
				echo "Rule for $interface already exists" | tee -a $LOG_FILE
			fi
		fi
	done
	if [[ $interface_found == 0 ]]; then
			echo "No NAT interface found. Exiting" | tee -a $LOG_FILE
			exit 1
	fi

	# Setuping up the LOG_AND_DROP chain and rules
	echo "Checking LOG_AND_DROP chain..." | tee -a $LOG_FILE
	if iptables -L LOG_AND_DROP >/dev/null 2>&1; then
		echo 'LOG_AND_DROP chain already exists.' | tee -a $LOG_FILE
		read -p 'Flush the current LOG_AND_DROP and recreate it? Say yes only if LOG_AND_DROP chain exists because of a previous VMSentry installation. (Y/n)' user_input
			if [ "${user_input,,}" == "y" ]; then
				echo "Flushing LOG_AND_DROP chain" | tee -a $LOG_FILE
				iptables -F LOG_AND_DROP || { echo 'An error occured while flushing LOG_AND_DROP chain. Exiting.' | tee -a $LOG_FILE ; exit 1; }
				echo "Flushing LOG_AND_DROP chain successfull" | tee -a $LOG_FILE
			else
				echo "Keeping the current LOG_AND_DROP chain ." | tee -a $LOG_FILE
			fi
	else
		echo "LOG_AND_DROP chain does not yet exist. Adding it." | tee -a $LOG_FILE
		iptables -N LOG_AND_DROP || { echo 'An error occured while creating LOG_AND_DROP chain. Exiting.' | tee -a $LOG_FILE ; exit 1; }
		echo "LOG_AND_DROP created successfully" | tee -a $LOG_FILE
	fi
	echo "Adding LOG_AND_DROP rules." | tee -a $LOG_FILE
	if ! iptables -C LOG_AND_DROP -j LOG --log-prefix "[VMS#1] Dropped: " --log-level 4 >/dev/null 2>&1; then
		# If the rule doesn't exist, add it
		echo "Adding LOG_AND_DROP LOG rules." | tee -a $LOG_FILE
		iptables -I LOG_AND_DROP -j LOG --log-prefix "[VMS#1] Dropped: " --log-level 4 || { echo 'An error occured while adding LOG rule to OUTGOING_MAIL chain. Exiting.' | tee -a $LOG_FILE ; exit 1; }
		echo "LOG rule added" | tee -a $LOG_FILE
	else
		# If the rule does exist, print a message
		echo "The LOG rule already exists in LOG_AND_DROP. Pursuing..." | tee -a $LOG_FILE
	fi

	if ! iptables -C LOG_AND_DROP -j DROP >/dev/null 2>&1; then
		# If the rule doesn't exist, add it
		echo "Adding LOG_AND_DROP DROP rules." | tee -a $LOG_FILE
		iptables -A LOG_AND_DROP -j DROP || { echo 'An error occured while adding DROP rule to LOG_AND_DROP chain. Exiting.' | tee -a $LOG_FILE ; exit 1; }
	else
		# If the rule does exist, print a message
		echo "The DROP rule already exists in LOG_AND_DROP. Pursuing..." | tee -a $LOG_FILE
	fi
	echo "LOG_AND_DROP chain setup completed" | tee -a $LOG_FILE

	# Change the log location via custom rsyslog configuration file
	if  systemctl is-active --quiet rsyslog; then
		echo "Rsyslog is running. Continuing..." | tee -a $LOG_FILE
	else
		echo "Rsyslog is not running. Starting rsyslog now..." | tee -a $LOG_FILE
		systemctl start rsyslog | tee -a $LOG_FILE || { echo 'Failed to start rsyslog. Exiting.' | tee -a $LOG_FILE ; exit 1; }
		echo "Rsyslog started successfully." | tee -a $LOG_FILE
	fi

	# Check if rsyslog is enabled
	if systemctl is-enabled --quiet rsyslog; then
		echo "Rsyslog is  enabled at startup. Continuing..." | tee -a $LOG_FILE
	else
		echo "Rsyslog is not enabled at startup. Enabling rsyslog now..." | tee -a $LOG_FILE
		systemctl enable rsyslog | tee -a $LOG_FILE || { echo 'Failed to enable rsyslog. Exiting.' | tee -a $LOG_FILE ; exit 1; }
	fi

	echo "Checking Rsyslog conf file..." | tee -a $LOG_FILE
	if [ -f "/etc/rsyslog.d/vms_iptables.conf" ]; then
		# Ask for user confirmation before overwriting
		read -p "/etc/rsyslog.d/vms_iptables.conf already exists. Overwrite? (Y/n): " user_input
		if [ "${user_input,,}" == "y" ]; then
			echo -e ':msg, contains, "VMS#0" /etc/vmsentry/logs/iptables_all_25.log\n& stop\n:msg, contains, "VMS#1" /etc/vmsentry/logs/iptables_dropped_25.log\n& stop' > /etc/rsyslog.d/vms_iptables.conf || { echo 'Failed to edit VMS log location in rsyslog. Exiting.' | tee -a $LOG_FILE ; exit 1; }   
			echo "Rsyslog configuration file updated to redirect iptables outgoing port 25 logs" | tee -a $LOG_FILE
			echo "Restarting Rsyslog..." | tee -a $LOG_FILE
			systemctl restart rsyslog | tee -a $LOG_FILE || { echo 'Failed to restart rsyslog.' | tee -a $LOG_FILE ; exit 1; }
			echo "Rsyslog restarted successfully" | tee -a $LOG_FILE
		else
			echo "Rsyslog configuration file was not updated. Pursuing." | tee -a $LOG_FILE
		fi
	else
		echo "Creating custom rsyslog configuration to redirect logs VMSentry logs directory..." | tee -a $LOG_FILE
		echo -e ':msg, contains, "VMS#0" /etc/vmsentry/logs/iptables_all_25.log\n& stop\n:msg, contains, "VMS#1" /etc/vmsentry/logs/iptables_dropped_25.log\n& stop' > /etc/rsyslog.d/vms_iptables.conf || { echo 'Failed to edit VMS log location in rsyslog. Exiting.' | tee -a $LOG_FILE ; exit 1; }   
		echo "Rsyslog configuration file created /etc/rsyslog.d/vms_iptables.conf " | tee -a $LOG_FILE
		echo "Restarting Rsyslog..." | tee -a $LOG_FILE
		systemctl restart rsyslog | tee -a $LOG_FILE || { echo 'Failed to restart rsyslog.' | tee -a $LOG_FILE ; exit 1; }
		echo "Rsyslog restarted successfully" | tee -a $LOG_FILE
	fi
}

# Setup cron job to run every X minutes
setup_cron() {
	# Name of the cron job for easy identification
	CRON_NAME="VMsentry"
	CURRENT_PATH=$(pwd)
	# Check if the cron job already exists
	if crontab -l | grep -q "$CRON_NAME"; then
		echo "Cron job already exists. Skipping addition." | tee -a $LOG_FILE
	else
		# Cron job does not exist, add it
		echo "Adding cron job..." | tee -a $LOG_FILE
		# Write out current crontab to a temp file, if one exists
		if crontab -l 2>/dev/null; then
			echo "Existing root cron jobs detected. Copying them to a temporary file $CURRENT_PATH/mycron" | tee -a $LOG_FILE
			crontab -l > mycron || { echo "Failed to write current crontab to file. Exiting." | tee -a $LOG_FILE ; exit 1; }
		else
			echo "No existing root cron jobs. Temporary file $CURRENT_PATH/mycron Created." | tee -a $LOG_FILE
			touch mycron
		fi
		# Echo new cron into cron file, run script every 10 minutes
		echo "*/10 * * * *  /etc/vmsentry/cron/run_vmsentry.sh > /etc/vmsentry/cron/cron.log 2>&1 # $CRON_NAME" >> mycron
		# Install new cron file
		crontab mycron || { echo "Failed to install new crontab. Exiting." | tee -a $LOG_FILE ; exit 1; }
		rm mycron
		echo "Temporary file $CURRENT_PATH/mycron Deleted" | tee -a $LOG_FILE
		echo "Cron job added successfully." | tee -a $LOG_FILE
	fi
}

 clean_up() {
	# Saving install.log into the main directory
	mv /tmp/vmsentry/install.log /etc/vmsentry/ || { echo 'Failed to move the installation log to the main vmsentry directory.'; }

	# Clean up temporary installation folder
	rm -rf /tmp/vmsentry || { echo 'Failed to remove temporary installation folder.'; }
 }

#Main structure

echo "Starting installation of VMsentry..."
initial_checks
install_script
install_python
# setup_iptables
# setup_cron
clean_up
echo "Install finished. Please check $LOG_FILE for the log"