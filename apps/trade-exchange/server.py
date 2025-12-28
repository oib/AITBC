#!/usr/bin/env python3
"""
Simple HTTP server for the AITBC Trade Exchange
"""

import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
import argparse

class CORSHTTPRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Api-Key')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

def run_server(port=3002, directory=None):
    """Run the HTTP server"""
    if directory:
        os.chdir(directory)
    
    server_address = ('', port)
    httpd = HTTPServer(server_address, CORSHTTPRequestHandler)
    
    print(f"""
╔═══════════════════════════════════════╗
║     AITBC Trade Exchange Server       ║
╠═══════════════════════════════════════╣
║  Server running at:                   ║
║  http://localhost:{port}               ║
║                                       ║
║  Buy AITBC with Bitcoin!              ║
║  Press Ctrl+C to stop                  ║
╚═══════════════════════════════════════╝
    """)
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run the AITBC Trade Exchange server')
    parser.add_argument('--port', type=int, default=3002, help='Port to run the server on')
    parser.add_argument('--dir', type=str, default='.', help='Directory to serve from')
    
    args = parser.parse_args()
    run_server(port=args.port, directory=args.dir)
