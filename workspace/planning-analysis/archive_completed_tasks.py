#!/usr/bin/env python3
"""
Task Archiver
Moves completed tasks from planning to appropriate archive folders
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

def categorize_task_for_archive(task_description):
    """Categorize task for archiving"""
    desc_lower = task_description.lower()
    
    if any(word in desc_lower for word in ['cli', 'command', 'interface']):
        return 'cli'
    elif any(word in desc_lower for word in ['api', 'backend', 'service']):
        return 'backend'
    elif any(word in desc_lower for word in ['infrastructure', 'server', 'deployment']):
        return 'infrastructure'
    elif any(word in desc_lower for word in ['security', 'auth', 'encryption']):
        return 'security'
    elif any(word in desc_lower for word in ['exchange', 'trading', 'market']):
        return 'exchange'
    elif any(word in desc_lower for word in ['wallet', 'transaction', 'blockchain']):
        return 'blockchain'
    else:
        return 'general'

def archive_completed_tasks(verification_file, planning_dir, archive_dir):
    """Archive completed tasks from planning to archive"""
    
    with open(verification_file, 'r') as f:
        verification_results = json.load(f)
    
    planning_path = Path(planning_dir)
    archive_path = Path(archive_dir)
    
    archived_tasks = []
    
    for result in verification_results:
        if 'error' in result:
            continue
        
        file_path = Path(result['file_path'])
        
        # Read original file
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract completed tasks
        completed_tasks = []
        for task in result.get('completed_tasks', []):
            if task.get('documented', False):  # Only archive documented tasks
                category = categorize_task_for_archive(task['task_description'])
                
                # Create archive entry
                archive_entry = {
                    'task_description': task['task_description'],
                    'category': category,
                    'completion_date': datetime.now().strftime('%Y-%m-%d'),
                    'original_file': str(file_path.relative_to(planning_path)),
                    'line_number': task['line_number'],
                    'original_content': task['line_content']
                }
                
                completed_tasks.append(archive_entry)
        
        if completed_tasks:
            # Create archive file
            archive_filename = file_path.stem + '_completed_tasks.md'
            archive_filepath = archive_path / archive_filename
            
            # Ensure archive directory exists
            archive_filepath.parent.mkdir(parents=True, exist_ok=True)
            
            # Create archive content
            archive_content = f"""# Archived Completed Tasks

**Source File**: {file_path.relative_to(planning_path)}
**Archive Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Completed Tasks

"""
            
            for task in completed_tasks:
                archive_content += f"### {task['task_description']}\n\n"
                archive_content += f"- **Category**: {task['category']}\n"
                archive_content += f"- **Completion Date**: {task['completion_date']}\n"
                archive_content += f"- **Original Line**: {task['line_number']}\n"
                archive_content += f"- **Original Content**: {task['original_content']}\n\n"
            
            # Write archive file
            with open(archive_filepath, 'w', encoding='utf-8') as f:
                f.write(archive_content)
            
            archived_tasks.append({
                'original_file': str(file_path),
                'archive_file': str(archive_filepath),
                'tasks_count': len(completed_tasks),
                'tasks': completed_tasks
            })
            
            print(f"Archived {len(completed_tasks)} tasks to {archive_filepath}")
    
    return archived_tasks

if __name__ == "__main__":
    import sys
    
    verification_file = sys.argv[1] if len(sys.argv) > 1 else 'documentation_status.json'
    planning_dir = sys.argv[2] if len(sys.argv) > 2 else '/opt/aitbc/docs/10_plan'
    archive_dir = sys.argv[3] if len(sys.argv) > 3 else '/opt/aitbc/docs/archive'
    
    archived_tasks = archive_completed_tasks(verification_file, planning_dir, archive_dir)
    
    print(f"Archived tasks from {len(archived_tasks)} files")
    
    # Save archive results
    with open('archive_results.json', 'w') as f:
        json.dump(archived_tasks, f, indent=2)
