#!/bin/bash
# Copies the project into a Proxmox LXC container over SSH and restarts the service.
# Usage: PVE=root@192.168.1.10 CT=103 DEST=/opt/ev-charger-bot scripts/deploy.sh [--no-restart]
# .env, config.toml and data/ on the target are never overwritten.
set -euo pipefail
PVE=${PVE:-root@192.168.1.10}
CT=${CT:-103}
DEST=${DEST:-/opt/ev-charger-bot}
SERVICE=${SERVICE:-ev-charger-bot}
cd "$(dirname "$0")/.."
tar --exclude=.git --exclude=venv --exclude=data --exclude=.env --exclude='__pycache__' -czf /tmp/evcb-deploy.tgz .
scp -q /tmp/evcb-deploy.tgz "$PVE:/tmp/evcb-deploy.tgz"
ssh "$PVE" "pct push $CT /tmp/evcb-deploy.tgz /tmp/evcb-deploy.tgz >/dev/null && rm -f /tmp/evcb-deploy.tgz && pct exec $CT -- bash -c '
  set -e
  mkdir -p $DEST
  if [ -f $DEST/config.toml ]; then tar -xzf /tmp/evcb-deploy.tgz -C $DEST --exclude=./config.toml; else tar -xzf /tmp/evcb-deploy.tgz -C $DEST; fi
  rm -f /tmp/evcb-deploy.tgz
  chown -R evsarj:evsarj $DEST
  sed -e \"s|/opt/ev-charger-bot|$DEST|g\" $DEST/ev-charger-bot.service > /etc/systemd/system/$SERVICE.service
  systemctl daemon-reload
  runuser -u evsarj -- $DEST/venv/bin/pip install -q -r $DEST/requirements.txt
  if [ \"${1:-}\" != \"--no-restart\" ]; then systemctl restart $SERVICE; sleep 3; systemctl --no-pager --lines=3 status $SERVICE; fi
'"
rm -f /tmp/evcb-deploy.tgz
