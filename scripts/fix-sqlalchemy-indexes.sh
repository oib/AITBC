#!/bin/bash

# ============================================================================
# Fix SQLAlchemy Index Issues in Domain Models
# ============================================================================

echo "🔧 Fixing SQLAlchemy index issues..."

# Fix global_marketplace.py
echo "Fixing global_marketplace.py..."
sed -i 's/"indexes": \[/# "indexes": [/g' /opt/aitbc/apps/coordinator-api/src/app/domain/global_marketplace.py
sed -i 's/            Index([^)]*),/            # Index(\1)/g' /opt/aitbc/apps/coordinator-api/src/app/domain/global_marketplace.py
sed -i 's/        \]/#        \]/g' /opt/aitbc/apps/coordinator-api/src/app/domain/global_marketplace.py

# Fix pricing_models.py
echo "Fixing pricing_models.py..."
sed -i 's/"indexes": \[/# "indexes": [/g' /opt/aitbc/apps/coordinator-api/src/app/domain/pricing_models.py
sed -i 's/            Index([^)]*),/            # Index(\1)/g' /opt/aitbc/apps/coordinator-api/src/app/domain/pricing_models.py
sed -i 's/        \]/#        \]/g' /opt/aitbc/apps/coordinator-api/src/app/domain/pricing_models.py

# Fix cross_chain_reputation.py
echo "Fixing cross_chain_reputation.py..."
sed -i 's/__table_args__ = (/__table_args__ = {/g' /opt/aitbc/apps/coordinator-api/src/app/domain/cross_chain_reputation.py
sed -i 's/        Index([^)]*),/        # Index(\1)/g' /opt/aitbc/apps/coordinator-api/src/app/domain/cross_chain_reputation.py
sed -i 's/    )/    }/g' /opt/aitbc/apps/coordinator-api/src/app/domain/cross_chain_reputation.py

# Fix bounty.py
echo "Fixing bounty.py..."
sed -i 's/"indexes": \[/# "indexes": [/g' /opt/aitbc/apps/coordinator-api/src/app/domain/bounty.py
sed -i 's/            {"name": "[^"]*", "columns": \[[^]]*\]},/            # {"name": "\1", "columns": [\2]}/g' /opt/aitbc/apps/coordinator-api/src/app/domain/bounty.py
sed -i 's/        \]/#        \]/g' /opt/aitbc/apps/coordinator-api/src/app/domain/bounty.py

echo "✅ SQLAlchemy index fixes completed!"
