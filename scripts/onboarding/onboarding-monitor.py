#!/usr/bin/env python3
"""
onboarding-monitor.py - Monitor agent onboarding success and performance

This script monitors the success rate of agent onboarding, tracks metrics,
and provides insights for improving the onboarding process.
"""

import asyncio
import json
import sys
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
import requests
from collections import defaultdict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OnboardingMonitor:
    """Monitor agent onboarding metrics and performance"""
    
    def __init__(self):
        self.metrics = {
            'total_onboardings': 0,
            'successful_onboardings': 0,
            'failed_onboardings': 0,
            'agent_type_distribution': defaultdict(int),
            'completion_times': [],
            'failure_points': defaultdict(int),
            'daily_stats': defaultdict(dict),
            'error_patterns': defaultdict(int)
        }
        
    def load_existing_data(self):
        """Load existing onboarding data"""
        data_file = Path('/tmp/aitbc-onboarding-metrics.json')
        if data_file.exists():
            try:
                with open(data_file, 'r') as f:
                    data = json.load(f)
                    self.metrics.update(data)
                logger.info(f"Loaded existing metrics: {data.get('total_onboardings', 0)} onboardings")
            except Exception as e:
                logger.error(f"Failed to load existing data: {e}")
    
    def save_metrics(self):
        """Save current metrics to file"""
        try:
            data_file = Path('/tmp/aitbc-onboarding-metrics.json')
            with open(data_file, 'w') as f:
                json.dump(dict(self.metrics), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")
    
    def scan_onboarding_reports(self):
        """Scan for onboarding report files"""
        reports = []
        report_dir = Path('/tmp')
        
        for report_file in report_dir.glob('aitbc-onboarding-*.json'):
            try:
                with open(report_file, 'r') as f:
                    report = json.load(f)
                    reports.append(report)
            except Exception as e:
                logger.error(f"Failed to read report {report_file}: {e}")
        
        return reports
    
    def analyze_reports(self, reports):
        """Analyze onboarding reports and update metrics"""
        for report in reports:
            try:
                onboarding = report.get('onboarding', {})
                
                # Update basic metrics
                self.metrics['total_onboardings'] += 1
                
                if onboarding.get('status') == 'success':
                    self.metrics['successful_onboardings'] += 1
                    
                    # Track completion time
                    duration = onboarding.get('duration_minutes', 0)
                    self.metrics['completion_times'].append(duration)
                    
                    # Track agent type distribution
                    agent_type = self.extract_agent_type(report)
                    if agent_type:
                        self.metrics['agent_type_distribution'][agent_type] += 1
                    
                    # Track daily stats
                    date = datetime.fromisoformat(onboarding['timestamp']).date()
                    self.metrics['daily_stats'][date]['successful'] = \
                        self.metrics['daily_stats'][date].get('successful', 0) + 1
                    self.metrics['daily_stats'][date]['total'] = \
                        self.metrics['daily_stats'][date].get('total', 0) + 1
                    
                else:
                    self.metrics['failed_onboardings'] += 1
                    
                    # Track failure points
                    steps_completed = onboarding.get('steps_completed', [])
                    expected_steps = ['environment_check', 'capability_assessment', 
                                   'agent_type_recommendation', 'agent_creation', 
                                   'network_registration', 'swarm_integration', 
                                   'participation_started', 'report_generated']
                    
                    for step in expected_steps:
                        if step not in steps_completed:
                            self.metrics['failure_points'][step] += 1
                    
                    # Track errors
                    for error in onboarding.get('errors', []):
                        self.metrics['error_patterns'][error] += 1
                    
                    # Track daily failures
                    date = datetime.fromisoformat(onboarding['timestamp']).date()
                    self.metrics['daily_stats'][date]['failed'] = \
                        self.metrics['daily_stats'][date].get('failed', 0) + 1
                    self.metrics['daily_stats'][date]['total'] = \
                        self.metrics['daily_stats'][date].get('total', 0) + 1
                
            except Exception as e:
                logger.error(f"Failed to analyze report: {e}")
    
    def extract_agent_type(self, report):
        """Extract agent type from report"""
        try:
            agent_capabilities = report.get('agent_capabilities', {})
            compute_type = agent_capabilities.get('specialization')
            
            # Map specialization to agent type
            type_mapping = {
                'inference': 'compute_provider',
                'training': 'compute_provider',
                'processing': 'compute_consumer',
                'coordination': 'swarm_coordinator',
                'development': 'platform_builder'
            }
            
            return type_mapping.get(compute_type, 'unknown')
        except:
            return 'unknown'
    
    def calculate_metrics(self):
        """Calculate derived metrics"""
        metrics = {}
        
        # Success rate
        if self.metrics['total_onboardings'] > 0:
            metrics['success_rate'] = (self.metrics['successful_onboardings'] / 
                                       self.metrics['total_onboardings']) * 100
        else:
            metrics['success_rate'] = 0
        
        # Average completion time
        if self.metrics['completion_times']:
            metrics['avg_completion_time'] = sum(self.metrics['completion_times']) / len(self.metrics['completion_times'])
        else:
            metrics['avg_completion_time'] = 0
        
        # Most common failure point
        if self.metrics['failure_points']:
            metrics['most_common_failure'] = max(self.metrics['failure_points'], 
                                                key=self.metrics['failure_points'].get)
        else:
            metrics['most_common_failure'] = 'none'
        
        # Most common error
        if self.metrics['error_patterns']:
            metrics['most_common_error'] = max(self.metrics['error_patterns'], 
                                              key=self.metrics['error_patterns'].get)
        else:
            metrics['most_common_error'] = 'none'
        
        # Agent type distribution percentages
        total_agents = sum(self.metrics['agent_type_distribution'].values())
        if total_agents > 0:
            metrics['agent_type_percentages'] = {
                agent_type: (count / total_agents) * 100
                for agent_type, count in self.metrics['agent_type_distribution'].items()
            }
        else:
            metrics['agent_type_percentages'] = {}
        
        return metrics
    
    def generate_report(self):
        """Generate comprehensive onboarding report"""
        metrics = self.calculate_metrics()
        
        report = {
            'timestamp': datetime.utcnow().isoformat(),
            'summary': {
                'total_onboardings': self.metrics['total_onboardings'],
                'successful_onboardings': self.metrics['successful_onboardings'],
                'failed_onboardings': self.metrics['failed_onboardings'],
                'success_rate': metrics['success_rate'],
                'avg_completion_time_minutes': metrics['avg_completion_time']
            },
            'agent_type_distribution': dict(self.metrics['agent_type_distribution']),
            'agent_type_percentages': metrics['agent_type_percentages'],
            'failure_analysis': {
                'most_common_failure_point': metrics['most_common_failure'],
                'failure_points': dict(self.metrics['failure_points']),
                'most_common_error': metrics['most_common_error'],
                'error_patterns': dict(self.metrics['error_patterns'])
            },
            'daily_stats': dict(self.metrics['daily_stats']),
            'recommendations': self.generate_recommendations(metrics)
        }
        
        return report
    
    def generate_recommendations(self, metrics):
        """Generate improvement recommendations"""
        recommendations = []
        
        # Success rate recommendations
        if metrics['success_rate'] < 80:
            recommendations.append({
                'priority': 'high',
                'issue': 'Low success rate',
                'recommendation': 'Review onboarding process for common failure points',
                'action': 'Focus on fixing: ' + metrics['most_common_failure']
            })
        elif metrics['success_rate'] < 95:
            recommendations.append({
                'priority': 'medium',
                'issue': 'Moderate success rate',
                'recommendation': 'Optimize onboarding for better success rate',
                'action': 'Monitor and improve failure points'
            })
        
        # Completion time recommendations
        if metrics['avg_completion_time'] > 20:
            recommendations.append({
                'priority': 'medium',
                'issue': 'Slow onboarding process',
                'recommendation': 'Optimize onboarding steps for faster completion',
                'action': 'Reduce time in capability assessment and registration'
            })
        
        # Agent type distribution recommendations
        if 'compute_provider' not in metrics['agent_type_percentages'] or \
           metrics['agent_type_percentages'].get('compute_provider', 0) < 20:
            recommendations.append({
                'priority': 'low',
                'issue': 'Low compute provider adoption',
                'recommendation': 'Improve compute provider onboarding experience',
                'action': 'Simplify GPU setup and resource offering process'
            })
        
        # Error pattern recommendations
        if metrics['most_common_error'] != 'none':
            recommendations.append({
                'priority': 'high',
                'issue': f'Recurring error: {metrics["most_common_error"]}',
                'recommendation': 'Fix common error pattern',
                'action': 'Add better error handling and user guidance'
            })
        
        return recommendations
    
    def print_dashboard(self):
        """Print a dashboard view of current metrics"""
        metrics = self.calculate_metrics()
        
        print("🤖 AITBC Agent Onboarding Dashboard")
        print("=" * 50)
        print()
        
        # Summary stats
        print("📊 SUMMARY:")
        print(f"   Total Onboardings: {self.metrics['total_onboardings']}")
        print(f"   Success Rate: {metrics['success_rate']:.1f}%")
        print(f"   Avg Completion Time: {metrics['avg_completion_time']:.1f} minutes")
        print()
        
        # Agent type distribution
        print("🎯 AGENT TYPE DISTRIBUTION:")
        for agent_type, count in self.metrics['agent_type_distribution'].items():
            percentage = metrics['agent_type_percentages'].get(agent_type, 0)
            print(f"   {agent_type}: {count} ({percentage:.1f}%)")
        print()
        
        # Recent performance
        print("📈 RECENT PERFORMANCE (Last 7 Days):")
        recent_date = datetime.now().date() - timedelta(days=7)
        recent_successful = 0
        recent_total = 0
        
        for date, stats in self.metrics['daily_stats'].items():
            if date >= recent_date:
                recent_total += stats.get('total', 0)
                recent_successful += stats.get('successful', 0)
        
        if recent_total > 0:
            recent_success_rate = (recent_successful / recent_total) * 100
            print(f"   Success Rate: {recent_success_rate:.1f}% ({recent_successful}/{recent_total})")
        else:
            print("   No recent data available")
        print()
        
        # Issues
        if metrics['most_common_failure'] != 'none':
            print("⚠️  COMMON ISSUES:")
            print(f"   Most Common Failure: {metrics['most_common_failure']}")
            if metrics['most_common_error'] != 'none':
                print(f"   Most Common Error: {metrics['most_common_error']}")
            print()
        
        # Recommendations
        recommendations = self.generate_recommendations(metrics)
        if recommendations:
            print("💡 RECOMMENDATIONS:")
            for rec in recommendations[:3]:  # Show top 3
                priority_emoji = "🔴" if rec['priority'] == 'high' else "🟡" if rec['priority'] == 'medium' else "🟢"
                print(f"   {priority_emoji} {rec['issue']}")
                print(f"      {rec['recommendation']}")
            print()
    
    def export_csv(self):
        """Export metrics to CSV format"""
        import csv
        from io import StringIO
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Date', 'Total', 'Successful', 'Failed', 'Success Rate', 'Avg Time'])
        
        # Write daily stats
        for date, stats in sorted(self.metrics['daily_stats'].items()):
            total = stats.get('total', 0)
            successful = stats.get('successful', 0)
            failed = stats.get('failed', 0)
            success_rate = (successful / total * 100) if total > 0 else 0
            
            writer.writerow([
                date,
                total,
                successful,
                failed,
                f"{success_rate:.1f}%",
                "N/A"  # Would need to calculate daily average
            ])
        
        csv_content = output.getvalue()
        
        # Save to file
        csv_file = Path('/tmp/aitbc-onboarding-metrics.csv')
        with open(csv_file, 'w') as f:
            f.write(csv_content)
        
        print(f"📊 Metrics exported to: {csv_file}")
    
    def run_monitoring(self):
        """Run continuous monitoring"""
        print("🔍 Starting onboarding monitoring...")
        print("Press Ctrl+C to stop monitoring")
        print()
        
        try:
            while True:
                # Load existing data
                self.load_existing_data()
                
                # Scan for new reports
                reports = self.scan_onboarding_reports()
                if reports:
                    print(f"📊 Processing {len(reports)} new onboarding reports...")
                    self.analyze_reports(reports)
                    self.save_metrics()
                    
                    # Print updated dashboard
                    self.print_dashboard()
                
                # Wait before next scan
                time.sleep(300)  # 5 minutes
                
        except KeyboardInterrupt:
            print("\n👋 Monitoring stopped by user")
        except Exception as e:
            logger.error(f"Monitoring error: {e}")

def main():
    """Main entry point"""
    monitor = OnboardingMonitor()
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == 'dashboard':
            monitor.load_existing_data()
            monitor.print_dashboard()
        elif command == 'export':
            monitor.load_existing_data()
            monitor.export_csv()
        elif command == 'report':
            monitor.load_existing_data()
            report = monitor.generate_report()
            print(json.dumps(report, indent=2))
        elif command == 'monitor':
            monitor.run_monitoring()
        else:
            print("Usage: python3 onboarding-monitor.py [dashboard|export|report|monitor]")
            sys.exit(1)
    else:
        # Default: show dashboard
        monitor.load_existing_data()
        monitor.print_dashboard()

if __name__ == "__main__":
    main()
