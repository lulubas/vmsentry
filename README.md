# VMsentry

## Overview

VMsentry is an alpha-stage security tool that actively monitors your VM's network traffic in a KVM Host, specifically focusing on SMTP connections through port 25. When traffic surpasses defined thresholds, VMsentry takes action as per the mode defined in its configuration. The possible modes include `monitor`, `block`, and `limit`. VMsentry logs all its operations in an orderly and efficient manner. 

**IMPORTANT:** This project is under active development and additional features are expected to be added soon. In particular, we are working on implementing TShark analysis to fine-tune spam detection and analyze packets more effectively. 

Currently, VMsentry is compatible with 5 Linux distributions: Debian, Ubuntu, AlmaLinux, CentOS, and RHEL. The current version only works with NAT routing setups.

## Installation

Install VMsentry by running the following command:

```
bash -c "$(curl -fsSL https://raw.githubusercontent.com/lulubas/vmsentry/main/install.sh)"
```

This script will download and install VMsentry and its dependencies, configure the necessary parameters, and start the monitoring service.

## Configuration

The `config.ini` file is located in `/etc/vmsentry/`. Here, you can configure the timeframe for monitoring, SMTP threshold, unique IPs threshold, and the mode of operation (`monitor`, `block`, `limit`).

## Execution

Once installed, the VMsentry script will run every 10 minutes to monitor the port 25 traffic and take appropriate actions when the set thresholds are reached. You can check the logs at `/etc/vmsentry/logs/vmsentry.log`.

## Support

Feel free to raise an issue on the GitHub page if you face any problems. As this is an alpha version, we appreciate your patience and support in helping us improve this tool.

## Future Plans

Our team is actively working to develop this tool further. Our plans for the future include:

- Implementing TShark analysis to fine-tune spam detection and provide a more comprehensive network traffic analysis.
- Extending support for additional Linux distributions and routing setups.

Please stay tuned for these exciting updates!