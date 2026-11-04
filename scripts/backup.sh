#!/bin/sh
# 账号数据自动备份：每小时一份，保留最近 24 份
DATA=/app/data
BAK=/app/data/backups
mkdir -p "$BAK"
while true; do
  if [ -f "$DATA/accounts.json" ] && [ "$(wc -c < "$DATA/accounts.json")" -gt 10 ]; then
    ts=$(date +%Y%m%d_%H%M)
    cp "$DATA/accounts.json" "$BAK/accounts_$ts.json" 2>/dev/null
    ls -t "$BAK"/accounts_*.json 2>/dev/null | tail -n +25 | xargs -r rm -f
  fi
  sleep 3600
done
