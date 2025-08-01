# LiveKit Self-Hosting on AWS EC2 - Deployment Guide

## Overview
This guide helps you deploy LiveKit server on AWS EC2 for reduced latency and WebRTC optimization in your voice agent project.

## Prerequisites
- AWS Account with EC2 access
- Domain name (for TLS/TURN configuration)
- Basic knowledge of AWS EC2 and security groups

## EC2 Instance Requirements

### Recommended Instance Type
- **Production**: `c5.xlarge` or `c5.2xlarge` (compute-optimized)
- **Testing**: `t3.medium` or `t3.large`
- **Minimum**: 2 vCPU, 4GB RAM, 20GB storage

### Operating System
- Ubuntu 22.04 LTS (recommended)
- Amazon Linux 2023 (alternative)

## Step 1: Launch EC2 Instance

### 1.1 Create Security Group
```bash
# Allow SSH (22), HTTP (80), HTTPS (443), LiveKit (7880), TURN (3478)
# WebRTC UDP range (50000-60000)

Inbound Rules:
- SSH (22): Your IP
- HTTP (80): 0.0.0.0/0
- HTTPS (443): 0.0.0.0/0
- Custom TCP (7880): 0.0.0.0/0  # LiveKit
- Custom UDP (3478): 0.0.0.0/0  # TURN
- Custom UDP (50000-60000): 0.0.0.0/0  # WebRTC
```

### 1.2 Launch Instance
1. Choose Ubuntu 22.04 LTS AMI
2. Select instance type (c5.xlarge recommended)
3. Configure storage (20GB minimum)
4. Attach security group created above
5. Create/use existing key pair

## Step 2: Install LiveKit Server

### 2.1 Connect to Instance
```bash
ssh -i your-key.pem ubuntu@your-ec2-public-ip
```

### 2.2 Install LiveKit
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install LiveKit
curl -sSL https://get.livekit.io | bash

# Verify installation
livekit-server --version
```

## Step 3: Configure LiveKit

### 3.1 Create Configuration File
```bash
sudo mkdir -p /etc/livekit
sudo nano /etc/livekit/livekit.yaml
```

### 3.2 Basic Configuration (`/etc/livekit/livekit.yaml`)
```yaml
port: 7880
bind_addresses:
  - ""

# Replace with your domain
rtc:
  tcp_port: 7881
  port_range_start: 50000
  port_range_end: 60000
  use_external_ip: true

# Generate secure keys
keys:
  your_api_key: your_secret_key

# Redis for scaling (optional)
redis:
  address: localhost:6379

# TURN server configuration
turn:
  enabled: true
  domain: your-domain.com
  cert_file: /etc/letsencrypt/live/your-domain.com/fullchain.pem
  key_file: /etc/letsencrypt/live/your-domain.com/privkey.pem
  tls_port: 5349
  udp_port: 3478

# Webhook for SIP (if using Twilio)
webhook:
  api_key: your_webhook_key
  urls:
    - http://localhost:9090/webhook

# Logging
logging:
  level: info
  json: true
```

### 3.3 Generate API Keys
```bash
# Generate secure API key and secret
livekit-cli create-token \
  --api-key your_api_key \
  --api-secret your_secret_key \
  --room test-room \
  --identity test-user \
  --valid-for 24h
```

## Step 4: SSL/TLS Setup (Required for Production)

### 4.1 Install Certbot
```bash
sudo apt install certbot nginx -y
```

### 4.2 Configure Nginx Reverse Proxy
```bash
sudo nano /etc/nginx/sites-available/livekit
```

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        return 301 https://$server_name$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    location / {
        proxy_pass http://localhost:7880;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 4.3 Get SSL Certificate
```bash
# Get certificate
sudo certbot --nginx -d your-domain.com

# Enable nginx
sudo systemctl enable nginx
sudo systemctl start nginx
```

## Step 5: Create Systemd Service

### 5.1 Create Service File
```bash
sudo nano /etc/systemd/system/livekit.service
```

```ini
[Unit]
Description=LiveKit Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu
ExecStart=/usr/local/bin/livekit-server --config /etc/livekit/livekit.yaml
Restart=always
RestartSec=5
Environment=PATH=/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
```

### 5.2 Enable and Start Service
```bash
sudo systemctl daemon-reload
sudo systemctl enable livekit
sudo systemctl start livekit
sudo systemctl status livekit
```

## Step 6: Configure Voice Agent

### 6.1 Update Environment Variables
```bash
# In your voice agent project .env file
LIVEKIT_URL=wss://your-domain.com
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_secret_key
```

### 6.2 Test Connection
```bash
# Test from your voice agent
python agent.py dev
```

## Step 7: Performance Optimization

### 7.1 System Optimization
```bash
# Increase file limits
echo "* soft nofile 65536" | sudo tee -a /etc/security/limits.conf
echo "* hard nofile 65536" | sudo tee -a /etc/security/limits.conf

# Optimize network
echo "net.core.rmem_max = 134217728" | sudo tee -a /etc/sysctl.conf
echo "net.core.wmem_max = 134217728" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### 7.2 Monitor Performance
```bash
# Install monitoring tools
sudo apt install htop iotop nethogs -y

# Monitor LiveKit logs
sudo journalctl -u livekit -f
```

## Step 8: Firewall Configuration

### 8.1 UFW Setup (if using Ubuntu firewall)
```bash
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443
sudo ufw allow 7880
sudo ufw allow 3478/udp
sudo ufw allow 50000:60000/udp
sudo ufw enable
```

## Troubleshooting

### Common Issues

1. **WebRTC Connection Failed**
   - Check UDP port range (50000-60000) is open
   - Verify TURN server configuration
   - Ensure external IP is correctly detected

2. **SSL Certificate Issues**
   - Verify domain points to EC2 public IP
   - Check certificate renewal: `sudo certbot renew --dry-run`

3. **High Latency**
   - Use compute-optimized instances (c5.xlarge+)
   - Enable enhanced networking
   - Consider placement groups for multiple instances

### Logs and Debugging
```bash
# LiveKit server logs
sudo journalctl -u livekit -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log

# System resources
htop
iotop
```

## Cost Optimization

### Instance Scheduling
```bash
# Auto-start/stop for development
# Create Lambda function or use AWS Instance Scheduler
```

### Reserved Instances
- Use Reserved Instances for production (up to 75% savings)
- Consider Spot Instances for development/testing

## Security Best Practices

1. **API Keys**: Use strong, unique API keys
2. **Firewall**: Restrict SSH access to your IP
3. **Updates**: Keep system and LiveKit updated
4. **Monitoring**: Set up CloudWatch alarms
5. **Backup**: Regular configuration backups

## Performance Comparison

Expected latency improvements with self-hosting:
- **Cloud LiveKit**: 150-300ms total latency
- **Self-hosted (same region)**: 50-150ms total latency
- **Self-hosted (optimized)**: 30-100ms total latency

## Next Steps

1. Deploy on EC2 following this guide
2. Test voice agent with self-hosted setup
3. Compare latency measurements
4. Optimize based on your specific requirements
5. Set up monitoring and alerting

## Support

- LiveKit Documentation: https://docs.livekit.io/
- AWS EC2 Documentation: https://docs.aws.amazon.com/ec2/
- Community Support: https://livekit.io/community
