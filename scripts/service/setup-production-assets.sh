#!/bin/bash

# Download production assets locally
echo "Setting up production assets..."

# Create assets directory
mkdir -p /home/oib/windsurf/aitbc/assets/{css,js,icons}

# Download Tailwind CSS (production build)
echo "Downloading Tailwind CSS..."
curl -L https://unpkg.com/tailwindcss@3.4.0/lib/tailwind.js -o /home/oib/windsurf/aitbc/assets/js/tailwind.js

# Download Axios
echo "Downloading Axios..."
curl -L https://unpkg.com/axios@1.6.2/dist/axios.min.js -o /home/oib/windsurf/aitbc/assets/js/axios.min.js

# Download Lucide icons
echo "Downloading Lucide..."
curl -L https://unpkg.com/lucide@latest/dist/umd/lucide.js -o /home/oib/windsurf/aitbc/assets/js/lucide.js

# Create a custom Tailwind build with only used classes
cat > /home/oib/windsurf/aitbc/assets/tailwind.config.js << 'EOF'
module.exports = {
  content: [
    "./apps/trade-exchange/index.html",
    "./apps/marketplace-ui/index.html"
  ],
  darkMode: 'class',
  theme: {
    extend: {},
  },
  plugins: [],
}
EOF

echo "Assets downloaded to /home/oib/windsurf/aitbc/assets/"
echo "Update your HTML files to use local paths:"
echo "  - /assets/js/tailwind.js"
echo "  - /assets/js/axios.min.js"
echo "  - /assets/js/lucide.js"
