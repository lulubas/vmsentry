#!/bin/bash

echo "Starting installation of VMsentry..."

# Perform initial checks
initial_checks() {
    echo "Starting installation of VMSentry"
    #Check for root privileges
    if [ "$EUID" -ne 0 ]; then 
        echo "Please run as root"
        exit
    fi
    echo "Script running as root."

    # Check if VMsentry already installed
    SCRIPT_DIR="/etc/vmsentry"
    LOG_DIR="/etc/vmsentry/logs"
    LOG_FILE="$LOG_DIR/install.log"
    
    if [ -d "$SCRIPT_DIR" ]; then
        echo "VMsentry seems already installed."
        read -p "Do you want to overwrite existing installation (Y/n) ?" user_input
        if [ "${user_input,,}" == "y" ]; then
            echo "Deleting existing vmsentry files/directories except logs" | tee -a $LOG_FILE
            for file in $(find $SCRIPT_DIR -mindepth 1 -maxdepth 1 ! -name logs); do
                rm -rf $file || { echo "Failed to delete $file" | tee -a $LOG_FILE ; exit 1; }
                echo "Deleted $file" | tee -a $LOG_FILE
            done
            echo "VMsentry directory successfully cleaned up." | tee -a $LOG_FILE
        else
            echo "Overwritting existing installation cancelled. Aborting..." | tee -a $LOG_FILE
            exit 1
        fi
    else
        # Create necessary directories
        mkdir -p $SCRIPT_DIR >/dev/null 2>&1 || { echo "Failed to create $SCRIPT_DIR" | tee -a $LOG_FILE ; exit 1; }
        mkdir -p $LOG_DIR >/dev/null 2>&1 || { echo "Failed to create $LOG_DIR" | tee -a $LOG_FILE ; exit 1; }
        echo "VMsentry directories created successfully" | tee -a $LOG_FILE
    fi

    # Set up logging
    exec > >(tee -i $LOG_FILE)
    exec 2>&1
    echo "Logging setup successfully" | tee -a $LOG_FILE

    #Detecting system OS
    OS=""
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$NAME
        echo "OS detected from /etc/os-release: $OS" | tee -a $LOG_FILE
    elif command -v lsb_release >/dev/null 2>&1; then
        OS=$(lsb_release -si)
        echo "OS detected from lsb_release:$OS" | tee -a $LOG_FILE
    elif [ -f /etc/debian_version ]; then
        OS=Debian
        echo "OS detected from /etc/debian_version: $OS" | tee -a $LOG_FILE
    elif [ -f /etc/redhat-release ]; then
        OS=Redhat
        echo "OS detected from /etc/redhat-release: $OS" | tee -a $LOG_FILE
    else
        OS=$(uname -s)
        echo "OS detected from uname: $OS" | tee -a $LOG_FILE
    fi

    # Check if the OS is supported, if not exit
    OS=$(echo "$OS" | awk '{$1=$1};1' | awk '{print tolower($0)}')
    if ! [[ "$OS" == "ubuntu" || "$OS" == "debian" || "$OS" == "centos linux" || "$OS" == "almalinux" || "$OS" == "red hat enterprise linux" ]]; then
        echo "OS not supported: $OS. VMsentry only compatible with Ubuntu, Debian, CentOS, RHEL and AlmaLinux. Exiting." | tee -a $LOG_FILE
        exit 1
    fi
}

install_script() {
     # Check if unzip is installed and install it if it's not
    if ! command -v unzip &> /dev/null; then
        echo "Unzip could not be found" | tee -a $LOG_FILE
        echo "Attempting to install unzip..." | tee -a $LOG_FILE
        if [ "$OS" == "ubuntu" ] || [ "$OS" == "debian" ]; then
            apt-get install unzip -y >/dev/null 2>&1 || { echo "Failed to install unzip on $OS" | tee -a $LOG_FILE ; exit 1; }
        elif [ "$OS" == "centos linux" ] || [ "$OS" == "red hat enterprise linux" ]; then
            yum install unzip -y >/dev/null 2>&1 || { echo "Failed to install unzip on $OS" | tee -a $LOG_FILE ; exit 1; }
        else
            echo "OS not supported for automatic unzip installation" | tee -a $LOG_FILE
            exit 1
        fi
        echo "Unzip installed successfully" | tee -a $LOG_FILE
    fi

    # Download the .zip file of the repository
    echo "Downloading VMsentry" | tee -a $LOG_FILE
    wget https://github.com/lulubas/vmsentry/archive/refs/heads/main.zip -O /etc/vmsentry/vmsentry.zip >/dev/null 2>&1 || { echo "Failed to download VMsentry" | tee -a $LOG_FILE ; exit 1; }

    # Unzip the downloaded file (junking the directory structure)
    echo "Unzipping VMsentry archive..." | tee -a $LOG_FILE
    unzip -j /etc/vmsentry/vmsentry.zip -d /etc/vmsentry/ >/dev/null 2>&1 || { echo "Failed to unzip VMsentry archive" | tee -a $LOG_FILE ; exit 1; }
    echo "Creating cron directory..." | tee -a $LOG_FILE
    mkdir /etc/vmsentry/cron/ || { echo "Failed to create cron directory" | tee -a $LOG_FILE ; exit 1; }
    echo "Moving cron wrapper into cron directory..." | tee -a $LOG_FILE
    mv /etc/vmsentry/run_vmsentry.sh /etc/vmsentry/cron/ || { echo "Failed to move cron wrapper into cron directory" | tee -a $LOG_FILE ; exit 1; }
    echo "Adding execution permission for cron wrapper script..." | tee -a $LOG_FILE
    chmod +x /etc/vmsentry/cron/run_vmsentry.sh || { echo "Failed to change cron wrapper permission. Exiting." | tee -a $LOG_FILE ; exit 1; }
    echo "Permission set correctly" | tee -a $LOG_FILE

    # Remove the downloaded .zip file and useless files
    echo "Removing installation archive..." | tee -a $LOG_FILE
    rm /etc/vmsentry/vmsentry.zip || { echo "Failed to remove VMsentry archive" | tee -a $LOG_FILE ; exit 1; }
    echo "VMsentry installation archive successfully removed" | tee -a $LOG_FILE
    echo "Removing unnecessary git files..." | tee -a $LOG_FILE
    rm /etc/vmsentry/.gitignore  || { echo "Failed to remove gtignore file" | tee -a $LOG_FILE ; exit 1; }
    rm /etc/vmsentry/README.md || { echo "Failed to remove README file" | tee -a $LOG_FILE ; exit 1; }
    echo "VMsentry downloaded and unzipped successfully" | tee -a $LOG_FILE
}

# Check and Install Python function
install_python() {
    if command -v python3 &>/dev/null; then
        echo "Python 3 is already installed."
    else
        echo "Python 3 is not yet installed. Starting installation now..."
        if [[ "$OS" == "ubuntu" || "$OS" == "debian" ]]; then
            apt-get update | tee -a $LOG_FILE || { echo 'Updating packages failed' | tee -a $LOG_FILE ; exit 1; }
            apt-get install python3 -y | tee -a $LOG_FILE || { echo 'Python3 installation failed' | tee -a $LOG_FILE ; exit 1; }
        elif [[ "$OS" == "centos linux" || "$OS" == "almalinux" || "$OS" == "red hat enterprise linux" ]]; then
            yum install python3 -y | tee -a $LOG_FILE || { echo 'Python3 installation failed' | tee -a $LOG_FILE ; exit 1; }
        else
            echo "Python installation not supported on this OS:$OS. Exiting." | tee -a $LOG_FILE
            exit 1
        fi
        echo "Python 3 has been installed."
    fi
}

# Check and Install Postfix if no MTA is currently installed
install_mta() {
    if command -v sendmail &>/dev/null; then
        echo "sendmail is already installed."
    elif command -v exim &>/dev/null; then
        echo "Exim is already installed."
    elif command -v postfix &>/dev/null; then
        echo "Postfix is already installed."
    else
        echo "No MTA detected. Do you want to install Postfix? (Y/n)"
        read user_input
        if [ "${user_input,,}" == "y" ]; then
            if [[ "$OS" == "ubuntu" || "$OS" == "debian" ]]; then
                apt-get install postfix -y | tee -a $LOG_FILE || { echo 'Postfix installation failed. Exiting.' | tee -a $LOG_FILE ; exit 1; }
            elif [[ "$OS" == "centOS linux" || "$OS" == "almalinux" || "$OS" == "red hat enterprise linux" ]]; then
                yum install postfix -y | tee -a $LOG_FILE  || { echo 'Postfix installation failed. Exiting.' | tee -a $LOG_FILE ; exit 1; }
            else
                echo "Postfix installation not supported on this OS:$OS. Exiting." | tee -a $LOG_FILE
                exit 1
            fi
            echo "Installation of Postfix successfull" | tee -a $LOG_FILE
        else
            echo "Installation cancelled. Exiting." | tee -a $LOG_FILE
            exit 1
        fi
    fi
}

# Define a function to check if an interface is a NAT interface.
# In this script, we're assuming that NAT interfaces have names that begin with "natbr".
is_nat_interface() {
    local interface=$1
    [[ $interface == natbr* ]]
}

# Setup iptables and required chains
setup_iptables() {
    # Check for iptables
    if command -v iptables &>/dev/null; then
        echo "iptables is already installed." | tee -a $LOG_FILE
    else
        echo "iptables is not installed. Make sure you run VMSentry on an iptables-enabled KVM host. Exiting." | tee -a $LOG_FILE
        exit 1
    fi

    # Setting up OUTGOING_MAIL chain
    echo "Setting up port 25 monitoring via a new OUTGOING_MAIL chain" | tee -a $LOG_FILE
    echo "Checking OUTGOING_MAIL chain..." | tee -a $LOG_FILE
    if iptables -L OUTGOING_MAIL >/dev/null 2>&1; then
        echo 'OUTGOING_MAIL chain already exists.' | tee -a $LOG_FILE
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

initial_checks
install_script
install_python
install_mta
setup_iptables
setup_cron

echo "Install finished. Please check $LOG_FILE for the log" | tee -a $LOG_FILE