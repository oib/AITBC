#!/bin/bash
# scripts/move-to-right-folder.sh

echo "🔄 Moving files to correct folders..."

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Auto mode
AUTO_MODE=false
if [[ "$1" == "--auto" ]]; then
    AUTO_MODE=true
fi

# Change to project root
cd "$(dirname "$0")/.."

# Function to move file with confirmation
move_file() {
    local file="$1"
    local target_dir="$2"
    
    if [[ -f "$file" ]]; then
        echo -e "${BLUE}📁 Moving '$file' to '$target_dir/'${NC}"
        
        if [[ "$AUTO_MODE" == "true" ]]; then
            mkdir -p "$target_dir"
            mv "$file" "$target_dir/"
            echo -e "${GREEN}✅ Moved automatically${NC}"
        else
            read -p "Move this file? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                mkdir -p "$target_dir"
                mv "$file" "$target_dir/"
                echo -e "${GREEN}✅ Moved${NC}"
            else
                echo -e "${YELLOW}⏭️  Skipped${NC}"
            fi
        fi
    fi
}

# Function to move directory with confirmation
move_dir() {
    local dir="$1"
    local target_dir="$2"
    
    if [[ -d "$dir" ]]; then
        echo -e "${BLUE}📁 Moving directory '$dir' to '$target_dir/'${NC}"
        
        if [[ "$AUTO_MODE" == "true" ]]; then
            mkdir -p "$target_dir"
            mv "$dir" "$target_dir/"
            echo -e "${GREEN}✅ Moved automatically${NC}"
        else
            read -p "Move this directory? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                mkdir -p "$target_dir"
                mv "$dir" "$target_dir/"
                echo -e "${GREEN}✅ Moved${NC}"
            else
                echo -e "${YELLOW}⏭️  Skipped${NC}"
            fi
        fi
    fi
}

# Move test files
for file in test_*.py test_*.sh run_mc_test.sh; do
    move_file "$file" "dev/tests"
done

# Move development scripts
for file in patch_*.py fix_*.py simple_test.py; do
    move_file "$file" "dev/scripts"
done

# Move multi-chain files
for file in MULTI_*.md; do
    move_file "$file" "dev/multi-chain"
done

# Move environment directories
for dir in node_modules .venv cli_env; do
    move_dir "$dir" "dev/env"
done

# Move cache directories
for dir in .pytest_cache .ruff_cache logs .vscode; do
    move_dir "$dir" "dev/cache"
done

# Move configuration files
for file in .aitbc.yaml .aitbc.yaml.example .env.production .nvmrc .lycheeignore; do
    move_file "$file" "config"
done

echo -e "${GREEN}🎉 File organization complete!${NC}"
