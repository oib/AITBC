"""
Ecosystem Analytics Service for AITBC

Tracks and analyzes ecosystem metrics including:
- Hackathon participation and outcomes
- Grant program effectiveness
- Extension adoption and usage
- Developer engagement
- Network effects and cross-chain activity
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from decimal import Decimal
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

# Configuration - in production, this would come from environment variables or config file
class Settings:
    DATABASE_URL = "postgresql://user:pass@localhost/aitbc"

settings = Settings()


@dataclass
class EcosystemMetric:
    """Base class for ecosystem metrics"""
    timestamp: datetime
    metric_name: str
    value: float
    unit: str
    dimensions: Dict[str, Any]
    source: str


@dataclass
class HackathonMetric:
    """Hackathon-specific metrics"""
    event_id: str
    event_name: str
    start_date: datetime
    end_date: datetime
    participants: int
    submissions: int
    winners: int
    projects_deployed: int
    github_stars: int
    community_engagement: float
    technical_score: float
    innovation_score: float


@dataclass
class GrantMetric:
    """Grant program metrics"""
    grant_id: str
    project_name: str
    amount_awarded: Decimal
    amount_disbursed: Decimal
    milestones_completed: int
    total_milestones: int
    users_acquired: int
    github_contributors: int
    code_commits: int
    documentation_score: float
    community_score: float


@dataclass
class ExtensionMetric:
    """Extension/connector metrics"""
    extension_id: str
    extension_name: str
    downloads: int
    active_installations: int
    api_calls: int
    error_rate: float
    avg_response_time: float
    user_satisfaction: float
    integration_count: int
    revenue_generated: Decimal


class EcosystemAnalyticsService:
    """Main analytics service for ecosystem metrics"""
    
    def __init__(self):
        self.engine = create_engine(settings.DATABASE_URL)
        self.Session = sessionmaker(bind=self.engine)
        self.logger = __import__('logging').getLogger(__name__)
        
    async def collect_hackathon_metrics(self, event_id: str) -> HackathonMetric:
        """Collect metrics for a specific hackathon"""
        with self.Session() as db:
            # Get event details
            event = self._get_hackathon_event(db, event_id)
            if not event:
                raise ValueError(f"Hackathon {event_id} not found")
            
            # Collect participant metrics
            participants = await self._count_participants(event_id)
            submissions = await self._count_submissions(event_id)
            
            # Get project metrics
            projects = await self._get_hackathon_projects(event_id)
            projects_deployed = sum(1 for p in projects if p.get('deployed', False))
            
            # Calculate engagement scores
            community_engagement = await self._calculate_community_engagement(event_id)
            technical_scores = [p.get('technical_score', 0) for p in projects]
            innovation_scores = [p.get('innovation_score', 0) for p in projects]
            
            # Get GitHub metrics
            github_stars = sum(p.get('github_stars', 0) for p in projects)
            
            metric = HackathonMetric(
                event_id=event_id,
                event_name=event['name'],
                start_date=event['start_date'],
                end_date=event['end_date'],
                participants=participants,
                submissions=submissions,
                winners=len([p for p in projects if p.get('winner', False)]),
                projects_deployed=projects_deployed,
                github_stars=github_stars,
                community_engagement=community_engagement,
                technical_score=sum(technical_scores) / len(technical_scores) if technical_scores else 0,
                innovation_score=sum(innovation_scores) / len(innovation_scores) if innovation_scores else 0
            )
            
            # Store metrics
            await self._store_metric(metric)
            
            return metric
    
    async def collect_grant_metrics(self, grant_id: str) -> GrantMetric:
        """Collect metrics for a specific grant"""
        with self.Session() as db:
            # Get grant details
            grant = self._get_grant_details(db, grant_id)
            if not grant:
                raise ValueError(f"Grant {grant_id} not found")
            
            # Get project metrics
            project = await self._get_grant_project(grant_id)
            
            # Calculate completion metrics
            milestones_completed = await self._count_completed_milestones(grant_id)
            total_milestones = grant.get('total_milestones', 1)
            
            # Get adoption metrics
            users_acquired = await self._count_project_users(grant_id)
            github_contributors = await self._count_github_contributors(project.get('repo_url'))
            code_commits = await self._count_code_commits(project.get('repo_url'))
            
            # Calculate quality scores
            documentation_score = await self._evaluate_documentation(project.get('docs_url'))
            community_score = await self._evaluate_community_health(project.get('repo_url'))
            
            metric = GrantMetric(
                grant_id=grant_id,
                project_name=grant['project_name'],
                amount_awarded=Decimal(str(grant.get('amount_awarded', 0))),
                amount_disbursed=Decimal(str(grant.get('amount_disbursed', 0))),
                milestones_completed=milestones_completed,
                total_milestones=total_milestones,
                users_acquired=users_acquired,
                github_contributors=github_contributors,
                code_commits=code_commits,
                documentation_score=documentation_score,
                community_score=community_score
            )
            
            # Store metrics
            await self._store_metric(metric)
            
            return metric
    
    async def collect_extension_metrics(self, extension_id: str) -> ExtensionMetric:
        """Collect metrics for a specific extension"""
        with self.Session() as db:
            # Get extension details
            extension = self._get_extension_details(db, extension_id)
            if not extension:
                raise ValueError(f"Extension {extension_id} not found")
            
            # Get usage metrics
            downloads = await self._count_downloads(extension_id)
            active_installations = await self._count_active_installations(extension_id)
            
            # Get performance metrics
            api_calls = await self._count_api_calls(extension_id, days=30)
            error_rate = await self._calculate_error_rate(extension_id, days=30)
            avg_response_time = await self._calculate_avg_response_time(extension_id, days=30)
            
            # Get quality metrics
            user_satisfaction = await self._calculate_user_satisfaction(extension_id)
            integration_count = await self._count_integrations(extension_id)
            
            # Get business metrics
            revenue_generated = await self._calculate_revenue(extension_id, days=30)
            
            metric = ExtensionMetric(
                extension_id=extension_id,
                extension_name=extension['name'],
                downloads=downloads,
                active_installations=active_installations,
                api_calls=api_calls,
                error_rate=error_rate,
                avg_response_time=avg_response_time,
                user_satisfaction=user_satisfaction,
                integration_count=integration_count,
                revenue_generated=Decimal(str(revenue_generated))
            )
            
            # Store metrics
            await self._store_metric(metric)
            
            return metric
    
    async def generate_ecosystem_dashboard(self, days: int = 30) -> Dict[str, Any]:
        """Generate comprehensive ecosystem dashboard"""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        dashboard = {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": days
            },
            "summary": await self._generate_summary_metrics(start_date, end_date),
            "hackathons": await self._generate_hackathon_section(start_date, end_date),
            "grants": await self._generate_grant_section(start_date, end_date),
            "extensions": await self._generate_extension_section(start_date, end_date),
            "network_effects": await self._generate_network_effects(start_date, end_date)
        }
        
        return dashboard
    
    async def generate_hackathon_report(self, event_id: str) -> Dict[str, Any]:
        """Generate detailed hackathon report"""
        metric = await self.collect_hackathon_metrics(event_id)
        
        # Generate visualizations
        figures = {}
        
        # Participation funnel
        fig_funnel = go.Figure(go.Funnel(
            y=["Registrations", "Active Participants", "Submissions", "Deployed Projects", "Winners"],
            x=[
                metric.participants * 1.5,  # Estimated registrations
                metric.participants,
                metric.submissions,
                metric.projects_deployed,
                metric.winners
            ]
        ))
        fig_funnel.update_layout(title="Hackathon Participation Funnel")
        figures['funnel'] = fig_funnel.to_json()
        
        # Score distribution
        fig_scores = go.Figure()
        fig_scores.add_trace(go.Scatter(
            x=list(range(metric.submissions)),
            y=[{'technical_score': 75, 'innovation_score': 85}] * metric.submissions,  # Sample data
            mode='markers',
            name='Projects'
        ))
        fig_scores.update_layout(title="Project Scores Distribution")
        figures['scores'] = fig_scores.to_json()
        
        # Project categories
        categories = ['DeFi', 'Enterprise', 'Developer Tools', 'Analytics', 'Other']
        counts = [15, 20, 10, 8, 12]  # Sample data
        
        fig_categories = px.pie(
            values=counts,
            names=categories,
            title="Project Categories"
        )
        figures['categories'] = fig_categories.to_json()
        
        report = {
            "event": asdict(metric),
            "figures": figures,
            "insights": await self._generate_hackathon_insights(metric),
            "recommendations": await self._generate_hackathon_recommendations(metric)
        }
        
        return report
    
    async def generate_grant_impact_report(self, grant_id: str) -> Dict[str, Any]:
        """Generate grant impact report"""
        metric = await self.collect_grant_metrics(grant_id)
        
        # Generate ROI analysis
        roi_analysis = await self._calculate_grant_roi(metric)
        
        # Generate adoption curve
        adoption_data = await self._get_adoption_curve(grant_id)
        
        fig_adoption = px.line(
            x=[d['date'] for d in adoption_data],
            y=[d['users'] for d in adoption_data],
            title="User Adoption Over Time"
        )
        
        report = {
            "grant": asdict(metric),
            "roi_analysis": roi_analysis,
            "adoption_chart": fig_adoption.to_json(),
            "milestone_progress": {
                "completed": metric.milestones_completed,
                "total": metric.total_milestones,
                "percentage": (metric.milestones_completed / metric.total_milestones * 100) if metric.total_milestones > 0 else 0
            },
            "quality_metrics": {
                "documentation": metric.documentation_score,
                "community": metric.community_score,
                "overall": (metric.documentation_score + metric.community_score) / 2
            }
        }
        
        return report
    
    async def export_metrics(self, metric_type: str, format: str = "csv") -> bytes:
        """Export metrics in specified format"""
        # Get metrics data
        if metric_type == "hackathons":
            data = await self._get_all_hackathon_metrics()
        elif metric_type == "grants":
            data = await self._get_all_grant_metrics()
        elif metric_type == "extensions":
            data = await self._get_all_extension_metrics()
        else:
            raise ValueError(f"Unknown metric type: {metric_type}")
        
        # Convert to DataFrame
        df = pd.DataFrame([asdict(m) for m in data])
        
        # Export in requested format
        if format == "csv":
            return df.to_csv(index=False).encode('utf-8')
        elif format == "json":
            return df.to_json(orient='records', indent=2).encode('utf-8')
        elif format == "excel":
            return df.to_excel(index=False).encode('utf-8')
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    # Private helper methods
    
    async def _store_metric(self, metric: Any):
        """Store metric in database"""
        # Implementation would store in metrics table
        pass
    
    async def _count_participants(self, event_id: str) -> int:
        """Count hackathon participants"""
        # Implementation would query participant data
        return 150  # Sample
    
    async def _count_submissions(self, event_id: str) -> int:
        """Count hackathon submissions"""
        return 45  # Sample
    
    async def _get_hackathon_projects(self, event_id: str) -> List[Dict]:
        """Get all projects from hackathon"""
        # Implementation would query project data
        return []  # Sample
    
    async def _calculate_community_engagement(self, event_id: str) -> float:
        """Calculate community engagement score"""
        return 85.5  # Sample
    
    async def _count_completed_milestones(self, grant_id: str) -> int:
        """Count completed grant milestones"""
        return 3  # Sample
    
    async def _count_project_users(self, grant_id: str) -> int:
        """Count users of grant project"""
        return 500  # Sample
    
    async def _count_github_contributors(self, repo_url: str) -> int:
        """Count GitHub contributors"""
        return 12  # Sample
    
    async def _count_code_commits(self, repo_url: str) -> int:
        """Count code commits"""
        return 234  # Sample
    
    async def _evaluate_documentation(self, docs_url: str) -> float:
        """Evaluate documentation quality"""
        return 90.0  # Sample
    
    async def _evaluate_community_health(self, repo_url: str) -> float:
        """Evaluate community health"""
        return 75.5  # Sample
    
    async def _count_downloads(self, extension_id: str) -> int:
        """Count extension downloads"""
        return 1250  # Sample
    
    async def _count_active_installations(self, extension_id: str) -> int:
        """Count active installations"""
        return 350  # Sample
    
    async def _count_api_calls(self, extension_id: str, days: int) -> int:
        """Count API calls to extension"""
        return 15000  # Sample
    
    async def _calculate_error_rate(self, extension_id: str, days: int) -> float:
        """Calculate error rate"""
        return 0.02  # Sample
    
    async def _calculate_avg_response_time(self, extension_id: str, days: int) -> float:
        """Calculate average response time"""
        return 125.5  # Sample
    
    async def _calculate_user_satisfaction(self, extension_id: str) -> float:
        """Calculate user satisfaction score"""
        return 4.5  # Sample
    
    async def _count_integrations(self, extension_id: str) -> int:
        """Count integrations using extension"""
        return 25  # Sample
    
    async def _calculate_revenue(self, extension_id: str, days: int) -> float:
        """Calculate revenue generated"""
        return 5000.0  # Sample
    
    async def _generate_summary_metrics(self, start_date: datetime, end_date: datetime) -> Dict:
        """Generate summary metrics for dashboard"""
        return {
            "total_hackathons": 4,
            "total_participants": 600,
            "total_grants_awarded": 12,
            "total_grant_amount": 500000,
            "active_extensions": 25,
            "total_downloads": 50000,
            "github_stars": 2500,
            "community_members": 1500
        }
    
    async def _generate_hackathon_section(self, start_date: datetime, end_date: datetime) -> Dict:
        """Generate hackathon section of dashboard"""
        return {
            "upcoming": [],
            "recent": [],
            "top_projects": [],
            "participation_trend": []
        }
    
    async def _generate_grant_section(self, start_date: datetime, end_date: datetime) -> Dict:
        """Generate grant section of dashboard"""
        return {
            "active_grants": 8,
            "completed_grants": 4,
            "total_disbursed": 350000,
            "roi_average": 2.5,
            "success_rate": 0.85
        }
    
    async def _generate_extension_section(self, start_date: datetime, end_date: datetime) -> Dict:
        """Generate extension section of dashboard"""
        return {
            "total_extensions": 25,
            "new_extensions": 3,
            "most_popular": [],
            "growth_rate": 0.15
        }
    
    async def _generate_network_effects(self, start_date: datetime, end_date: datetime) -> Dict:
        """Generate network effects analysis"""
        return {
            "cross_chain_volume": 1000000,
            "interoperability_score": 85.5,
            "network_value": 25000000,
            "metcalfe_coefficient": 1.2
        }
    
    async def _generate_hackathon_insights(self, metric: HackathonMetric) -> List[str]:
        """Generate insights from hackathon metrics"""
        insights = []
        
        if metric.projects_deployed / metric.submissions > 0.5:
            insights.append("High deployment rate indicates strong technical execution")
        
        if metric.community_engagement > 80:
            insights.append("Excellent community engagement and participation")
        
        if metric.github_stars > 100:
            insights.append("Strong GitHub community interest")
        
        return insights
    
    async def _generate_hackathon_recommendations(self, metric: HackathonMetric) -> List[str]:
        """Generate recommendations for improvement"""
        recommendations = []
        
        if metric.projects_deployed / metric.submissions < 0.3:
            recommendations.append("Provide more deployment support and infrastructure")
        
        if metric.technical_score < 70:
            recommendations.append("Offer technical workshops and mentorship")
        
        if metric.innovation_score < 70:
            recommendations.append("Encourage more innovative and ambitious projects")
        
        return recommendations
    
    async def _calculate_grant_roi(self, metric: GrantMetric) -> Dict:
        """Calculate grant ROI"""
        if metric.amount_disbursed == 0:
            return {"roi": 0, "payback_period": None}
        
        # Simplified ROI calculation
        estimated_value = metric.users_acquired * 100  # $100 per user
        roi = (estimated_value - float(metric.amount_disbursed)) / float(metric.amount_disbursed)
        
        return {
            "roi": roi,
            "payback_period": "12 months" if roi > 0 else None,
            "value_created": estimated_value
        }
    
    async def _get_adoption_curve(self, grant_id: str) -> List[Dict]:
        """Get user adoption over time"""
        # Sample data
        return [
            {"date": "2024-01-01", "users": 50},
            {"date": "2024-02-01", "users": 120},
            {"date": "2024-03-01", "users": 200},
            {"date": "2024-04-01", "users": 350},
            {"date": "2024-05-01", "users": 500}
        ]
    
    def _get_hackathon_event(self, db, event_id: str) -> Optional[Dict]:
        """Get hackathon event details"""
        # Implementation would query database
        return {
            "name": "DeFi Innovation Hackathon",
            "start_date": datetime(2024, 1, 15),
            "end_date": datetime(2024, 1, 22)
        }
    
    def _get_grant_details(self, db, grant_id: str) -> Optional[Dict]:
        """Get grant details"""
        # Implementation would query database
        return {
            "project_name": "Advanced Analytics Platform",
            "amount_awarded": 50000,
            "amount_disbursed": 25000,
            "total_milestones": 4
        }
    
    def _get_extension_details(self, db, extension_id: str) -> Optional[Dict]:
        """Get extension details"""
        # Implementation would query database
        return {
            "name": "SAP ERP Connector"
        }
    
    async def _get_grant_project(self, grant_id: str) -> Dict:
        """Get grant project details"""
        return {
            "repo_url": "https://github.com/example/project",
            "docs_url": "https://docs.example.com"
        }
    
    async def _get_all_hackathon_metrics(self) -> List[HackathonMetric]:
        """Get all hackathon metrics"""
        # Implementation would query database
        return []
    
    async def _get_all_grant_metrics(self) -> List[GrantMetric]:
        """Get all grant metrics"""
        # Implementation would query database
        return []
    
    async def _get_all_extension_metrics(self) -> List[ExtensionMetric]:
        """Get all extension metrics"""
        # Implementation would query database
        return []


# CLI interface for analytics service
async def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="AITBC Ecosystem Analytics")
    parser.add_argument("--dashboard", action="store_true", help="Generate ecosystem dashboard")
    parser.add_argument("--hackathon", help="Generate hackathon report for event ID")
    parser.add_argument("--grant", help="Generate grant impact report for grant ID")
    parser.add_argument("--export", choices=["hackathons", "grants", "extensions"], help="Export metrics")
    parser.add_argument("--format", choices=["csv", "json", "excel"], default="json", help="Export format")
    parser.add_argument("--days", type=int, default=30, help="Number of days for dashboard")
    
    args = parser.parse_args()
    
    service = EcosystemAnalyticsService()
    
    if args.dashboard:
        dashboard = await service.generate_ecosystem_dashboard(args.days)
        print(json.dumps(dashboard, indent=2, default=str))
    elif args.hackathon:
        report = await service.generate_hackathon_report(args.hackathon)
        print(json.dumps(report, indent=2, default=str))
    elif args.grant:
        report = await service.generate_grant_impact_report(args.grant)
        print(json.dumps(report, indent=2, default=str))
    elif args.export:
        data = await service.export_metrics(args.export, args.format)
        print(data.decode())
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
