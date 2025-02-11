from flask import Flask, jsonify
import subprocess
import re
from collections import defaultdict

# Configuration
LOG_FILE = "/var/log/smtp_out.log"
SMTP_CHAIN = "SMTP_OUT"

app = Flask(__name__)

def parse_smtp_logs():
    smtp_data = defaultdict(lambda: {"total_packets": 0, "syn_packets": 0, "unique_dst": set()})

    try:
        with open(LOG_FILE, "r") as file:
            for line in file:
                match = re.search(r"SRC=([\d\.]+).*DST=([\d\.]+).*PROTO=TCP SPT=\d+ DPT=25 .* (SYN|ACK|PSH|FIN)", line)
                if match:
                    src_ip, dst_ip, flag = match.groups()
                    smtp_data[src_ip]["total_packets"] += 1  # Count every packet
                    smtp_data[src_ip]["unique_dst"].add(dst_ip)  # Track unique destinations
                    if flag == "SYN":
                        smtp_data[src_ip]["syn_packets"] += 1  # Count new SMTP connections

        # Convert sets to count
        for src_ip in smtp_data:
            smtp_data[src_ip]["unique_dst"] = len(smtp_data[src_ip]["unique_dst"])

    except Exception as e:
        return {"status" : "KO", "message": str(e)}

    return {"status" : "OK", "data" : smtp_data}

def is_ip_blocked(ip):
    try:
        # List current rules and check if the IP is already blocked
        result = subprocess.run(
            f"iptables -C {SMTP_CHAIN} -s {ip} -j DROP",
            shell=True, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return result.returncode == 0  # Return True if rule exists
    except subprocess.CalledProcessError:
        return False

def suspend_ip(ip):
    try:

        if is_ip_blocked(ip):
            return {"status": "KO", "message": f"IP {ip} is already blocked."}

        # Insert DROP rule at the top of SMTP_OUT to prevent logging unnecessary traffic
        subprocess.run(f"iptables -I {SMTP_CHAIN} 1 -s {ip} -j DROP", shell=True, check=True)
        return {"status" : "OK", "message": f"IP {ip} has been suspended from sending emails (Port 25 blocked)."}
    
    except subprocess.CalledProcessError as e:
        return {"status" : "KO", "message": str(e)}


def unsuspend_ip(ip):
    try:
        if not is_ip_blocked(ip):
            return {"status": "KO", "message": f"IP {ip} is not blocked."}

        # Remove any DROP rule for this IP in SMTP_OUT chain
        subprocess.run(f"iptables -D {SMTP_CHAIN} -s {ip} -j DROP", shell=True, check=False)
        return {"status" : "OK", "message": f"IP {ip} has been unsuspended (Port 25 unblocked)."}
    except subprocess.CalledProcessError as e:
        return {"status" : "KO", "message": str(e)}

@app.route("/smtp_stats", methods=["GET"])
def smtp_stats():
    return jsonify(parse_smtp_logs())

@app.route("/suspend_ip/<ip>", methods=["POST"])
def api_suspend_ip(ip):
    return jsonify(suspend_ip(ip))

@app.route("/unsuspend_ip/<ip>", methods=["POST"])
def api_unsuspend_ip(ip):
    return jsonify(unsuspend_ip(ip))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)