# AWS EC2 Security Hardening Lab

This repository contains a premium automation suite and web dashboard for provisioning, hardening, and monitoring AWS EC2 instances securely. It implements standard Cloud Security best practices.

---

## 🌐 Web Dashboard UI

A local web application is provided to manage the lab exercises directly from your browser. 

### Features:
- **AWS Configuration**: Save and manage AWS credentials securely.
- **Action Controls**: Deploy or clean up all AWS resources with a single click.
- **Live Terminal Console**: Streams the execution logs of the backend scripts in real-time.
- **Resource Details Card**: Dynamically displays provisioned resource IDs, public IPs, DNS, and a copyable SSH connection string.

---

## 🚀 Getting Started

### 1. Install Dependencies
Ensure you have Python 3 and Pip installed, then run:
```bash
pip install boto3 requests flask
```

### 2. Launch the Web Dashboard Server
Run the local Flask server:
```bash
python server.py
```

### 3. Open the Dashboard in Browser
Access the dashboard at:
👉 **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

---

## 🛠️ Script Components

If you prefer to run the automation via CLI, the following scripts are available in the root folder:

- **`run_project_1.py`**:
  - Automatically fetches your current public IP.
  - Generates an EC2 Key Pair (`project1-key`) and secures the local `.pem` permissions.
  - Creates a Security Group that restricts SSH access to only your public IP.
  - Launches a `t2.micro` EC2 instance with custom security-hardening User Data (updates OS, creates a new admin user `newuser`, and disables root login & password authentication in SSH settings).
  - Configures a CloudWatch alarm and SNS topic to monitor CPU Utilization (> 80%).

- **`cleanup_project_1.py`**:
  - Automatically tears down all deployed resources in the correct order to ensure zero cost leftovers.
