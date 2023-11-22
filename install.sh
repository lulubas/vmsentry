#!/bin/bash

#######################
#####CONFIGURATION#####
#######################

# Name of the main iptables chain that handles outgoing traffic from the VMs
# By default on KVM host using Libvirt for traffic management it is called LIBVIRT_FWO (Libvirt Forward Out)
OUTGOING_NETWORK_CHAIN="LIBVIRT_FWO"

#######################
###DO NOT EDIT BELOW###
#######################

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

# Utility function to create an iptables chain and add a LOG rule in its first position
create_chain() {
    local chain_name=$1
    local log_prefix=$2

	# Check if the chain already exists and create it if it does not
    if ! iptables -L "$chain_name" >/dev/null 2>&1; then
        iptables -N "$chain_name" || { echo "An error occurred while creating $chain_name chain. Exiting."; exit 1; }
        echo "$chain_name created successfully"
    else
        echo "$chain_name chain already exists."
    fi

	# Check if a LOG rule already exists and create it if it does not
    if ! iptables -C "$chain_name" -j LOG --log-prefix "$log_prefix" --log-level 4 >/dev/null 2>&1; then
        iptables -I "$chain_name" -j LOG --log-prefix "$log_prefix" --log-level 4 || { echo "An error occurred while adding LOG rule to $chain_name chain. Exiting."; exit 1; }
        echo "$chain_name LOG rule added"
    else
        echo "$chain_name LOG rule already exists"
    fi
}

# Utility function to create the DROP rule at the end of a given iptables chain
create_drop_rule() {
    local chain_name=$1

	#Check if a DROP rule already exists and create it if it does not
    if ! iptables -C "$chain_name" -j DROP >/dev/null 2>&1; then
        iptables -A "$chain_name" -j DROP || { echo "An error occurred while adding DROP rule to $chain_name chain. Exiting."; exit 1; }
        echo "$chain_name DROP rule added"
    else
        echo "$chain_name DROP rule already exists"
    fi
}

# Utility function to redirect port 25 traffic to custom OUTGOING_MAIL chain
create_jump_rule() {
    local chain_name=$1

	#Check if a the iptables rule already exists and create it if it does not
    if ! iptables -C "$chain_name" -p tcp --dport 25 -j OUTGOING_MAIL >/dev/null 2>&1; then
        iptables -I "$chain_name" -p tcp --dport 25 -j OUTGOING_MAIL || { echo "An error occurred while redirecting port 25 packets from $chain_name. Exiting."; exit 1; }
        echo "$chain_name port 25 traffic redirected to OUTGOING_MAIL chain"
    else
        echo "$chain_name traffic already redirected to OUTGOING_MAIL"
    fi
}

# Main function to create the required iptables chains and rules 
setup_chains() {
    create_chain OUTGOING_MAIL "[VMS#0] Logged: "
    create_chain LOG_AND_DROP "[VMS#1] Dropped: "
    create_jump_rule LOG_AND_DROP
	create_forward_rule $OUTGOING_NETWORK_CHAIN
}

setup_rsyslog() {

	# Change the log location via custom rsyslog configuration file
	if  systemctl is-active --quiet rsyslog; then
		echo "Rsyslog is running. Continuing..."
	else
		echo "Rsyslog is not running. Starting rsyslog now..."
		systemctl start rsyslog || { echo 'Failed to start rsyslog. Exiting.'; exit 1; }
		echo "Rsyslog started successfully."
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