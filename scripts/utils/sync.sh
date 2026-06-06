#!/bin/bash
# AITBC GitHub Sync Script
# Usage: ./sync.sh [push|pull|deploy]

ENVIRONMENT=$(hostname)
ACTION=${1:-"status"}

echo "=== AITBC GitHub Sync ==="
echo "Environment: $ENVIRONMENT"
echo "Action: $ACTION"
echo ""

case $ACTION in
    "push")
        echo "📤 Pushing changes to GitHub..."
        if [ "$ENVIRONMENT" = "aitbc" ]; then
            echo "❌ Don't push from production server!"
            exit 1
        fi
        git add .
        git commit -m "auto: sync from $ENVIRONMENT"
        git push github main
        echo "✅ Pushed to GitHub"
        ;;
        
    "pull")
        echo "📥 Pulling changes from GitHub..."
        git pull github main
        echo "✅ Pulled from GitHub"
        ;;
        
    "deploy")
        echo "🚀 Deploying to AITBC server..."
        if [ "$ENVIRONMENT" != "aitbc" ]; then
            echo "❌ Deploy command only works on AITBC server!"
            exit 1
        fi
        git pull github main
        systemctl restart aitbc-coordinator
        echo "✅ Deployed and service restarted"
        ;;
        
    "status")
        echo "📊 Git Status:"
        git status
        echo ""
        echo "📊 Remote Status:"
        git remote -v
        echo ""
        echo "📊 Recent Commits:"
        git log --oneline -3
        ;;
        
    *)
        echo "Usage: $0 [push|pull|deploy|status]"
        echo "  push    - Push changes to GitHub (localhost only)"
        echo "  pull    - Pull changes from GitHub"
        echo "  deploy  - Pull and restart services (server only)"
        echo "  status  - Show current status"
        exit 1
        ;;
esac
