#!/bin/bash

echo "🚀 Deploying AITBC for Production..."

# 1. Setup production assets
echo "📦 Setting up production assets..."
bash setup-production-assets.sh

# 2. Copy assets to server
echo "📋 Copying assets to server..."
scp -r assets/ aitbc:/var/www/html/

# 3. Update Nginx configuration
echo "⚙️ Updating Nginx configuration..."
ssh aitbc "cat >> /etc/nginx/sites-available/aitbc.conf << 'EOF'

# Serve production assets
location /assets/ {
    alias /var/www/html/assets/;
    expires 1y;
    add_header Cache-Control \"public, immutable\";
    add_header X-Content-Type-Options nosniff;
    
    # Gzip compression
    gzip on;
    gzip_types text/css application/javascript image/svg+xml;
}

# Security headers
add_header Referrer-Policy \"strict-origin-when-cross-origin\" always;
add_header X-Frame-Options \"SAMEORIGIN\" always;
add_header X-Content-Type-Options \"nosniff\" always;
EOF"

# 4. Reload Nginx
echo "🔄 Reloading Nginx..."
ssh aitbc "nginx -t && systemctl reload nginx"

# 5. Update Exchange page to use production assets
echo "🔄 Updating Exchange page..."
scp apps/trade-exchange/index.prod.html aitbc:/root/aitbc/apps/trade-exchange/index.html

# 6. Update Marketplace page
echo "🔄 Updating Marketplace page..."
sed -i 's|https://cdn.tailwindcss.com|/assets/js/tailwind.js|g' apps/marketplace-ui/index.html
sed -i 's|https://unpkg.com/axios/dist/axios.min.js|/assets/js/axios.min.js|g' apps/marketplace-ui/index.html
sed -i 's|https://unpkg.com/lucide@latest|/assets/js/lucide.js|g' apps/marketplace-ui/index.html
scp apps/marketplace-ui/index.html aitbc:/root/aitbc/apps/marketplace-ui/

echo "✅ Production deployment complete!"
echo ""
echo "📝 Next steps:"
echo "1. Restart services: ssh aitbc 'systemctl restart aitbc-exchange aitbc-marketplace-ui'"
echo "2. Clear browser cache"
echo "3. Test all pages"
