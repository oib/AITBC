#!/usr/bin/env python3
"""
Build script for AITBC Trade Exchange
Combines CSS and HTML for production deployment
"""

import os
import shutil

def build_html():
    """Build production HTML with embedded CSS"""
    print("🔨 Building AITBC Exchange for production...")
    
    # Read CSS file
    css_path = "styles.css"
    html_path = "index.html"
    output_path = "index.html"
    
    # Backup original
    if os.path.exists(html_path):
        shutil.copy(html_path, "index.dev.html")
        print("✓ Backed up original index.html to index.dev.html")
    
    # Read the template
    with open("index.template.html", "r") as f:
        template = f.read()
    
    # Read CSS
    with open(css_path, "r") as f:
        css_content = f.read()
    
    # Replace placeholder with CSS
    html_content = template.replace("<!-- CSS_PLACEHOLDER -->", f"<style>\n{css_content}\n    </style>")
    
    # Write production HTML
    with open(output_path, "w") as f:
        f.write(html_content)
    
    print(f"✓ Built production HTML: {output_path}")
    print("✓ CSS is now embedded in HTML")

def create_template():
    """Create a template file for future use"""
    template = """<!DOCTYPE html>
<html lang="en" class="h-full">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AITBC Trade Exchange - Buy & Sell AITBC</title>
    <script src="https://unpkg.com/lucide@latest"></script>
    <!-- CSS_PLACEHOLDER -->
</head>
<body>
    <!-- Body content will be added here -->
</body>
</html>"""
    
    with open("index.template.html", "w") as f:
        f.write(template)
    
    print("✓ Created template file: index.template.html")

if __name__ == "__main__":
    if not os.path.exists("index.template.html"):
        create_template()
    
    build_html()
