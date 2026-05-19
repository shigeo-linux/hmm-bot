#!/bin/bash

set -e

APP_NAME="hmm-bot"
INSTALL_DIR="/opt/${APP_NAME}"
DESKTOP_DIR="/usr/share/applications"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

echo "=== Installing ${APP_NAME} ==="

sudo apt-get update -qq
sudo apt-get install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-requests python3-venv

echo "Copying application files..."
sudo mkdir -p "${INSTALL_DIR}"
sudo cp -r "$(dirname "$0")"/* "${INSTALL_DIR}/"
sudo chmod +x "${INSTALL_DIR}/hmm_bot.py"
sudo chmod +x "${INSTALL_DIR}/runner.py"

echo "Creating virtual environment..."
sudo python3 -m venv --system-site-packages "${INSTALL_DIR}/venv"
sudo "${INSTALL_DIR}/venv/bin/pip" install --quiet \
    hmmlearn pandas numpy requests matplotlib tabulate

echo "Installing desktop entry..."
sudo cp "${INSTALL_DIR}/hmm-bot.desktop" "${DESKTOP_DIR}/"
sudo update-desktop-database "${DESKTOP_DIR}" 2>/dev/null || true

echo "Creating launcher..."
sudo tee /usr/local/bin/hmm-bot > /dev/null << 'EOF'
#!/bin/bash
exec /opt/hmm-bot/venv/bin/python3 /opt/hmm-bot/hmm_bot.py "$@"
EOF
sudo chmod +x /usr/local/bin/hmm-bot

echo "Creating config directory..."
mkdir -p "$HOME/.config/${APP_NAME}"

echo "Installing systemd user timer..."
mkdir -p "${SYSTEMD_USER_DIR}"
cp "${INSTALL_DIR}/hmm-bot.service" "${SYSTEMD_USER_DIR}/hmm-bot.service"
cp "${INSTALL_DIR}/hmm-bot.timer"   "${SYSTEMD_USER_DIR}/hmm-bot.timer"

sudo loginctl enable-linger "$(whoami)"

export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus"

if systemctl --user daemon-reload 2>/dev/null; then
    systemctl --user enable hmm-bot.timer
    systemctl --user start hmm-bot.timer
else
    echo "Note: Timer files installed. Run 'systemctl --user enable --now hmm-bot.timer' after logging in."
fi

echo ""
echo "=== Installation complete! ==="
echo "Run: hmm-bot"
echo ""
echo "Next steps:"
echo "  1. Enter your Telegram bot token and chat ID"
echo "  2. Set your daily signal time (default 9:00)"
echo "  3. Click 'Test Telegram' to verify the connection"
echo "  4. Click 'Send Signal Now' to run immediately"
