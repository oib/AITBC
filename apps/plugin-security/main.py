"""
Plugin Security Validation Service for AITBC
Handles plugin security scanning, vulnerability detection, and validation
"""

import asyncio
import json
import subprocess
import tempfile
import os
from datetime import datetime, UTC, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel

from aitbc import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="AITBC Plugin Security Service",
    description="Security validation and vulnerability scanning for AITBC plugins",
    version="1.0.0"
)

# Data models
class SecurityScan(BaseModel):
    plugin_id: str
    version: str
    plugin_type: str
    scan_type: str  # basic, comprehensive, deep
    priority: str  # low, medium, high, critical

class Vulnerability(BaseModel):
    cve_id: Optional[str]
    severity: str  # low, medium, high, critical
    title: str
    description: str
    affected_file: str
    line_number: Optional[int]
    recommendation: str

class SecurityReport(BaseModel):
    scan_id: str
    plugin_id: str
    version: str
    scan_date: datetime
    scan_duration: float
    overall_score: str  # passed, warning, failed, critical
    vulnerabilities: List[Vulnerability]
    security_metrics: Dict[str, Any]
    recommendations: List[str]

# In-memory storage (in production, use database)
scan_reports: Dict[str, Dict] = {}
security_policies: Dict[str, Dict] = {}
scan_queue: List[Dict] = []
vulnerability_database: Dict[str, Dict] = {}

@app.get("/")
async def root():
    return {
        "service": "AITBC Plugin Security Service",
        "status": "running",
        "timestamp": datetime.now(datetime.UTC).isoformat(),
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "total_scans": len(scan_reports),
        "queue_size": len(scan_queue),
        "vulnerabilities_db": len(vulnerability_database),
        "active_policies": len(security_policies)
    }

@app.post("/api/v1/security/scan")
async def initiate_security_scan(scan: SecurityScan):
    """Initiate a security scan for a plugin"""
    scan_id = f"scan_{int(datetime.now(datetime.UTC).timestamp())}"
    
    # Create scan record
    scan_record = {
        "scan_id": scan_id,
        "plugin_id": scan.plugin_id,
        "version": scan.version,
        "plugin_type": scan.plugin_type,
        "scan_type": scan.scan_type,
        "priority": scan.priority,
        "status": "queued",
        "created_at": datetime.now(datetime.UTC).isoformat(),
        "started_at": None,
        "completed_at": None,
        "duration": None,
        "result": None
    }
    
    scan_queue.append(scan_record)
    
    # Sort queue by priority
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    scan_queue.sort(key=lambda x: priority_order.get(x["priority"], 4))
    
    logger.info(f"Security scan queued: {scan_id} for {scan.plugin_id} v{scan.version}")
    
    return {
        "scan_id": scan_id,
        "status": "queued",
        "queue_position": scan_queue.index(scan_record) + 1,
        "estimated_time": estimate_scan_time(scan.scan_type)
    }

@app.get("/api/v1/security/scan/{scan_id}")
async def get_scan_status(scan_id: str):
    """Get scan status and results"""
    if scan_id not in scan_reports and not any(s["scan_id"] == scan_id for s in scan_queue):
        raise HTTPException(status_code=404, detail="Scan not found")
    
    # Check if scan is in queue
    for scan_record in scan_queue:
        if scan_record["scan_id"] == scan_id:
            return {
                "scan_id": scan_id,
                "status": scan_record["status"],
                "queue_position": scan_queue.index(scan_record) + 1,
                "created_at": scan_record["created_at"]
            }
    
    # Return completed scan results
    return scan_reports.get(scan_id, {"status": "not_found"})

@app.get("/api/v1/security/reports")
async def list_security_reports(plugin_id: Optional[str] = None, 
                                  status: Optional[str] = None,
                                  limit: int = 50):
    """List security scan reports"""
    reports = list(scan_reports.values())
    
    # Apply filters
    if plugin_id:
        reports = [r for r in reports if r.get("plugin_id") == plugin_id]
    if status:
        reports = [r for r in reports if r.get("status") == status]
    
    # Sort by scan date (most recent first)
    reports.sort(key=lambda x: x.get("scan_date", ""), reverse=True)
    
    return {
        "reports": reports[:limit],
        "total_reports": len(reports),
        "filters": {
            "plugin_id": plugin_id,
            "status": status,
            "limit": limit
        }
    }

@app.get("/api/v1/security/vulnerabilities")
async def list_vulnerabilities(severity: Optional[str] = None,
                                plugin_id: Optional[str] = None):
    """List known vulnerabilities"""
    vulnerabilities = list(vulnerability_database.values())
    
    # Apply filters
    if severity:
        vulnerabilities = [v for v in vulnerabilities if v["severity"] == severity]
    if plugin_id:
        vulnerabilities = [v for v in vulnerabilities if v.get("plugin_id") == plugin_id]
    
    return {
        "vulnerabilities": vulnerabilities,
        "total_vulnerabilities": len(vulnerabilities),
        "filters": {
            "severity": severity,
            "plugin_id": plugin_id
        }
    }

@app.post("/api/v1/security/policies")
async def create_security_policy(policy: Dict[str, Any]):
    """Create a new security policy"""
    policy_id = f"policy_{int(datetime.now(datetime.UTC).timestamp())}"
    
    policy_record = {
        "policy_id": policy_id,
        "name": policy.get("name"),
        "description": policy.get("description"),
        "rules": policy.get("rules", []),
        "severity_thresholds": policy.get("severity_thresholds", {
            "critical": 0,
            "high": 0,
            "medium": 5,
            "low": 10
        }),
        "plugin_types": policy.get("plugin_types", []),
        "active": True,
        "created_at": datetime.now(datetime.UTC).isoformat(),
        "updated_at": datetime.now(datetime.UTC).isoformat()
    }
    
    security_policies[policy_id] = policy_record
    
    logger.info(f"Security policy created: {policy_id} - {policy.get('name')}")
    
    return {
        "policy_id": policy_id,
        "name": policy.get("name"),
        "status": "created",
        "active": True
    }

@app.get("/api/v1/security/policies")
async def list_security_policies():
    """List all security policies"""
    return {
        "policies": list(security_policies.values()),
        "total_policies": len(security_policies),
        "active_policies": len([p for p in security_policies.values() if p["active"]])
    }

@app.post("/api/v1/security/upload")
async def upload_plugin_for_scan(plugin_id: str, version: str, 
                                 file: UploadFile = File(...)):
    """Upload plugin file for security scanning"""
    # Validate file
    if not file.filename.endswith(('.py', '.zip', '.tar.gz')):
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=file.filename) as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_file_path = tmp_file.name
    
    # Initiate scan
    scan = SecurityScan(
        plugin_id=plugin_id,
        version=version,
        plugin_type="uploaded",
        scan_type="comprehensive",
        priority="medium"
    )
    
    scan_result = await initiate_security_scan(scan)
    
    # Start async scan process
    asyncio.create_task(process_scan_file(scan_result["scan_id"], tmp_file_path, file.filename))
    
    return {
        "scan_id": scan_result["scan_id"],
        "filename": file.filename,
        "file_size": len(content),
        "status": "uploaded_and_queued"
    }

@app.get("/api/v1/security/dashboard")
async def get_security_dashboard():
    """Get security dashboard data"""
    total_scans = len(scan_reports)
    recent_scans = [r for r in scan_reports.values() 
                   if datetime.fromisoformat(r["scan_date"]) > datetime.now(datetime.UTC) - timedelta(days=7)]
    
    # Calculate statistics
    scan_results = list(scan_reports.values())
    passed_scans = len([r for r in scan_results if r.get("overall_score") == "passed"])
    warning_scans = len([r for r in scan_results if r.get("overall_score") == "warning"])
    failed_scans = len([r for r in scan_results if r.get("overall_score") in ["failed", "critical"]])
    
    # Vulnerability statistics
    all_vulnerabilities = []
    for report in scan_results:
        all_vulnerabilities.extend(report.get("vulnerabilities", []))
    
    vuln_by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for vuln in all_vulnerabilities:
        vuln_by_severity[vuln["severity"]] = vuln_by_severity.get(vuln["severity"], 0) + 1
    
    return {
        "dashboard": {
            "total_scans": total_scans,
            "recent_scans": len(recent_scans),
            "scan_results": {
                "passed": passed_scans,
                "warning": warning_scans,
                "failed": failed_scans
            },
            "vulnerabilities": {
                "total": len(all_vulnerabilities),
                "by_severity": vuln_by_severity
            },
            "queue_size": len(scan_queue),
            "active_policies": len([p for p in security_policies.values() if p["active"]])
        },
        "generated_at": datetime.now(datetime.UTC).isoformat()
    }

# Core security scanning functions
async def process_scan_file(scan_id: str, file_path: str, filename: str):
    """Process uploaded file for security scanning"""
    try:
        # Update scan status
        for scan_record in scan_queue:
            if scan_record["scan_id"] == scan_id:
                scan_record["status"] = "running"
                scan_record["started_at"] = datetime.now(datetime.UTC).isoformat()
                break
        
        start_time = datetime.now(datetime.UTC)
        
        # Perform security scan
        scan_result = await perform_security_scan(file_path, filename)
        
        end_time = datetime.now(datetime.UTC)
        duration = (end_time - start_time).total_seconds()
        
        # Create security report
        security_report = SecurityReport(
            scan_id=scan_id,
            plugin_id=scan_record["plugin_id"],
            version=scan_record["version"],
            scan_date=end_time,
            scan_duration=duration,
            overall_score=calculate_overall_score(scan_result),
            vulnerabilities=scan_result["vulnerabilities"],
            security_metrics=scan_result["metrics"],
            recommendations=scan_result["recommendations"]
        )
        
        # Save report
        report_data = {
            "scan_id": scan_id,
            "plugin_id": scan_record["plugin_id"],
            "version": scan_record["version"],
            "scan_date": security_report.scan_date.isoformat(),
            "scan_duration": security_report.scan_duration,
            "overall_score": security_report.overall_score,
            "vulnerabilities": [v.dict() for v in security_report.vulnerabilities],
            "security_metrics": security_report.security_metrics,
            "recommendations": security_report.recommendations,
            "status": "completed",
            "completed_at": security_report.scan_date.isoformat()
        }
        
        scan_reports[scan_id] = report_data
        
        # Remove from queue
        scan_queue[:] = [s for s in scan_queue if s["scan_id"] != scan_id]
        
        # Clean up temporary file
        os.unlink(file_path)
        
        logger.info(f"Security scan completed: {scan_id} - {security_report.overall_score}")
        
    except Exception as e:
        logger.error(f"Error processing scan {scan_id}: {str(e)}")
        # Update scan status to failed
        for scan_record in scan_queue:
            if scan_record["scan_id"] == scan_id:
                scan_record["status"] = "failed"
                scan_record["completed_at"] = datetime.now(datetime.UTC).isoformat()
                break

async def perform_security_scan(file_path: str, filename: str) -> Dict[str, Any]:
    """Perform actual security scanning"""
    vulnerabilities = []
    metrics = {}
    recommendations = []
    
    # File analysis
    try:
        # Basic file checks
        file_size = os.path.getsize(file_path)
        metrics["file_size"] = file_size
        
        # Check for suspicious patterns (simplified for demo)
        if filename.endswith('.py'):
            vulnerabilities.extend(scan_python_file(file_path))
        elif filename.endswith('.zip'):
            vulnerabilities.extend(scan_zip_file(file_path))
        
        # Check common vulnerabilities
        vulnerabilities.extend(check_common_vulnerabilities(file_path))
        
        # Generate recommendations
        recommendations = generate_recommendations(vulnerabilities)
        
        # Calculate metrics
        metrics.update({
            "vulnerability_count": len(vulnerabilities),
            "severity_distribution": get_severity_distribution(vulnerabilities),
            "file_type": filename.split('.')[-1],
            "scan_timestamp": datetime.now(datetime.UTC).isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error during security scan: {str(e)}")
        vulnerabilities.append({
            "severity": "medium",
            "title": "Scan Error",
            "description": f"Error during scanning: {str(e)}",
            "affected_file": filename,
            "recommendation": "Review file and rescan"
        })
    
    return {
        "vulnerabilities": vulnerabilities,
        "metrics": metrics,
        "recommendations": recommendations
    }

async def scan_python_file(file_path: str) -> List[Dict]:
    """Scan Python file for security issues"""
    vulnerabilities = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')
        
        # Check for suspicious patterns
        suspicious_patterns = {
            "eval": "Use of eval() function",
            "exec": "Use of exec() function",
            "subprocess.call": "Unsafe subprocess usage",
            "os.system": "Use of os.system() function",
            "pickle.loads": "Unsafe pickle deserialization",
            "input(": "Use of input() function"
        }
        
        for i, line in enumerate(lines, 1):
            for pattern, description in suspicious_patterns.items():
                if pattern in line:
                    vulnerabilities.append({
                        "severity": "medium",
                        "title": "Suspicious Code Pattern",
                        "description": description,
                        "affected_file": file_path,
                        "line_number": i,
                        "recommendation": f"Review usage of {pattern} and consider safer alternatives"
                    })
        
        # Check for hardcoded credentials
        if any('password' in line.lower() or 'secret' in line.lower() or 'key' in line.lower() 
               for line in lines):
            vulnerabilities.append({
                "severity": "high",
                "title": "Potential Hardcoded Credentials",
                "description": "Possible hardcoded sensitive information detected",
                "affected_file": file_path,
                "recommendation": "Use environment variables or secure configuration management"
            })
        
    except Exception as e:
        logger.error(f"Error scanning Python file: {str(e)}")
    
    return vulnerabilities

async def scan_zip_file(file_path: str) -> List[Dict]:
    """Scan ZIP file for security issues"""
    vulnerabilities = []
    
    try:
        import zipfile
        
        with zipfile.ZipFile(file_path, 'r') as zip_file:
            # Check for suspicious files
            for file_info in zip_file.filelist:
                filename = file_info.filename.lower()
                
                # Check for suspicious file types
                suspicious_extensions = ['.exe', '.bat', '.cmd', '.scr', '.dll', '.so']
                if any(filename.endswith(ext) for ext in suspicious_extensions):
                    vulnerabilities.append({
                        "severity": "high",
                        "title": "Suspicious File Type",
                        "description": f"Suspicious file found in archive: {filename}",
                        "affected_file": file_path,
                        "recommendation": "Review file contents and ensure they are safe"
                    })
                
                # Check for large files (potential data exfiltration)
                if file_info.file_size > 100 * 1024 * 1024:  # 100MB
                    vulnerabilities.append({
                        "severity": "medium",
                        "title": "Large File Detected",
                        "description": f"Large file detected: {filename} ({file_info.file_size} bytes)",
                        "affected_file": file_path,
                        "recommendation": "Verify file contents and necessity"
                    })
        
    except Exception as e:
        logger.error(f"Error scanning ZIP file: {str(e)}")
        vulnerabilities.append({
            "severity": "medium",
            "title": "ZIP Scan Error",
            "description": f"Error scanning ZIP file: {str(e)}",
            "affected_file": file_path,
            "recommendation": "Verify ZIP file integrity"
        })
    
    return vulnerabilities

async def check_common_vulnerabilities(file_path: str) -> List[Dict]:
    """Check for common security vulnerabilities"""
    vulnerabilities = []
    
    # Mock vulnerability database check
    known_vulnerabilities = {
        "requests": "Check for outdated requests library",
        "urllib": "Check for urllib security issues",
        "socket": "Check for unsafe socket usage"
    }
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        for lib, issue in known_vulnerabilities.items():
            if lib in content:
                vulnerabilities.append({
                    "severity": "low",
                    "title": f"Library Security Check",
                    "description": issue,
                    "affected_file": file_path,
                    "recommendation": f"Update {lib} to latest secure version"
                })
        
    except Exception as e:
        logger.error(f"Error checking common vulnerabilities: {str(e)}")
    
    return vulnerabilities

def calculate_overall_score(scan_result: Dict[str, Any]) -> str:
    """Calculate overall security score"""
    vulnerabilities = scan_result["vulnerabilities"]
    
    if not vulnerabilities:
        return "passed"
    
    # Count by severity
    critical_count = len([v for v in vulnerabilities if v["severity"] == "critical"])
    high_count = len([v for v in vulnerabilities if v["severity"] == "high"])
    medium_count = len([v for v in vulnerabilities if v["severity"] == "medium"])
    low_count = len([v for v in vulnerabilities if v["severity"] == "low"])
    
    # Determine overall score
    if critical_count > 0:
        return "critical"
    elif high_count > 2:
        return "failed"
    elif high_count > 0 or medium_count > 5:
        return "warning"
    else:
        return "passed"

def generate_recommendations(vulnerabilities: List[Dict]) -> List[str]:
    """Generate security recommendations"""
    recommendations = []
    
    if not vulnerabilities:
        recommendations.append("No security issues detected. Plugin appears secure.")
        return recommendations
    
    # Generate recommendations based on vulnerabilities
    severity_counts = {}
    for vuln in vulnerabilities:
        severity = vuln["severity"]
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
    
    if severity_counts.get("critical", 0) > 0:
        recommendations.append("CRITICAL: Address critical security vulnerabilities immediately.")
    
    if severity_counts.get("high", 0) > 0:
        recommendations.append("HIGH: Review and fix high-severity security issues.")
    
    if severity_counts.get("medium", 0) > 3:
        recommendations.append("MEDIUM: Consider addressing medium-severity issues.")
    
    recommendations.append("Regular security scans recommended for ongoing protection.")
    recommendations.append("Keep all dependencies updated to latest secure versions.")
    
    return recommendations

def get_severity_distribution(vulnerabilities: List[Dict]) -> Dict[str, int]:
    """Get vulnerability severity distribution"""
    distribution = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for vuln in vulnerabilities:
        severity = vuln["severity"]
        distribution[severity] = distribution.get(severity, 0) + 1
    return distribution

def estimate_scan_time(scan_type: str) -> str:
    """Estimate scan time based on scan type"""
    estimates = {
        "basic": "1-2 minutes",
        "comprehensive": "5-10 minutes",
        "deep": "15-30 minutes"
    }
    return estimates.get(scan_type, "5-10 minutes")

# Background task for processing scan queue
async def process_scan_queue():
    """Background task to process security scan queue"""
    while True:
        await asyncio.sleep(10)  # Check queue every 10 seconds
        
        if scan_queue:
            # Get next scan from queue
            scan_record = scan_queue[0]
            
            # Process scan (in production, this would be more sophisticated)
            logger.info(f"Processing scan from queue: {scan_record['scan_id']}")
            
            # Simulate processing time
            await asyncio.sleep(2)

@app.on_event("startup")
async def startup_event():
    logger.info("Starting AITBC Plugin Security Service")
    # Initialize vulnerability database
    initialize_vulnerability_database()
    # Start queue processing
    asyncio.create_task(process_scan_queue())

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down AITBC Plugin Security Service")

def initialize_vulnerability_database():
    """Initialize vulnerability database with known issues"""
    # Mock data for demo
    vulnerabilities = [
        {
            "vuln_id": "CVE-2023-1234",
            "severity": "high",
            "title": "Buffer Overflow in Library X",
            "description": "Buffer overflow vulnerability in commonly used library",
            "affected_plugins": ["plugin1", "plugin2"],
            "recommendation": "Update to latest version"
        },
        {
            "vuln_id": "CVE-2023-5678",
            "severity": "medium",
            "title": "Information Disclosure",
            "description": "Potential information disclosure in logging",
            "affected_plugins": ["plugin3"],
            "recommendation": "Review logging implementation"
        }
    ]
    
    for vuln in vulnerabilities:
        vulnerability_database[vuln["vuln_id"]] = vuln

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8015, log_level="info")
