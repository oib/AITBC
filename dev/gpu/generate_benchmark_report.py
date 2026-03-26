#!/usr/bin/env python3
"""
GPU Benchmark Report Generator
Generates HTML reports from benchmark results
"""

import json
import argparse
from datetime import datetime
from typing import Dict, List, Any
import matplotlib.pyplot as plt
import seaborn as sns

def load_benchmark_results(filename: str) -> Dict:
    """Load benchmark results from JSON file"""
    with open(filename, 'r') as f:
        return json.load(f)

def generate_html_report(results: Dict, output_file: str):
    """Generate HTML benchmark report"""
    
    # Extract data
    timestamp = datetime.fromtimestamp(results['timestamp'])
    gpu_info = results['gpu_info']
    benchmarks = results['benchmarks']
    
    # Create HTML content
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>GPU Benchmark Report - AITBC</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #007acc;
        }}
        .gpu-info {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        .benchmark-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .benchmark-card {{
            background: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .metric {{
            display: flex;
            justify-content: space-between;
            margin: 10px 0;
        }}
        .metric-label {{
            font-weight: 600;
            color: #333;
        }}
        .metric-value {{
            color: #007acc;
            font-weight: bold;
        }}
        .status-good {{
            color: #28a745;
        }}
        .status-warning {{
            color: #ffc107;
        }}
        .status-bad {{
            color: #dc3545;
        }}
        .chart {{
            margin: 20px 0;
            text-align: center;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #007acc;
            color: white;
        }}
        .performance-summary {{
            background: linear-gradient(135deg, #007acc, #0056b3);
            color: white;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 GPU Benchmark Report</h1>
            <h2>AITBC Performance Analysis</h2>
            <p>Generated: {timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        </div>

        <div class="performance-summary">
            <h3>📊 Performance Summary</h3>
            <div class="metric">
                <span class="metric-label">Overall Performance Score:</span>
                <span class="metric-value">{calculate_performance_score(benchmarks):.1f}/100</span>
            </div>
            <div class="metric">
                <span class="metric-label">GPU Utilization:</span>
                <span class="metric-value">{gpu_info.get('gpu_name', 'Unknown')}</span>
            </div>
            <div class="metric">
                <span class="metric-label">CUDA Version:</span>
                <span class="metric-value">{gpu_info.get('cuda_version', 'N/A')}</span>
            </div>
        </div>

        <div class="gpu-info">
            <h3>🖥️ GPU Information</h3>
            <table>
                <tr><th>Property</th><th>Value</th></tr>
                <tr><td>GPU Name</td><td>{gpu_info.get('gpu_name', 'N/A')}</td></tr>
                <tr><td>Total Memory</td><td>{gpu_info.get('gpu_memory', 0):.1f} GB</td></tr>
                <tr><td>Compute Capability</td><td>{gpu_info.get('gpu_compute_capability', 'N/A')}</td></tr>
                <tr><td>Driver Version</td><td>{gpu_info.get('gpu_driver_version', 'N/A')}</td></tr>
                <tr><td>Temperature</td><td>{gpu_info.get('gpu_temperature', 'N/A')}°C</td></tr>
                <tr><td>Power Usage</td><td>{gpu_info.get('gpu_power_usage', 0):.1f}W</td></tr>
            </table>
        </div>

        <div class="benchmark-grid">
"""

    # Generate benchmark cards
    for name, data in benchmarks.items():
        status = get_performance_status(data['ops_per_sec'])
        html_content += f"""
            <div class="benchmark-card">
                <h4>{format_benchmark_name(name)}</h4>
                <div class="metric">
                    <span class="metric-label">Operations/sec:</span>
                    <span class="metric-value">{data['ops_per_sec']:.2f}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Mean Time:</span>
                    <span class="metric-value">{data['mean']:.4f}s</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Std Dev:</span>
                    <span class="metric-value">{data['std']:.4f}s</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Status:</span>
                    <span class="metric-value {status}">{status.replace('_', ' ').title()}</span>
                </div>
            </div>
"""

    html_content += """
        </div>

        <div class="chart">
            <h3>📈 Performance Comparison</h3>
            <canvas id="performanceChart" width="800" height="400"></canvas>
        </div>

        <div class="chart">
            <h3>🎯 Benchmark Breakdown</h3>
            <canvas id="breakdownChart" width="800" height="400"></canvas>
        </div>

        <script>
            // Chart.js implementation would go here
            // For now, we'll use a simple table representation
        </script>

        <footer style="margin-top: 40px; text-align: center; color: #666;">
            <p>AITBC GPU Benchmark Suite v0.2.0</p>
            <p>Generated automatically by GPU Performance CI</p>
        </footer>
    </div>
</body>
</html>
"""

    # Write HTML file
    with open(output_file, 'w') as f:
        f.write(html_content)

def calculate_performance_score(benchmarks: Dict) -> float:
    """Calculate overall performance score (0-100)"""
    if not benchmarks:
        return 0.0
    
    # Weight different benchmark types
    weights = {
        'pytorch_matmul': 0.2,
        'cupy_matmul': 0.2,
        'gpu_hash_computation': 0.25,
        'pow_simulation': 0.25,
        'neural_forward': 0.1
    }
    
    total_score = 0.0
    total_weight = 0.0
    
    for name, data in benchmarks.items():
        weight = weights.get(name, 0.1)
        # Normalize ops/sec to 0-100 scale (arbitrary baseline)
        normalized_score = min(100, data['ops_per_sec'] / 100)  # 100 ops/sec = 100 points
        total_score += normalized_score * weight
        total_weight += weight
    
    return total_score / total_weight if total_weight > 0 else 0.0

def get_performance_status(ops_per_sec: float) -> str:
    """Get performance status based on operations per second"""
    if ops_per_sec > 100:
        return "status-good"
    elif ops_per_sec > 50:
        return "status-warning"
    else:
        return "status-bad"

def format_benchmark_name(name: str) -> str:
    """Format benchmark name for display"""
    return name.replace('_', ' ').title()

def compare_with_history(current_results: Dict, history_file: str) -> Dict:
    """Compare current results with historical data"""
    try:
        with open(history_file, 'r') as f:
            history = json.load(f)
    except FileNotFoundError:
        return {"status": "no_history"}
    
    # Get most recent historical data
    if not history.get('results'):
        return {"status": "no_history"}
    
    latest_history = history['results'][-1]
    current_benchmarks = current_results['benchmarks']
    history_benchmarks = latest_history['benchmarks']
    
    comparison = {
        "status": "comparison_available",
        "timestamp_diff": current_results['timestamp'] - latest_history['timestamp'],
        "changes": {}
    }
    
    for name, current_data in current_benchmarks.items():
        if name in history_benchmarks:
            history_data = history_benchmarks[name]
            change_percent = ((current_data['ops_per_sec'] - history_data['ops_per_sec']) / 
                             history_data['ops_per_sec']) * 100
            
            comparison['changes'][name] = {
                'current_ops': current_data['ops_per_sec'],
                'history_ops': history_data['ops_per_sec'],
                'change_percent': change_percent,
                'status': 'improved' if change_percent > 5 else 'degraded' if change_percent < -5 else 'stable'
            }
    
    return comparison

def main():
    parser = argparse.ArgumentParser(description='Generate GPU benchmark report')
    parser.add_argument('--input', required=True, help='Input JSON file with benchmark results')
    parser.add_argument('--output', required=True, help='Output HTML file')
    parser.add_argument('--history-file', help='Historical benchmark data file')
    
    args = parser.parse_args()
    
    # Load benchmark results
    results = load_benchmark_results(args.input)
    
    # Generate HTML report
    generate_html_report(results, args.output)
    
    # Compare with history if available
    if args.history_file:
        comparison = compare_with_history(results, args.history_file)
        print(f"Performance comparison: {comparison['status']}")
        
        if comparison['status'] == 'comparison_available':
            for name, change in comparison['changes'].items():
                print(f"{name}: {change['change_percent']:+.2f}% ({change['status']})")
    
    print(f"✅ Benchmark report generated: {args.output}")

if __name__ == "__main__":
    main()
