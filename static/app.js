document.addEventListener('DOMContentLoaded', () => {
    // UI Elements
    const credStatusBadge = document.getElementById('cred-status-badge');
    const inputAccessKey = document.getElementById('aws-access-key');
    const inputSecretKey = document.getElementById('aws-secret-key');
    const inputRegion = document.getElementById('aws-region');
    const btnSaveCreds = document.getElementById('btn-save-creds');

    const btnDeploy = document.getElementById('btn-deploy');
    const btnCleanup = document.getElementById('btn-cleanup');
    const btnRefresh = document.getElementById('btn-refresh');

    const resourceStatusBadge = document.getElementById('resource-status-badge');
    const valInstanceId = document.getElementById('val-instance-id');
    const valPublicIp = document.getElementById('val-public-ip');
    const valPublicDns = document.getElementById('val-public-dns');
    const valKeyName = document.getElementById('val-key-name');
    const valMonitoring = document.getElementById('val-monitoring');
    const sshBox = document.getElementById('ssh-box');
    const sshCommand = document.getElementById('ssh-command');
    const btnCopySsh = document.getElementById('btn-copy-ssh');

    const consoleOutput = document.getElementById('console-output');
    const btnClearConsole = document.getElementById('btn-clear-console');

    const globalIndicator = document.getElementById('global-status-indicator');
    const globalText = document.getElementById('global-status-text');

    let logEventSource = null;

    // Helper functions
    function logToConsole(message, type = 'line') {
        const line = document.createElement('div');
        line.className = `console-line ${type}-line`;
        
        // Clean line formatting
        let text = message.trim();
        if (text.startsWith('data:')) {
            text = text.substring(5).trim();
        }

        if (!text) return;

        // Custom highlighting
        if (text.includes('[+]') || text.includes('SUCCESSFUL')) {
            line.classList.add('success-line');
        } else if (text.includes('[!]') || text.includes('[Error]') || text.includes('Error')) {
            line.classList.add('error-line');
        } else if (text.startsWith('[*]')) {
            line.classList.add('system-line');
        }

        line.textContent = text;
        consoleOutput.appendChild(line);
        consoleOutput.scrollTop = consoleOutput.scrollHeight;
    }

    function disableActions(disabled) {
        btnDeploy.disabled = disabled;
        btnCleanup.disabled = disabled;
        btnSaveCreds.disabled = disabled;
        if (disabled) {
            btnDeploy.style.opacity = '0.5';
            btnCleanup.style.opacity = '0.5';
            globalIndicator.className = 'pulse-indicator active';
            globalText.textContent = 'Active Process...';
        } else {
            btnDeploy.style.opacity = '1';
            btnCleanup.style.opacity = '1';
            globalIndicator.className = 'pulse-indicator';
            globalText.textContent = 'Idle';
        }
    }

    // API Integration

    // 1. Check Credentials Status
    async function checkCredentials() {
        try {
            const response = await fetch('/api/credentials');
            const data = await response.json();
            if (data.configured) {
                credStatusBadge.textContent = 'Configured';
                credStatusBadge.className = 'badge badge-success';
                globalIndicator.className = 'pulse-indicator';
                globalText.textContent = 'Connected';
            } else {
                credStatusBadge.textContent = 'Not Configured';
                credStatusBadge.className = 'badge badge-warning';
                globalText.textContent = 'Credentials Required';
            }
            if (data.region) {
                inputRegion.value = data.region;
            }
        } catch (e) {
            console.error('Error fetching credentials:', e);
            logToConsole('[Error] Failed to connect to local API server.', 'error');
        }
    }

    // 2. Save Credentials
    btnSaveCreds.addEventListener('click', async () => {
        const accessKey = inputAccessKey.value.trim();
        const secretKey = inputSecretKey.value.trim();
        const region = inputRegion.value.trim() || 'us-east-1';

        if (!accessKey || !secretKey) {
            alert('Please enter both AWS Access Key ID and Secret Access Key.');
            return;
        }

        btnSaveCreds.textContent = 'Saving...';
        btnSaveCreds.disabled = true;

        try {
            const response = await fetch('/api/credentials', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ accessKey, secretKey, region })
            });
            const data = await response.json();
            if (data.success) {
                logToConsole('[*] AWS Credentials successfully saved to credentials files.');
                inputAccessKey.value = '';
                inputSecretKey.value = '';
                checkCredentials();
            } else {
                logToConsole('[Error] Failed to save credentials: ' + data.error, 'error');
            }
        } catch (e) {
            logToConsole('[Error] Connection issues saving credentials.', 'error');
        } finally {
            btnSaveCreds.textContent = 'Save Credentials';
            btnSaveCreds.disabled = false;
        }
    });

    // 3. Get Resource State
    async function refreshResourceState() {
        resourceStatusBadge.textContent = 'Checking...';
        resourceStatusBadge.className = 'badge';

        try {
            const response = await fetch('/api/state');
            const data = await response.json();

            if (data.state_exists) {
                const s = data.state;
                resourceStatusBadge.textContent = data.instance_status.toUpperCase();
                
                if (data.instance_status === 'running') {
                    resourceStatusBadge.className = 'badge badge-success';
                } else if (data.instance_status === 'pending' || data.instance_status === 'shutting-down') {
                    resourceStatusBadge.className = 'badge badge-warning';
                } else {
                    resourceStatusBadge.className = 'badge';
                }

                valInstanceId.textContent = s.instance_id || '-';
                valPublicIp.textContent = s.public_ip || '-';
                valPublicDns.textContent = s.public_dns || '-';
                valKeyName.textContent = s.key_name || '-';
                valMonitoring.textContent = s.alarm_name ? 'Active (CloudWatch)' : 'None';

                if (data.instance_status === 'running' && s.public_ip) {
                    sshCommand.textContent = `ssh -i "${s.key_name}.pem" ec2-user@${s.public_ip}`;
                    sshBox.style.display = 'block';
                } else {
                    sshBox.style.display = 'none';
                }
            } else {
                resourceStatusBadge.textContent = 'Not Deployed';
                resourceStatusBadge.className = 'badge';
                valInstanceId.textContent = '-';
                valPublicIp.textContent = '-';
                valPublicDns.textContent = '-';
                valKeyName.textContent = '-';
                valMonitoring.textContent = 'None';
                sshBox.style.display = 'none';
            }
        } catch (e) {
            console.error('Error refreshing state:', e);
            resourceStatusBadge.textContent = 'ERROR';
        }
    }

    // 4. Stream Deploy Process Logs
    btnDeploy.addEventListener('click', () => {
        if (logEventSource) {
            logEventSource.close();
        }

        logToConsole('\n[System] Initiating Lab Deployment Process...', 'system');
        disableActions(true);

        logEventSource = new EventSource('/api/deploy');

        logEventSource.onmessage = (event) => {
            const text = event.data;
            if (text.includes('[EOF] Process finished')) {
                logToConsole('[System] Deployment thread finished.', 'system');
                logEventSource.close();
                logEventSource = null;
                disableActions(false);
                refreshResourceState();
            } else {
                logToConsole(text);
            }
        };

        logEventSource.onerror = (err) => {
            logToConsole('[Error] Deployment event source error or connection lost.', 'error');
            logEventSource.close();
            logEventSource = null;
            disableActions(false);
            refreshResourceState();
        };
    });

    // 5. Stream Cleanup Process Logs
    btnCleanup.addEventListener('click', () => {
        if (logEventSource) {
            logEventSource.close();
        }

        logToConsole('\n[System] Initiating Lab Teardown Process...', 'system');
        disableActions(true);

        logEventSource = new EventSource('/api/cleanup');

        logEventSource.onmessage = (event) => {
            const text = event.data;
            if (text.includes('[EOF] Process finished')) {
                logToConsole('[System] Teardown thread finished.', 'system');
                logEventSource.close();
                logEventSource = null;
                disableActions(false);
                refreshResourceState();
            } else {
                logToConsole(text);
            }
        };

        logEventSource.onerror = (err) => {
            logToConsole('[Error] Teardown event source error or connection lost.', 'error');
            logEventSource.close();
            logEventSource = null;
            disableActions(false);
            refreshResourceState();
        };
    });

    // 6. Manual refresh
    btnRefresh.addEventListener('click', () => {
        refreshResourceState();
    });

    // Copy SSH connection string
    btnCopySsh.addEventListener('click', () => {
        const text = sshCommand.textContent;
        navigator.clipboard.writeText(text).then(() => {
            btnCopySsh.textContent = 'Copied!';
            setTimeout(() => {
                btnCopySsh.textContent = 'Copy';
            }, 2000);
        }).catch(err => {
            console.error('Could not copy command string: ', err);
        });
    });

    // Clear log console
    btnClearConsole.addEventListener('click', () => {
        consoleOutput.innerHTML = '<div class="console-line system-line">[System] Console cleared.</div>';
    });

    // Initialize App
    checkCredentials();
    refreshResourceState();
});
