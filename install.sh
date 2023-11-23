#!/bin/bash

#######################
#####CONFIGURATION#####
#######################

# Name of the main iptables chain that handles outgoing traffic from the VMs
# By default on KVM host using Libvirt for traffic management it is called LIBVIRT_FWO (Libvirt Forward Out)
OUTGOING_NETWORK_CHAIN="LIBVIRT_FWO"
#Interval of time between each run in minutes (Default : 20)
CRON_INTERVAL=20

#######################
###DO NOT EDIT BELOW###
#######################

# Declaration of some variables needed during the installation
SCRIPT_DIR="/etc/vmsentry"
TEMP_DIR="/tmp/vmsentry"
LOG_FILE="$TEMP_DIR/install.log"
REQ_FILE="$SCRIPT_DIR/srcs/requirements.txt"

# Perform initial checks
initial_checks() {

	#Check for root privileges
	[[ "$EUID" -ne 0 ]] && { echo "Please run as root"; exit 1; }
	echo "Script running as root."

	# Creating temporary folder for installation
	mkdir -p $TEMP_DIR || { echo "Failed to create $TEMP_DIR temporary directory"; exit 1; }

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

# Install the main files for VMsentry
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
	wget https://github.com/lulubas/vmsentry/archive/refs/heads/main.zip -O $TEMP_DIR/vmsentry.zip >/dev/null || { echo "Failed to download VMsentry" ; exit 1; }

	# Create mais script directory if it doesn't exist
	mkdir -p $SCRIPT_DIR || { echo "Failed to create $SCRIPT_DIR directory"; exit 1; }

	# Unzip the downloaded file
	echo "Unzipping VMsentry archive..."
	unzip -o $TEMP_DIR/vmsentry.zip -d $TEMP_DIR || { echo "Failed to unzip VMsentry archive"; exit 1; }

	# Move the contents to /etc/vmsentry
	echo "Moving VMsentry files..."
	mv $TEMP_DIR/vmsentry-main/* $SCRIPT_DIR/ || { echo "Failed to move VMsentry files"; exit 1; }

	echo "VMsentry downloaded and set up successfully"
}

# Install python, pip and the necessary packages to run vmsentry if not already installed.
install_python() {

	# Get the Python version in two formats (one with a dot and one without) and potential header locations
	# These are needed for installing development package)
	PYTHON_VERSION_PKG=$(python3 -c "import sys; print(f'python{sys.version_info.major}{sys.version_info.minor}')")

	PYTHON_VERSION_HEADER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
	PYTHON_H_PATH1="/usr/include/python${PYTHON_VERSION_HEADER}/Python.h"
	PYTHON_H_PATH2="/usr/include/python${PYTHON_VERSION_HEADER}m/Python.h"	

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

	# Check if Python development package is already installed by checking the presence of headers
	if [ -f "$PYTHON_H_PATH1" ] || [ -f "$PYTHON_H_PATH2" ]; then
		echo "Python development headers are installed for Python ${PYTHON_VERSION_HEADER}."
	else
		echo "Python development headers are not installed for Python ${PYTHON_VERSION_HEADER}. Installing them now..."
		if [[ $PKG_MANAGER == "apt-get" ]]; then
			$PKG_MANAGER install python${PYTHON_VERSION_PKG}-dev -y || { echo "Failed to install python${PYTHON_VERSION_PKG}-dev using $PKG_MANAGER"; exit 1; }
		elif [[ $PKG_MANAGER == "yum" ]]; then
			$PKG_MANAGER install python${PYTHON_VERSION_PKG}-devel -y || { echo "Failed to install python${PYTHON_VERSION_PKG}-devel using $PKG_MANAGER"; exit 1; }
		else
			echo "Package manager not recognized. Cannot install Python development headers."
			exit 1
		fi
		echo "Python development headers have been installed for Python ${PYTHON_VERSION_HEADER}."
	fi

	#Check if libvirt development package is installed
	if ! pkg-config --exists libvirt; then
		echo "libvirt development package is not installed. Installing it now..."
		if [[ $PKG_MANAGER == "apt-get" ]]; then
			$PKG_MANAGER install libvirt-dev -y || { echo "Failed to install libvirt-dev using $PKG_MANAGER"; exit 1; }
		elif [[ $PKG_MANAGER == "yum" ]]; then
			$PKG_MANAGER install libvirt-devel -y || { echo "Failed to install libvirt-dev using $PKG_MANAGER"; exit 1; }
		else
			echo "Package manager not recognized. Cannot install libvirt development package."
			exit 1
		fi
		echo "libvirt develomment package has been installed."
	else
		echo "libvirt develomment package is installed."
	fi

	#Install required depedencies for VMsentry to run
	pip3 install --user -r $REQ_FILE || { echo "Failed to install depedencies"; exit 1; }
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
		echo "$chain_name SMTP traffic now redirects to OUTGOING_MAIL chain"
	else
		echo "$chain_name SMTP traffic already redirects to OUTGOING_MAIL"
	fi
}

# Main function to create the required iptables chains and rules 
setup_chains() {
	create_chain OUTGOING_MAIL "[VMS#0] Logged: "
	create_chain LOG_AND_DROP "[VMS#1] Dropped: "
	create_drop_rule LOG_AND_DROP
	create_jump_rule $OUTGOING_NETWORK_CHAIN
}

# Configure rsyslog to generate custom logs
setup_rsyslog() {

	#Check if rsyslog is running and start it if it is not
	if ! systemctl is-active --quiet rsyslog; then
		systemctl start rsyslog || { echo 'Failed to start rsyslog. Exiting.'; exit 1; }
		echo "Rsyslog started successfully"
	else
		echo "Rsyslog is running"
	fi

	# Check if rsyslog is enabled and enable it if it is not
	if ! systemctl is-enabled --quiet rsyslog; then
		systemctl enable rsyslog || { echo 'Failed to enable rsyslog. Exiting.'; exit 1; }
		echo "Rsyslog has been enabled at startup"
	else
		echo "Rsyslog is enabled at startup"
	fi

	# Change the log location via rsyslog configuration file
	if [ -f "/etc/rsyslog.d/vmsentry.conf" ]; then
		echo "rsyslog configuration file already exists. It will be overwriten"
	fi

	#Create/overwrite rsyslog custom  file to redirect custom logs to the VMSentry directory
	echo -e ':msg, contains, "VMS#0" /etc/vmsentry/logs/iptables_all_25.log\n& stop\n:msg, contains, "VMS#1" /etc/vmsentry/logs/iptables_dropped_25.log\n& stop' > /etc/rsyslog.d/vms_iptables.conf || { echo 'Failed to edit VMS log location in rsyslog. Exiting.'; exit 1; }   
	echo "Rsyslog custom configuration file has been setup"

	#Restart rsyslog service
	systemctl restart rsyslog || { echo 'Failed to restart rsyslog.'; exit 1; }
	echo "Rsyslog restarted successfully"
}

# Setup cron job to run every X minutes
setup_cron() {
	
	# Name of the cron job for easy identification and declare it
	CRON_NAME="VMsentry"
	CRON_EXE="$SCRIPT_DIR/cron/vmsentry.sh"
	CRON_TMP="$TEMP_DIR/cron_tmp"
	CRON_JOB="*/$CRON_INTERVAL * * * *  $CRON_EXE > $SCRIPT_DIR/cron/cron.log 2>&1 # $CRON_NAME"
	
	# Save existing cron jobs (without the existing vmsentry cron job if it already exists) to a temporary file
	if crontab -l | grep -q "$CRON_NAME"; then
		# Check the number of lines in the crontab
		if [ "$(crontab -l | wc -l)" -eq 1 ]; then
			# If only one line is present (ie. only the VMsentry cron job) simply create an empty temp file
			echo -n > $CRON_TMP || { echo "Failed to create empty temp file"; exit 1; }
			echo "Existing cron job has been deleted"
		else
			# More than one line present, remove the VMsentry job
			crontab -l | grep -v "$CRON_NAME" > $CRON_TMP || { echo "Failed to remove current VMsentry job and write current crontab to file"; exit 1; }
			echo "Existing cron job has been deleted, other cron jobs remain"
		fi
	else
		crontab -l 2>/dev/null > $CRON_TMP || { echo "Failed to write current crontab to file"; exit 1; }
	fi
	
	# Append the temporary file with the VMsentry cron job
	echo "$CRON_JOB" >> $CRON_TMP || { echo "Failed to write temp file to crontab"; exit 1; }

	# Install new cron file and delete temporary file
	crontab $CRON_TMP || { echo "Failed to install new crontab"; exit 1; }
	echo "New cron job set up successfully to run every $CRON_INTERVAL minutes."

	# Give the execute permissions to the cron executable
	chmod +x $CRON_EXE || { echo "Failed to give execute permissions to $CRON_EXE"; exit 1; }
	echo "Execute permissions given successfully to the cron executable."
}

# Clean up temporary installation files/directories
 clean_up() {

	# Moving installation logfile into the main VMsentry directory
	mv $LOG_FILE $SCRIPT_DIR || echo 'Failed to move the installation log to the main vmsentry directory.'

	# Clean up temporary installation folder
	rm -rf $TEMP_DIR || echo 'Failed to remove temporary installation folder.'
	echo "Installation temporary files deleted"
}

#Main structure
echo "Starting installation of VMsentry..."
initial_checks
install_script
install_python
install_iptables
setup_chains
setup_rsyslog
setup_cron
clean_up
echo "Install finished. Please check $LOG_FILE for the log"