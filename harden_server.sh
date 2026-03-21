#!/bin/bash
set -e

echo "🔒 Hardening Server Security..."

# 1. Update system packages
echo "📦 Updating packages..."
sudo apt-get update
sudo apt-get upgrade -y

# 2. Install fail2ban
echo "🛡️ Installing fail2ban..."
sudo apt-get install fail2ban -y

echo "⚙️ Configuring fail2ban for SSH..."
sudo tee /etc/fail2ban/jail.local > /dev/null << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 5
EOF

sudo systemctl restart fail2ban
sudo systemctl enable fail2ban

# 3. Harden SSH
echo "🔐 Hardening SSH..."
# Backup sshd_config
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak

# Disable Password Authentication
sudo sed -i 's/^#*PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/^#*PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config.d/*.conf 2>/dev/null || true

# Disable Root Login
sudo sed -i 's/^#*PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sudo sed -i 's/^#*PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config

echo "🔄 Restarting SSH daemon..."
sudo systemctl restart sshd

echo "✅ Server hardening complete."
echo "⚠️ IMPORTANT: Ensure you have your PEM key securely stored, as password login and root login are now completely disabled."
