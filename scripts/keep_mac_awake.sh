#!/bin/bash
# Newt — configure macOS so the system never sleeps but the display can,
# so the Newt bridge stays reachable from your phone overnight.
#
# Run once. Settings persist across reboots.
# You'll be asked for your Mac password (needed for `pmset`).

G='\033[0;32m'; Y='\033[1;33m'; B='\033[0;36m'; N='\033[0m'

echo ""
echo "=========================================="
echo "  Newt — keep-awake configuration         "
echo "=========================================="
echo ""
echo "Setting your Mac to:"
echo "  • Never sleep when on AC power (bridge stays online)"
echo "  • Display turns off after 10 minutes (saves screen / power)"
echo "  • Disks never spin down (avoid wake-up lag)"
echo ""
echo "macOS will ask for your password to apply these."
echo ""

# Configure for AC power (the only profile that matters on iMac).
sudo pmset -c sleep 0
sudo pmset -c displaysleep 10
sudo pmset -c disksleep 0

# Make sure Wake on LAN is on so you can Wake-on-Lan if it ever DOES sleep
sudo pmset -c womp 1

echo ""
echo -e "${G}✓${N} Settings applied."
echo ""
echo "Current power management settings:"
echo ""
pmset -g | sed 's/^/    /'
echo ""
echo "=========================================="
echo "  Test it: leave your Mac for 15 minutes  "
echo "  The screen will turn off, but if you    "
echo "  can still hit /health from your phone,  "
echo "  the bridge is alive."
echo "=========================================="
echo ""
echo "  curl http://newt:8001/health"
echo ""
