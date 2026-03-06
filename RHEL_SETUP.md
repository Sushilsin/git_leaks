# RHEL Setup Guide for Gitleaks MCP Server

This guide provides instructions for setting up and running the Gitleaks MCP Server on Red Hat Enterprise Linux (RHEL) 8 or 9.

## Prerequisites

### 1. Install Required System Packages

```bash
# Enable EPEL repository (Extra Packages for Enterprise Linux)
sudo dnf install -y epel-release

# Update system
sudo dnf update -y

# Install Python 3.11+ (RHEL 9 has Python 3.9 by default, install Python 3.11)
sudo dnf install -y python3.11 python3.11-pip python3.11-devel

# Install development tools
sudo dnf groupinstall -y "Development Tools"

# Install Git
sudo dnf install -y git

# Install curl and wget
sudo dnf install -y curl wget

# Install podman (RHEL's container runtime, alternative to Docker)
sudo dnf install -y podman podman-docker
```

### 2. Install Gitleaks

```bash
# Download and install Gitleaks
GITLEAKS_VERSION="8.21.2"
ARCH=$(uname -m)
if [ "$ARCH" = "x86_64" ]; then ARCH="x64"; fi
if [ "$ARCH" = "aarch64" ]; then ARCH="arm64"; fi

cd /tmp
curl -sL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_${ARCH}.tar.gz" | tar xz
sudo mv gitleaks /usr/local/bin/
sudo chmod +x /usr/local/bin/gitleaks

# Verify installation
gitleaks version
```

### 3. Install Ollama (for Portal)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Enable and start Ollama service
sudo systemctl enable ollama
sudo systemctl start ollama

# Verify Ollama is running
systemctl status ollama

# Pull a model
ollama pull llama3.2
```

## Installation

### 1. Clone or Copy the Repository

```bash
cd /opt
sudo git clone <your-repo-url> git_leaks
sudo chown -R $USER:$USER git_leaks
cd git_leaks
```

### 2. Create Python Virtual Environment

```bash
# Create virtual environment with Python 3.11
python3.11 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install server dependencies
pip install -r requirements.txt

# Install portal dependencies
pip install -r portal_requirements.txt
```

### 3. Create Output Directory

```bash
mkdir -p output
chmod 755 output
```

### 4. Configure Environment

```bash
# Create .env file
cat > .env << 'EOF'
# Ollama Configuration
OLLAMA_HOST=http://localhost:11434
OLLAMA_DEFAULT_MODEL=llama3.2

# Gitleaks Configuration
GITLEAKS_OUTPUT_DIR=/opt/git_leaks/output
GITLEAKS_TIMEOUT=300
GITLEAKS_MAX_CONCURRENT=2
EOF

# Make environment file readable
chmod 644 .env
```

## Running the Application

### Option 1: Run Directly (Development)

```bash
# Activate virtual environment
source .venv/bin/activate

# Run the portal
./start_portal.sh
```

### Option 2: Run as Systemd Service (Production)

Create a systemd service file:

```bash
sudo tee /etc/systemd/system/gitleaks-portal.service > /dev/null << 'EOF'
[Unit]
Description=Gitleaks MCP Portal
After=network.target ollama.service

[Service]
Type=simple
User=$USER
WorkingDirectory=/opt/git_leaks
Environment="PATH=/opt/git_leaks/.venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/opt/git_leaks/.env
ExecStart=/opt/git_leaks/.venv/bin/python /opt/git_leaks/portal.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
sudo systemctl daemon-reload

# Enable and start service
sudo systemctl enable gitleaks-portal
sudo systemctl start gitleaks-portal

# Check status
sudo systemctl status gitleaks-portal

# View logs
sudo journalctl -u gitleaks-portal -f
```

### Option 3: Run with Podman (Containerized)

```bash
# Build container with Podman
podman build -t gitleaks-mcp .

# Run container
podman run -d \
  --name gitleaks-portal \
  -p 5001:5001 \
  -v ./output:/app/output:Z \
  -e OLLAMA_HOST=http://host.containers.internal:11434 \
  gitleaks-mcp

# Check logs
podman logs -f gitleaks-portal

# Stop container
podman stop gitleaks-portal

# Remove container
podman rm gitleaks-portal
```

## Firewall Configuration

If you need to access the portal from other machines:

```bash
# Open port 5001 for the portal
sudo firewall-cmd --permanent --add-port=5001/tcp

# Open port 11434 for Ollama (if needed)
sudo firewall-cmd --permanent --add-port=11434/tcp

# Reload firewall
sudo firewall-cmd --reload

# Verify
sudo firewall-cmd --list-ports
```

## SELinux Configuration

If SELinux is enforcing and causing issues:

```bash
# Check SELinux status
sestatus

# Allow network connections for the service
sudo setsebool -P httpd_can_network_connect 1

# If using containers with volume mounts
sudo chcon -Rt svirt_sandbox_file_t /opt/git_leaks/output

# Or temporarily set SELinux to permissive (not recommended for production)
sudo setenforce 0
```

## Verification

1. **Check Gitleaks Installation:**
   ```bash
   gitleaks version
   ```

2. **Check Ollama:**
   ```bash
   ollama list
   curl http://localhost:11434/api/tags
   ```

3. **Check Portal:**
   ```bash
   curl http://localhost:5001/
   ```

4. **Test MCP Server:**
   ```bash
   source .venv/bin/activate
   python server.py
   # Press Ctrl+C to exit
   ```

## Troubleshooting

### Python Version Issues
```bash
# Verify Python version
python3.11 --version

# If python3.11 not available on RHEL 8
sudo dnf install -y python39
# Then use python3.9 instead
```

### Virtual Environment Issues
```bash
# Recreate virtual environment
rm -rf .venv
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r portal_requirements.txt
```

### Permission Issues
```bash
# Fix ownership
sudo chown -R $USER:$USER /opt/git_leaks

# Fix permissions
chmod -R 755 /opt/git_leaks
chmod 644 /opt/git_leaks/.env
```

### Ollama Connection Issues
```bash
# Check if Ollama is running
systemctl status ollama

# Restart Ollama
sudo systemctl restart ollama

# Check Ollama logs
sudo journalctl -u ollama -n 50
```

### Container Issues with Podman
```bash
# Check Podman version
podman --version

# Reset Podman if needed
podman system reset

# Check for SELinux denials
sudo ausearch -m avc -ts recent
```

## Security Considerations

1. **Run as non-root user** in production
2. **Use SELinux** in enforcing mode
3. **Configure firewall** to restrict access
4. **Regularly update** packages and dependencies
5. **Review scan outputs** for sensitive data before sharing
6. **Use strong authentication** if exposing the portal externally

## Resource Requirements

- **Minimum:** 2 CPU cores, 4 GB RAM, 10 GB disk
- **Recommended:** 4+ CPU cores, 8 GB RAM, 20 GB disk
- **For large repos:** Scale resources based on repository size

## Additional Notes

- RHEL uses `dnf` instead of `apt` for package management
- Podman is the default container runtime (drop-in replacement for Docker)
- SELinux is enabled by default and may require additional configuration
- Firewalld is the default firewall manager
- Systemd is used for service management
