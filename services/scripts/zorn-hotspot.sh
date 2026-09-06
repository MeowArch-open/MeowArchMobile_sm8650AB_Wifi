#!/bin/bash
# Bring up the WLAN access point, or say clearly why it cannot come up.
#
# This runs as zorn-hotspot.service's ExecStartPre. It has three jobs: make sure
# the radio actually offers AP mode before hostapd tries, get wpa_supplicant off
# the interface, and put the AP's networkd file in place so networkd addresses
# wlp1s0 and runs a DHCP server on it. The matching ExecStopPost removes that
# file again, so stopping the unit hands the interface back to station mode.
set -u
OUT=/root/net.txt
IF=wlp1s0
SRC=/usr/local/lib/zorn/15-zorn-ap.network
DST=/etc/systemd/network/15-zorn-ap.network

say() {
	printf '%s\n' "$*" >> "$OUT"
	printf 'zorn-hotspot: %s\n' "$*" > /dev/kmsg 2>/dev/null || true
}

case "${1:-up}" in
down)
	rm -f "$DST"
	networkctl reload 2>/dev/null || true
	say "=== hotspot down; $IF handed back to station mode ==="
	exit 0
	;;
esac

say ""
say "=== wlan hotspot ==="

# ath12k is a PCI device that loads firmware, so wlp1s0 turns up a few seconds
# after userspace starts. The first version of this checked once and failed, and
# the unit only came up on the systemd restart.
for i in $(seq 1 60); do
	[ -d "/sys/class/net/$IF" ] && break
	sleep 0.5
done
if [ ! -d "/sys/class/net/$IF" ]; then
	say "  $IF never appeared"
	exit 1
fi

# ath12k only advertises AP if the firmware allows it, so ask rather than assume:
# a clear message here beats hostapd failing three lines into nl80211 setup.
PHY=$(basename "$(readlink -f "/sys/class/net/$IF/phy80211")" 2>/dev/null)
modes() {
	iw phy "$PHY" info 2>/dev/null | awk '
		/Supported interface modes:/ { inmodes = 1; next }
		inmodes && /^[[:space:]]*\*/ { print; next }
		inmodes { exit }
	'
}
if ! modes | grep -q '\* AP$'; then
	say "  $PHY does not advertise AP mode; the firmware will not do this"
	modes | sed 's/^/    /' >> "$OUT"
	exit 1
fi
say "  $PHY supports AP mode"

# wpa_supplicant and hostapd cannot both own the interface.
systemctl stop "wpa_supplicant@$IF.service" 2>/dev/null || true

# 15- sorts before the station file 25-wlan.network, and networkd uses the first
# match, so this takes precedence for as long as it is installed.
mkdir -p /etc/systemd/network
cp "$SRC" "$DST" 2>/dev/null || { say "  missing $SRC"; exit 1; }
networkctl reload 2>/dev/null || true

mkdir -p /run/hostapd
say "  ssid=$(sed -n 's/^ssid=//p' /etc/hostapd/zorn.conf) channel=$(sed -n 's/^channel=//p' /etc/hostapd/zorn.conf), clients get 10.43.0.0/24"
say "  (NAT out of the modem comes from zorn-share.sh)"
