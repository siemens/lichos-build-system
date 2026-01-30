"""Container-related utilities and setup scripts."""

import logging

logger = logging.getLogger(__name__)


class ContainerUtils:
    """Utility class for container setup and configuration."""

    @staticmethod
    def get_ssh_setup_script() -> str:
        """
        Get a generic SSH setup script for containerized environments.

        This script sets up SSH daemon in a container to enable remote development
        connections (e.g., VS Code Remote - SSH).

        Returns:
            str: Complete bash script for SSH setup
        """
        return """
set -e
echo "Container starting..."

# SSH Setup
echo "Starting SSH setup..."

# Install openssh-server if not already installed
if ! command -v sshd &> /dev/null; then
    echo "Installing openssh-server..."
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server sudo procps net-tools
fi

# Set root password for SSH access
echo "root:root" | chpasswd
echo "Root password set for SSH access"

# Setup SSH directory for root
mkdir -p /root/.ssh
chmod 700 /root/.ssh

# Copy host's public keys for passwordless login
echo "Setting up SSH key authentication for root user..."
if [ -f /root/.ssh/authorized_keys ]; then
    echo "Using existing authorized_keys"
fi

# Add user's public key from common locations
for key_file in id_rsa.pub id_ecdsa.pub id_ed25519.pub; do
    if [ -f "/tmp/ssh_keys/$key_file" ]; then
        cat "/tmp/ssh_keys/$key_file" >> /root/.ssh/authorized_keys
        echo "Added $key_file to authorized_keys"
    fi
done

# Set proper permissions for SSH keys
if [ -f /root/.ssh/authorized_keys ]; then
    chmod 600 /root/.ssh/authorized_keys
    echo "SSH key authentication configured for root user"
fi

if [ -f /tmp/container_env ]; then
    cat > /etc/profile.d/container-env.sh << 'ENVEOF'

if [ -f /tmp/container_env ]; then
    set -a  # automatically export all variables
    . /tmp/container_env
    set +a
fi

ENVEOF
    chmod +x /etc/profile.d/container-env.sh

    # Setup for root's bashrc as well
    if ! grep -q "source /tmp/container_env" /root/.bashrc 2>/dev/null; then
        echo '# Source container environment variables' >> /root/.bashrc
        echo 'export LC_ALL=C' >> /root/.bashrc
        echo 'set -a' >> /root/.bashrc
        echo '. /tmp/container_env' >> /root/.bashrc
        echo 'set +a' >> /root/.bashrc
    fi
    echo "Environment variables configured for SSH sessions"
else
    echo "No container environment file found at /tmp/container_env"
fi

echo "Configuring SSH daemon..."
mkdir -p /var/run/sshd /var/log

# Create a minimal working SSH configuration
cat > /etc/ssh/sshd_config << 'SSHEOF'
Port 22
PermitRootLogin yes
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys
PasswordAuthentication yes
UsePAM yes
X11Forwarding yes
PrintMotd no
PermitUserEnvironment yes
Subsystem sftp /usr/lib/openssh/sftp-server
SSHEOF

echo "Generating SSH host keys..."
ssh-keygen -A

echo "Testing SSH configuration..."
/usr/sbin/sshd -t || { echo "SSH config test failed"; exit 1; }

echo "Starting SSH daemon..."
/usr/sbin/sshd -D -e &
SSHD_PID=$!

# Wait and verify SSH is running
sleep 5

if ps -p $SSHD_PID > /dev/null 2>&1; then
    echo "SSH daemon started successfully (PID: $SSHD_PID)"
    # Test if SSH is listening
    if netstat -tlnp | grep :22 > /dev/null; then
        echo "SSH daemon is listening on port 22"
    else
        echo "WARNING: SSH daemon not listening on port 22"
    fi
else
    echo "ERROR: SSH daemon failed to start"
    echo "Checking for SSH daemon errors..."
    tail -20 /var/log/auth.log 2>/dev/null || echo "No auth log available"
    exit 1
fi

echo "Container ready for VS Code Remote - SSH connection"
echo "SSH setup completed, keeping container alive..."
""".strip()

    @staticmethod
    def get_container_keepalive_script() -> str:
        """
        Get a script to keep container running indefinitely.

        Returns:
            str: Simple keepalive script
        """
        return "tail -f /dev/null"

    @staticmethod
    def build_ssh_enabled_command(base_command: str = None) -> str:
        """
        Build a command that sets up SSH and optionally runs a base command.

        Args:
            base_command: Optional command to run after SSH setup

        Returns:
            str: Combined command string
        """
        ssh_script = ContainerUtils.get_ssh_setup_script()

        if base_command:
            return f"{ssh_script}\n{base_command}"
        else:
            return f"{ssh_script}\n{ContainerUtils.get_container_keepalive_script()}"
