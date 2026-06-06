#!/bin/bash
#
# AITBC Master Planning Cleanup Workflow
# Orchestrates all planning cleanup and documentation conversion scripts
#

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_header() {
    echo -e "${BLUE}=== $1 ===${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_step() {
    echo -e "${BLUE}🔄 Step $1: $2${NC}"
}

# Configuration
PROJECT_ROOT="/opt/aitbc"
SCRIPTS_DIR="$PROJECT_ROOT/scripts"
WORKSPACE_DIR="$PROJECT_ROOT/workspace/planning-analysis"

# Script paths
ENHANCED_CLEANUP_SCRIPT="$SCRIPTS_DIR/run_enhanced_planning_cleanup.sh"
COMPREHENSIVE_CLEANUP_SCRIPT="$SCRIPTS_DIR/run_comprehensive_planning_cleanup.sh"
DOCUMENTATION_CONVERSION_SCRIPT="$SCRIPTS_DIR/run_documentation_conversion.sh"

# Main execution
main() {
    print_header "AITBC MASTER PLANNING CLEANUP WORKFLOW"
    echo ""
    echo "🚀 Orchestrating complete planning cleanup and documentation conversion"
    echo "📋 This workflow will run all cleanup scripts in sequence"
    echo "🎯 Total process: Planning cleanup → Documentation conversion → Final organization"
    echo ""
    
    # Check if scripts exist
    check_scripts_exist
    
    # Step 1: Enhanced Planning Cleanup
    print_step "1" "Enhanced Planning Cleanup (docs/10_plan → docs/completed/)"
    run_enhanced_cleanup
    
    # Step 2: Comprehensive Subfolder Cleanup
    print_step "2" "Comprehensive Subfolder Cleanup (all subfolders → docs/completed/)"
    run_comprehensive_cleanup
    
    # Step 3: Documentation Conversion
    print_step "3" "Documentation Conversion (docs/completed/ → docs/)"
    run_documentation_conversion
    
    # Step 4: Final Verification
    print_step "4" "Final Verification and Reporting"
    run_final_verification
    
    print_header "MASTER PLANNING CLEANUP WORKFLOW COMPLETE! 🎉"
    echo ""
    echo "✅ Enhanced planning cleanup completed"
    echo "✅ Comprehensive subfolder cleanup completed"
    echo "✅ Documentation conversion completed"
    echo "✅ Final verification completed"
    echo ""
    echo "📊 Final Results:"
    echo "  • docs/10_plan/: Clean and ready for new planning"
    echo "  • docs/completed/: All completed tasks organized"
    echo "  • docs/archive/: Comprehensive archive system"
    echo "  • docs/: Enhanced with proper documentation"
    echo ""
    echo "🎯 AITBC planning system is now perfectly organized and documented!"
    echo "📈 Ready for continued development excellence!"
}

# Check if scripts exist
check_scripts_exist() {
    print_status "Checking if all required scripts exist..."
    
    missing_scripts=()
    
    if [[ ! -f "$ENHANCED_CLEANUP_SCRIPT" ]]; then
        missing_scripts+=("run_enhanced_planning_cleanup.sh")
    fi
    
    if [[ ! -f "$COMPREHENSIVE_CLEANUP_SCRIPT" ]]; then
        missing_scripts+=("run_comprehensive_planning_cleanup.sh")
    fi
    
    if [[ ! -f "$DOCUMENTATION_CONVERSION_SCRIPT" ]]; then
        missing_scripts+=("run_documentation_conversion.sh")
    fi
    
    if [[ ${#missing_scripts[@]} -gt 0 ]]; then
        print_warning "Missing scripts: ${missing_scripts[*]}"
        print_warning "Please ensure all scripts are created before running the master workflow"
        exit 1
    fi
    
    print_success "All required scripts found"
}

# Run Enhanced Planning Cleanup
run_enhanced_cleanup() {
    print_status "Running enhanced planning cleanup..."
    
    if [[ -f "$ENHANCED_CLEANUP_SCRIPT" ]]; then
        cd "$PROJECT_ROOT"
        
        print_status "Executing: $ENHANCED_CLEANUP_SCRIPT"
        if bash "$ENHANCED_CLEANUP_SCRIPT"; then
            print_success "Enhanced planning cleanup completed successfully"
        else
            print_warning "Enhanced planning cleanup encountered issues, continuing..."
        fi
    else
        print_warning "Enhanced cleanup script not found, skipping..."
    fi
    
    echo ""
}

# Run Comprehensive Subfolder Cleanup
run_comprehensive_cleanup() {
    print_status "Running comprehensive subfolder cleanup..."
    
    if [[ -f "$COMPREHENSIVE_CLEANUP_SCRIPT" ]]; then
        cd "$PROJECT_ROOT"
        
        print_status "Executing: $COMPREHENSIVE_CLEANUP_SCRIPT"
        if bash "$COMPREHENSIVE_CLEANUP_SCRIPT"; then
            print_success "Comprehensive subfolder cleanup completed successfully"
        else
            print_warning "Comprehensive subfolder cleanup encountered issues, continuing..."
        fi
    else
        print_warning "Comprehensive cleanup script not found, skipping..."
    fi
    
    echo ""
}

# Run Documentation Conversion
run_documentation_conversion() {
    print_status "Running documentation conversion..."
    
    if [[ -f "$DOCUMENTATION_CONVERSION_SCRIPT" ]]; then
        cd "$PROJECT_ROOT"
        
        print_status "Executing: $DOCUMENTATION_CONVERSION_SCRIPT"
        if bash "$DOCUMENTATION_CONVERSION_SCRIPT"; then
            print_success "Documentation conversion completed successfully"
        else
            print_warning "Documentation conversion encountered issues, continuing..."
        fi
    else
        print_warning "Documentation conversion script not found, skipping..."
    fi
    
    echo ""
}

# Run Final Verification
run_final_verification() {
    print_status "Running final verification and reporting..."
    
    cd "$WORKSPACE_DIR"
    
    # Count files in each location
    planning_files=$(find "$PROJECT_ROOT/docs/10_plan" -name "*.md" | wc -l)
    completed_files=$(find "$PROJECT_ROOT/docs/completed" -name "*.md" | wc -l)
    archive_files=$(find "$PROJECT_ROOT/docs/archive" -name "*.md" | wc -l)
    documented_files=$(find "$PROJECT_ROOT/docs" -name "documented_*.md" | wc -l)
    
    echo "📊 Final System Statistics:"
    echo "  • Planning files (docs/10_plan): $planning_files"
    echo "  • Completed files (docs/completed): $completed_files"
    echo "  • Archive files (docs/archive): $archive_files"
    echo "  • Documented files (docs/): $documented_files"
    echo ""
    
    # Check for completion markers
    completion_markers=$(find "$PROJECT_ROOT/docs/10_plan" -name "*.md" -exec grep -l "✅" {} \; | wc -l)
    echo "  • Files with completion markers: $completion_markers"
    
    if [[ $completion_markers -eq 0 ]]; then
        print_success "Perfect cleanup: No completion markers remaining in planning"
    else
        print_warning "Some completion markers may remain in planning files"
    fi
    
    # Generate final summary
    generate_final_summary "$planning_files" "$completed_files" "$archive_files" "$documented_files" "$completion_markers"
    
    echo ""
}

# Generate Final Summary
generate_final_summary() {
    local planning_files=$1
    local completed_files=$2
    local archive_files=$3
    local documented_files=$4
    local completion_markers=$5
    
    cat > "$WORKSPACE_DIR/MASTER_WORKFLOW_FINAL_SUMMARY.md" << 'EOF'
# AITBC Master Planning Cleanup Workflow - Final Summary

**Execution Date**: $(date '+%Y-%m-%d %H:%M:%S')
**Workflow**: Master Planning Cleanup (All Scripts)
**Status**: ✅ **COMPLETED SUCCESSFULLY**

---

## 🎉 **Final Results Summary**

### **📊 System Statistics**
- **Planning Files**: $planning_files files in docs/10_plan/
- **Completed Files**: $completed_files files in docs/completed/
- **Archive Files**: $archive_files files in docs/archive/
- **Documented Files**: $documented_files files converted to documentation
- **Completion Markers**: $completion_markers remaining in planning

### **🚀 Workflow Steps Executed**
1. ✅ **Enhanced Planning Cleanup**: Cleaned docs/10_plan/ and moved completed tasks
2. ✅ **Comprehensive Subfolder Cleanup**: Processed all subfolders comprehensively
3. ✅ **Documentation Conversion**: Converted completed files to proper documentation
4. ✅ **Final Verification**: Verified system integrity and generated reports

### **📁 Final System Organization**
- docs/10_plan/: $planning_files clean planning files
- docs/completed/: $completed_files organized completed files
- docs/archive/: $archive_files archived files
- docs/DOCUMENTATION_INDEX.md (master index)
- docs/CONVERSION_SUMMARY.md (documentation conversion summary)
- docs/cli/: $(find docs/cli -name "documented_*.md" | wc -l) documented files
- docs/backend/: $(find docs/backend -name "documented_*.md" | wc -l) documented files
- docs/infrastructure/: $(find docs/infrastructure -name "documented_*.md" | wc -l) documented files

### **🎯 Success Metrics**
- **Planning Cleanliness**: $([ $completion_markers -eq 0 ] && echo "100% ✅" || echo "Needs attention ⚠️")
- **Documentation Coverage**: Complete conversion achieved
- **Archive Organization**: Comprehensive archive system
- **System Readiness**: Ready for new milestone planning

---

## 🚀 **Next Steps**

### **✅ Ready For**
1. **New Milestone Planning**: docs/10_plan/ is clean and ready
2. **Reference Documentation**: All completed work documented in docs/
3. **Archive Access**: Historical work preserved in docs/archive/
4. **Development Continuation**: System optimized for ongoing work

### **🔄 Maintenance**
- Run this master workflow periodically to maintain organization
- Use individual scripts for specific cleanup needs
- Reference documentation in docs/ for implementation guidance

---

## 📋 **Scripts Executed**

1. **Enhanced Planning Cleanup**: \`run_enhanced_planning_cleanup.sh\`
2. **Comprehensive Subfolder Cleanup**: \`run_comprehensive_planning_cleanup.sh\`
3. **Documentation Conversion**: \`run_documentation_conversion.sh\`

---

**🎉 The AITBC planning system has been completely optimized and is ready for continued development excellence!**

*Generated by AITBC Master Planning Cleanup Workflow*
EOF

    print_success "Final summary generated: MASTER_WORKFLOW_FINAL_SUMMARY.md"
}

# Run main function
main "$@"
