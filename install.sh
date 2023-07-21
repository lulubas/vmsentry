#!/bin/bash

echo "Starting installation of VMsentry..."

# Perform initial checks
initial_checks() {
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
        echo "One or more VMsentry directories already exist. Aborting installation..."
        exit 1
    else
        echo "VMsentry does not exist on the system. Pursuing installation..."
    fi

    # Create necessary directories
    mkdir -p $SCRIPT_DIR >/dev/null 2>&1 || { echo "Failed to create $SCRIPT_DIR" | tee -a $LOG_FILE ; exit 1; }
    mkdir -p $LOG_DIR >/dev/null 2>&1 || { echo "Failed to create $LOG_DIR" | tee -a $LOG_FILE ; exit 1; }
    echo "Required directories created successfully" | tee -a $LOG_FILE

    # Set up logging
    exec > >(tee -i $LOG_FILE)
    exec 2>&1
    echo "Logging setup successfully" | tee -a $LOG_FILE

    #Detecting system OS
    OS=""
    {
        if [ -f /etc/os-release ]; then
            . /etc/os-release
            OS=$NAME
            echo "OS detected from /etc/os-release: $OS"
        elif command -v lsb_release >/dev/null 2>&1; then
            OS=$(lsb_release -si)
            echo "OS detected from lsb_release: $OS"
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
    } | tee -a $LOG_FILE

    # Check if the OS is supported, if not exit
    if ! [[ "$OS" == "Ubuntu" || "$OS" == "Debian" || "$OS" == "CentOS Linux" || "$OS" == "AlmaLinux" || "$OS" == "Red Hat Enterprise Linux" ]]; then
        echo "OS not supported: $OS. Exiting." | tee -a $LOG_FILE
        exit 1
    fi
}

install_script() {
     # Check if unzip is installed and install it if it's not
    if ! command -v unzip &> /dev/null; then
        echo "Unzip could not be found" | tee -a $LOG_FILE
        echo "Attempting to install unzip..." | tee -a $LOG_FILE
        if [ "$OS" == "Ubuntu" ] || [ "$OS" == "Debian" ]; then
            apt-get install unzip -y >/dev/null 2>&1 || { echo "Failed to install unzip on $OS" | tee -a $LOG_FILE ; exit 1; }
        elif [ "$OS" == "CentOS" ] || [ "$OS" == "Redhat" ]; then
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

    # Unzip the downloaded file
    echo "Unzipping VMsentry archive..." | tee -a $LOG_FILE
    unzip /etc/vmsentry/vmsentry.zip -d /etc/vmsentry/ >/dev/null 2>&1 || { echo "Failed to unzip VMsentry archive" | tee -a $LOG_FILE ; exit 1; }

    # Remove the downloaded .zip file
    echo "Removing installation archive..." | tee -a $LOG_FILE
    rm /etc/vmsentry/vmsentry.zip || { echo "Failed to remove VMsentry archive" | tee -a $LOG_FILE ; exit 1; }
    echo "VMsentry installation archive successfully removed" | tee -a $LOG_FILE

    echo "VMsentry downloaded and unzipped successfully" | tee -a $LOG_FILE
}

# Check and Install Python function
install_python() {
    if command -v python3 &>/dev/null; then
        echo "Python 3 is already installed"
    else
        echo "Python 3 is not yet installed. Starting installation now..."
        if [[ "$OS" == "Ubuntu" || "$OS" == "Debian" ]]; then
            apt-get update | tee -a $LOG_FILE || { echo 'Updating packages failed' | tee -a $LOG_FILE ; exit 1; }
            apt-get install python3 -y | tee -a $LOG_FILE || { echo 'Python3 installation failed' | tee -a $LOG_FILE ; exit 1; }
        elif [[ "$OS" == "CentOS Linux" || "$OS" == "AlmaLinux" || "$OS" == "Red Hat Enterprise Linux" ]]; then
            yum install python3 -y | tee -a $LOG_FILE || { echo 'Python3 installation failed' | tee -a $LOG_FILE ; exit 1; }
        else
            echo "Python installation not supported on this OS"
            exit 1
        fi
        echo "Python 3 has been installed."
    fi
}

# Check and Install Postfix if no MTA is currently installed
install_mta() {
    if command -v sendmail &>/dev/null; then
        echo "sendmail is already installed. Continuing"
    elif command -v exim &>/dev/null; then
        echo "Exim is already installed. Continuing"
    elif command -v postfix &>/dev/null; then
        echo "Postfix is already installed. Continuing"
    else
        echo "No MTA detected. Do you want to install Postfix? (y/n)"
        read answer
        if [[ "$answer" == "y" || "$answer" == "Y" ]]; then
            if [[ "$OS" == "Ubuntu" || "$OS" == "Debian" ]]; then
                apt-get install postfix -y | tee -a $LOG_FILE || { echo 'Postfix installation failed. Exiting.' | tee -a $LOG_FILE ; exit 1; }
            elif [[ "$OS" == "CentOS Linux" || "$OS" == "AlmaLinux" || "$OS" == "Red Hat Enterprise Linux" ]]; then
                yum install postfix -y | tee -a $LOG_FILE  || { echo 'Postfix installation failed. Exiting.' | tee -a $LOG_FILE ; exit 1; }
            else
                echo "Postfix installation not supported on this OS"
                exit 1
            fi
            echo "Installation of Postfix successfull" | tee -a $LOG_FILE
        else
            echo "Installation cancelled. Exiting." | tee -a $LOG_FILE
            exit 1
        fi
    fi
}

# Setup iptables and required chains
setup_iptables() {
    # Install iptables
    if command -v iptables &>/dev/null; then
        echo "iptables is already installed. Continuing" | tee -a $LOG_FILE
    else
        echo "iptables is not yet installed. Starting to install now." | tee -a $LOG_FILE
        if [[ "$OS" == "Ubuntu" || "$OS" == "Debian" ]]; then
            apt-get install iptables -y | tee -a $LOG_FILE || { echo 'Iptables installation failed. Exiting.' | tee -a $LOG_FILE ; exit 1; }
        elif [[ "$OS" == "CentOS Linux" || "$OS" == "AlmaLinux" || "$OS" == "Red Hat Enterprise Linux" ]]; then
            yum install iptables -y | tee -a $LOG_FILE || { echo 'IPtables installation failed. Exiting.' | tee -a $LOG_FILE ; exit 1; }
        else
            echo "iptables installation not supported on this OS"
            exit 1
        fi
        echo "iptables installation successfull" | tee -a $LOG_FILE
    fi

    # Seting up logging of port 25 traffic via LOG_ONLY chain
    echo "Setting up port 25 monitoring" | tee -a $LOG_FILE
    iptables -N LOG_ONLY >/dev/null 2>&1 || { echo 'LOG_ONLY chain already exists. Exiting.' | tee -a $LOG_FILE ; exit 1; }
    iptables -A LOG_ONLY -j LOG --log-prefix "[VMS#0] Logged: " --log-level 4 || { echo 'Failed to add LOG rule to LOG_ONLY chain. Exiting.' | tee -a $LOG_FILE ; exit 1; }
    iptables -A LOG_ONLY -j ACCEPT || { echo 'Failed to add ACCEPT rule to LOG_ONLY chain. Exiting.' | tee -a $LOG_FILE ; exit 1; }
    echo "LOG_ONLY chain created and LOG and ACCEPT rules added" | tee -a $LOG_FILE

    MAIN_IFACE=$(ip route show default | awk '/default/ {print $5}' | sed -n 2p)
    echo "Main network interface detected: $MAIN_IFACE" | tee -a $LOG_FILE
    iptables -I FORWARD -o $MAIN_IFACE -p tcp --dport 25 -j LOG_ONLY || { echo 'Failed to add LOG_ONLY rule to FORWARD chain. Exiting.' | tee -a $LOG_FILE ; exit 1; }
    echo "Port 25 traffic redirected to LOG_ONLY chain" | tee -a $LOG_FILE

    # Setuping up the LOG_AND_DROP chain and rules
    echo "Creating LOG_AND_DROP chain and rules" | tee -a $LOG_FILE
    iptables -N LOG_AND_DROP >/dev/null 2>&1 || { echo 'LOG_AND_DROP chain already exists. Exiting.' | tee -a $LOG_FILE ; exit 1; }
    iptables -A LOG_AND_DROP -j LOG --log-prefix "[VMS#1] Dropped: " --log-level 4 || { echo 'Failed to add LOG rule to LOG_AND_DROP chain. Exiting.' | tee -a $LOG_FILE ; exit 1; }
    iptables -A LOG_AND_DROP -j DROP || { echo 'Failed to add DROP rule to LOG_AND_DROP chain. Exiting.' | tee -a $LOG_FILE ; exit 1; }
    echo "iptables LOG_AND_DROP chain and rules created successfully" | tee -a $LOG_FILE

    # Change the log location
    echo -e ':msg, startswith, "VMS#0" -/etc/vmsentry/logs/iptables_all_25.log\n:msg, startswith, "VMS#1" -/etc/vmsentry/logs/iptables_dropped_25.log' > /etc/rsyslog.d/vms_iptables.conf | tee -a $LOG_FILE || { echo 'Failed to edit VMS log location in rsyslog. Exiting.' | tee -a $LOG_FILE ; exit 1; }
    echo "Rsyslog configuration file updated to redirect iptables outgoing port 25 logs" | tee -a $LOG_FILE
    echo "Restarting Rsyslog..." | tee -a $LOG_FILE
    systemctl restart rsyslog | tee -a $LOG_FILE || { echo 'Failed to restart rsyslog.' | tee -a $LOG_FILE ; exit 1; }
    echo "Rsyslog restarted successfully" | tee -a $LOG_FILE
}

# Setup cron job to run every X minutes
setup_cron() {
    # Name of the cron job for easy identification
    CRON_NAME="VMsentry"

    # Check if the cron job already exists
    if crontab -l | grep -q "$CRON_NAME"; then
        echo "Cron job already exists. Skipping addition." | tee -a $LOG_FILE
    else
        # Cron job does not exist, add it
        echo "Adding cron job..." | tee -a $LOG_FILE
        # Write out current crontab to a temp file
        crontab -l > mycron || { echo "Failed to write current crontab to file. Exiting." | tee -a $LOG_FILE ; exit 1; }
        # Echo new cron into cron file, run script every 10 minutes
        echo "*/10 * * * * /usr/bin/python3 /etc/vmsentry/vm_sentry.py # $CRON_NAME" >> mycron
        # Install new cron file
        crontab mycron || { echo "Failed to install new crontab. Exiting." | tee -a $LOG_FILE ; exit 1; }
        rm mycron
        echo "Cron job added successfully." | tee -a $LOG_FILE
    fi
}

initial_checks
install_script
install_python
install_mta
setup_iptables
setup_cron

echo "Install finished. Please check $LOG_FILE for the log"