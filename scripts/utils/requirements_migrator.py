#!/usr/bin/env python3
"""
AITBC Requirements Migration Tool
Core function to migrate service requirements to central and identify 3rd party modules
"""

import os
import sys
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple
import argparse

class RequirementsMigrator:
    """Core requirements migration and analysis tool"""
    
    def __init__(self, base_path: str = "/opt/aitbc"):
        self.base_path = Path(base_path)
        self.central_req = self.base_path / "requirements.txt"
        self.central_packages = set()
        self.migration_log = []
        
    def load_central_requirements(self) -> Set[str]:
        """Load central requirements packages"""
        if not self.central_req.exists():
            print(f"❌ Central requirements not found: {self.central_req}")
            return set()
            
        packages = set()
        with open(self.central_req, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Extract package name (before version specifier)
                    match = re.match(r'^([a-zA-Z0-9_-]+)', line)
                    if match:
                        packages.add(match.group(1))
        
        self.central_packages = packages
        print(f"✅ Loaded {len(packages)} packages from central requirements")
        return packages
    
    def find_requirements_files(self) -> List[Path]:
        """Find all requirements.txt files"""
        files = []
        for req_file in self.base_path.rglob("requirements.txt"):
            if req_file != self.central_req:
                files.append(req_file)
        return files
    
    def parse_requirements_file(self, file_path: Path) -> List[str]:
        """Parse individual requirements file"""
        requirements = []
        try:
            with open(file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        requirements.append(line)
        except Exception as e:
            print(f"❌ Error reading {file_path}: {e}")
        return requirements
    
    def analyze_coverage(self, file_path: Path, requirements: List[str]) -> Dict:
        """Analyze coverage of requirements by central packages"""
        covered = []
        not_covered = []
        version_upgrades = []
        
        if not requirements:
            return {
                'file': file_path,
                'total': 0,
                'covered': 0,
                'not_covered': [],
                'coverage_percent': 100.0,
                'version_upgrades': []
            }
        
        for req in requirements:
            # Extract package name
            match = re.match(r'^([a-zA-Z0-9_-]+)([><=!]+.*)?', req)
            if not match:
                continue
                
            package_name = match.group(1)
            version_spec = match.group(2) or ""
            
            if package_name in self.central_packages:
                covered.append(req)
                # Check for version upgrades
                central_req = self._find_central_requirement(package_name)
                if central_req and version_spec and central_req != version_spec:
                    version_upgrades.append({
                        'package': package_name,
                        'old_version': version_spec,
                        'new_version': central_req
                    })
            else:
                not_covered.append(req)
        
        return {
            'file': file_path,
            'total': len(requirements),
            'covered': len(covered),
            'not_covered': not_covered,
            'coverage_percent': (len(covered) / len(requirements) * 100) if requirements else 100.0,
            'version_upgrades': version_upgrades
        }
    
    def _find_central_requirement(self, package_name: str) -> str:
        """Find requirement specification in central file"""
        try:
            with open(self.central_req, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        match = re.match(rf'^{re.escape(package_name)}([><=!]+.+)', line)
                        if match:
                            return match.group(1)
        except:
            pass
        return ""
    
    def categorize_uncovered(self, not_covered: List[str]) -> Dict[str, List[str]]:
        """Categorize uncovered requirements"""
        categories = {
            'core_infrastructure': [],
            'ai_ml': [],
            'blockchain': [],
            'translation_nlp': [],
            'monitoring': [],
            'testing': [],
            'security': [],
            'utilities': [],
            'other': []
        }
        
        # Package categorization mapping
        category_map = {
            # Core Infrastructure
            'fastapi': 'core_infrastructure', 'uvicorn': 'core_infrastructure',
            'sqlalchemy': 'core_infrastructure', 'pydantic': 'core_infrastructure',
            'sqlmodel': 'core_infrastructure', 'alembic': 'core_infrastructure',
            
            # AI/ML
            'torch': 'ai_ml', 'tensorflow': 'ai_ml', 'numpy': 'ai_ml',
            'pandas': 'ai_ml', 'scikit-learn': 'ai_ml', 'transformers': 'ai_ml',
            'opencv-python': 'ai_ml', 'pillow': 'ai_ml', 'tenseal': 'ai_ml',
            
            # Blockchain
            'web3': 'blockchain', 'eth-utils': 'blockchain', 'eth-account': 'blockchain',
            'cryptography': 'blockchain', 'ecdsa': 'blockchain', 'base58': 'blockchain',
            
            # Translation/NLP
            'openai': 'translation_nlp', 'google-cloud-translate': 'translation_nlp',
            'deepl': 'translation_nlp', 'langdetect': 'translation_nlp',
            'polyglot': 'translation_nlp', 'fasttext': 'translation_nlp',
            'nltk': 'translation_nlp', 'spacy': 'translation_nlp',
            
            # Monitoring
            'prometheus-client': 'monitoring', 'structlog': 'monitoring',
            'sentry-sdk': 'monitoring',
            
            # Testing
            'pytest': 'testing', 'pytest-asyncio': 'testing', 'pytest-mock': 'testing',
            
            # Security
            'python-jose': 'security', 'passlib': 'security', 'keyring': 'security',
            
            # Utilities
            'click': 'utilities', 'rich': 'utilities', 'typer': 'utilities',
            'httpx': 'utilities', 'requests': 'utilities', 'aiohttp': 'utilities',
        }
        
        for req in not_covered:
            package_name = re.match(r'^([a-zA-Z0-9_-]+)', req).group(1)
            category = category_map.get(package_name, 'other')
            categories[category].append(req)
        
        return categories
    
    def migrate_requirements(self, dry_run: bool = True) -> Dict:
        """Migrate requirements to central if fully covered"""
        results = {
            'migrated': [],
            'kept': [],
            'errors': []
        }
        
        self.load_central_requirements()
        req_files = self.find_requirements_files()
        
        for file_path in req_files:
            try:
                requirements = self.parse_requirements_file(file_path)
                analysis = self.analyze_coverage(file_path, requirements)
                
                if analysis['coverage_percent'] == 100:
                    if not dry_run:
                        file_path.unlink()
                        results['migrated'].append({
                            'file': str(file_path),
                            'packages': analysis['covered']
                        })
                        print(f"✅ Migrated: {file_path} ({len(analysis['covered'])} packages)")
                    else:
                        results['migrated'].append({
                            'file': str(file_path),
                            'packages': analysis['covered']
                        })
                        print(f"🔄 Would migrate: {file_path} ({len(analysis['covered'])} packages)")
                else:
                    categories = self.categorize_uncovered(analysis['not_covered'])
                    results['kept'].append({
                        'file': str(file_path),
                        'coverage': analysis['coverage_percent'],
                        'not_covered': analysis['not_covered'],
                        'categories': categories
                    })
                    print(f"⚠️  Keep: {file_path} ({analysis['coverage_percent']:.1f}% covered)")
                    
            except Exception as e:
                results['errors'].append({
                    'file': str(file_path),
                    'error': str(e)
                })
                print(f"❌ Error processing {file_path}: {e}")
        
        return results
    
    def generate_report(self, results: Dict) -> str:
        """Generate migration report"""
        report = []
        report.append("# AITBC Requirements Migration Report\n")
        
        # Summary
        report.append("## Summary")
        report.append(f"- Files analyzed: {len(results['migrated']) + len(results['kept']) + len(results['errors'])}")
        report.append(f"- Files migrated: {len(results['migrated'])}")
        report.append(f"- Files kept: {len(results['kept'])}")
        report.append(f"- Errors: {len(results['errors'])}\n")
        
        # Migrated files
        if results['migrated']:
            report.append("## ✅ Migrated Files")
            for item in results['migrated']:
                packages = item['packages'] if isinstance(item['packages'], list) else []
                report.append(f"- `{item['file']}` ({len(packages)} packages)")
            report.append("")
        
        # Kept files with analysis
        if results['kept']:
            report.append("## ⚠️ Files Kept (Specialized Dependencies)")
            for item in results['kept']:
                report.append(f"### `{item['file']}`")
                report.append(f"- Coverage: {item['coverage']:.1f}%")
                report.append(f"- Uncovered packages: {len(item['not_covered'])}")
                
                for category, packages in item['categories'].items():
                    if packages:
                        report.append(f"  - **{category.replace('_', ' ').title()}**: {len(packages)} packages")
                        for pkg in packages[:3]:  # Show first 3
                            report.append(f"    - `{pkg}`")
                        if len(packages) > 3:
                            report.append(f"    - ... and {len(packages) - 3} more")
                report.append("")
        
        # Errors
        if results['errors']:
            report.append("## ❌ Errors")
            for item in results['errors']:
                report.append(f"- `{item['file']}`: {item['error']}")
            report.append("")
        
        return "\n".join(report)
    
    def suggest_3rd_party_modules(self, results: Dict) -> Dict[str, List[str]]:
        """Suggest 3rd party module groupings"""
        modules = {
            'ai_ml_translation': [],
            'blockchain_web3': [],
            'monitoring_observability': [],
            'testing_quality': [],
            'security_compliance': []
        }
        
        for item in results['kept']:
            categories = item['categories']
            
            # AI/ML + Translation
            ai_ml_packages = categories.get('ai_ml', []) + categories.get('translation_nlp', [])
            if ai_ml_packages:
                modules['ai_ml_translation'].extend([pkg.split('>=')[0] for pkg in ai_ml_packages])
            
            # Blockchain
            blockchain_packages = categories.get('blockchain', [])
            if blockchain_packages:
                modules['blockchain_web3'].extend([pkg.split('>=')[0] for pkg in blockchain_packages])
            
            # Monitoring
            monitoring_packages = categories.get('monitoring', [])
            if monitoring_packages:
                modules['monitoring_observability'].extend([pkg.split('>=')[0] for pkg in monitoring_packages])
            
            # Testing
            testing_packages = categories.get('testing', [])
            if testing_packages:
                modules['testing_quality'].extend([pkg.split('>=')[0] for pkg in testing_packages])
            
            # Security
            security_packages = categories.get('security', [])
            if security_packages:
                modules['security_compliance'].extend([pkg.split('>=')[0] for pkg in security_packages])
        
        # Remove duplicates and sort
        for key in modules:
            modules[key] = sorted(list(set(modules[key])))
        
        return modules


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="AITBC Requirements Migration Tool")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without actually doing it")
    parser.add_argument("--execute", action="store_true", help="Actually migrate files")
    parser.add_argument("--base-path", default="/opt/aitbc", help="Base path for AITBC repository")
    
    args = parser.parse_args()
    
    if not args.dry_run and not args.execute:
        print("Use --dry-run to preview or --execute to actually migrate")
        return
    
    migrator = RequirementsMigrator(args.base_path)
    
    print("🔍 Analyzing AITBC requirements files...")
    results = migrator.migrate_requirements(dry_run=not args.execute)
    
    print("\n📊 Generating report...")
    report = migrator.generate_report(results)
    
    # Save report
    report_file = Path(args.base_path) / "docs" / "REQUIREMENTS_MIGRATION_REPORT.md"
    report_file.parent.mkdir(exist_ok=True)
    with open(report_file, 'w') as f:
        f.write(report)
    
    print(f"📄 Report saved to: {report_file}")
    
    # Suggest 3rd party modules
    modules = migrator.suggest_3rd_party_modules(results)
    print("\n🎯 Suggested 3rd Party Modules:")
    
    for module_name, packages in modules.items():
        if packages:
            print(f"\n📦 {module_name.replace('_', ' ').title()}:")
            for pkg in packages:
                print(f"   - {pkg}")


if __name__ == "__main__":
    main()
