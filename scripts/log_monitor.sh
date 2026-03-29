#!/bin/bash
# Monitor AITBC logs for critical errors

tail -f /var/log/aitbc/blockchain-node.log | grep --line-buffered -E "(ERROR|CRITICAL|FATAL)" | while read line; do
    echo "$(date): $line" >> /var/log/aitbc/critical_errors.log
    # Send alert (configure your alert system here)
done
