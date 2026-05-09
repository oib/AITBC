# Logs Directory Organization

## Log Files Location

System logs are now properly organized in /var/log/aitbc/:

### Current Log Files:
- 
- contract_endpoints_final_status.txt
- final_production_ai_results.txt
- final_testing_fixes.txt
- issues_resolved.txt
- marketplace_results_20260329_190503.txt
- monitoring_report_20260329_192921.txt
- monitoring_report_20260329_193125.txt
- network_monitor.log
- qa_cycle.log
- qa-cycle.log
- security_summary.txt
- sync_detector.log
- testing_completion_report.txt

### Log Categories:
- **audit/**: Audit logs
- **network_monitor.log**: Network monitoring logs
- **qa_cycle.log**: QA cycle logs
- **qa-cycle.log**: QA cycle testing logs (from temp directory)
- **host_gpu_miner.log**: GPU miner client logs (2.4MB)
- **contract_endpoints_final_status.txt**: Contract endpoint status
- **final_production_ai_results.txt**: Production AI results
- **monitoring_report_*.txt**: System monitoring reports
- **testing_completion_report.txt**: Testing completion logs

## Change History
- **2026-03-30**: Moved from /opt/aitbc/results/ to /var/log/aitbc/ for proper organization
- **2026-03-30**: Consolidated /opt/aitbc/logs/host_gpu_miner.log to /var/log/aitbc/ for unified logging
- **2026-03-30**: Cleaned up /opt/aitbc/temp/ directory and moved qa-cycle.log to proper logs location
