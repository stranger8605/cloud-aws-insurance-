import os
import json
import subprocess
import sys
from pathlib import Path
from flask import Flask, render_template, request, Response, jsonify

# Pre-import verification to ensure packages are accessible
try:
    import boto3
    import requests
except ImportError:
    pass

app = Flask(__name__, template_folder='templates', static_folder='static')

STATE_FILE = "project1_state.json"

def credentials_configured():
    """Check if standard AWS credentials exist or env variable is set."""
    aws_dir = Path.home() / '.aws'
    credentials_path = aws_dir / 'credentials'
    return credentials_path.exists() or os.environ.get('AWS_ACCESS_KEY_ID') is not None

@app.route('/')
def index():
    """Render the main single page dashboard."""
    return render_template('index.html')

@app.route('/api/credentials', methods=['GET', 'POST'])
def api_credentials():
    """Get status of credentials or write new credentials to ~/.aws/credentials."""
    aws_dir = Path.home() / '.aws'
    credentials_path = aws_dir / 'credentials'
    config_path = aws_dir / 'config'

    if request.method == 'GET':
        configured = credentials_configured()
        region = "us-east-1"
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    for line in f:
                        if 'region' in line:
                            region = line.split('=')[-1].strip()
            except Exception:
                pass
        return jsonify({
            "configured": configured,
            "region": region
        })

    elif request.method == 'POST':
        data = request.json
        access_key = data.get('accessKey', '').strip()
        secret_key = data.get('secretKey', '').strip()
        region = data.get('region', 'us-east-1').strip()

        if not access_key or not secret_key:
            return jsonify({"success": False, "error": "Access Key and Secret Key are required."}), 400

        try:
            aws_dir.mkdir(exist_ok=True)
            with open(credentials_path, 'w') as f:
                f.write(f"[default]\naws_access_key_id = {access_key}\naws_secret_access_key = {secret_key}\n")
            with open(config_path, 'w') as f:
                f.write(f"[default]\nregion = {region}\n")
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/state', methods=['GET'])
def api_state():
    """Fetch current deployment metadata and live instance status from AWS."""
    state_exists = os.path.exists(STATE_FILE)
    state_data = {}
    instance_status = "Not Deployed"
    
    if state_exists:
        try:
            with open(STATE_FILE, 'r') as f:
                state_data = json.load(f)
            
            instance_id = state_data.get("instance_id")
            region = state_data.get("region", "us-east-1")
            
            if instance_id:
                # Import boto3 dynamically to prevent start crash if not fully installed yet
                import boto3
                ec2 = boto3.client('ec2', region_name=region)
                response = ec2.describe_instances(InstanceIds=[instance_id])
                if response['Reservations']:
                    instance = response['Reservations'][0]['Instances'][0]
                    state = instance['State']['Name']
                    instance_status = state
                    state_data["public_ip"] = instance.get('PublicIpAddress', 'N/A')
                    state_data["public_dns"] = instance.get('PublicDnsName', 'N/A')
                else:
                    instance_status = "Terminated (Not found in AWS)"
        except Exception as e:
            instance_status = f"Status Unknown ({str(e)})"
            
    return jsonify({
        "state_exists": state_exists,
        "state": state_data,
        "instance_status": instance_status
    })

@app.route('/api/deploy', methods=['GET'])
def api_deploy():
    """Stream run_project_1.py stdout in real-time to front-end."""
    if not credentials_configured():
        def error_gen():
            yield "data: [Error] AWS credentials are not configured. Please save credentials first.\n\n"
            yield "data: [EOF] Process finished with exit code 1\n\n"
        return Response(error_gen(), mimetype='text/event-stream')

    def run_deploy():
        process = subprocess.Popen(
            [sys.executable, "-u", "run_project_1.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        for line in iter(process.stdout.readline, ""):
            yield f"data: {line}\n\n"
            
        process.stdout.close()
        return_code = process.wait()
        yield f"data: [EOF] Process finished with exit code {return_code}\n\n"

    return Response(run_deploy(), mimetype='text/event-stream')

@app.route('/api/cleanup', methods=['GET'])
def api_cleanup():
    """Stream cleanup_project_1.py stdout in real-time to front-end."""
    def run_cleanup():
        process = subprocess.Popen(
            [sys.executable, "-u", "cleanup_project_1.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        for line in iter(process.stdout.readline, ""):
            yield f"data: {line}\n\n"
            
        process.stdout.close()
        return_code = process.wait()
        yield f"data: [EOF] Process finished with exit code {return_code}\n\n"

    return Response(run_cleanup(), mimetype='text/event-stream')

if __name__ == '__main__':
    print("[*] Starting local Flask server on http://127.0.0.1:5000")
    app.run(debug=True, host='127.0.0.1', port=5000)
