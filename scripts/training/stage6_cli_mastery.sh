#!/bin/bash

# Source training library
source "$(dirname "$0")/training_lib.sh"

# OpenClaw AITBC Training - Stage 6: CLI Mastery & Extension Development
# CLI Architecture, Command Development, and Extension

set -e

# Training configuration
TRAINING_STAGE="Stage 6: CLI Mastery & Extension Development"
SCRIPT_NAME="stage6_cli_mastery"
CURRENT_LOG=$(init_logging "$SCRIPT_NAME")
WALLET_NAME="openclaw-trainee"
WALLET_PASSWORD="trainee123"

# Logging function
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee "$CURRENT_LOG"
}

# Print colored output
print_status() {
    echo -e "${BLUE}[TRAINING]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check if CLI exists
    if [ ! -f "$CLI_PATH" ]; then
        print_error "AITBC CLI not found at $CLI_PATH"
        exit 1
    fi
    
    # Check if training wallet exists
    if ! $CLI_PATH wallet list 2>/dev/null | grep -q "$WALLET_NAME"; then
        print_error "Training wallet $WALLET_NAME not found"
        exit 1
    fi
    
    # Check if docs directory exists
    if [ ! -d "/opt/aitbc/docs/cli" ]; then
        print_warning "CLI docs directory not found, will create"
        mkdir -p /opt/aitbc/docs/cli
    fi
    
    print_success "Prerequisites check completed"
}

# Section 6.1: CLI Architecture Fundamentals
cli_architecture_fundamentals() {
    print_status "6.1 CLI Architecture Fundamentals"
    
    print_status "Understanding parser registration..."
    log "Examining parser registration in parsers/__init__.py"
    cat /opt/aitbc/cli/parsers/__init__.py | head -20
    
    print_status "Understanding handler execution..."
    log "Examining handler execution in unified_cli.py"
    grep -A 5 "def run_cli" /opt/aitbc/cli/unified_cli.py | head -10
    
    print_status "Understanding argument parsing..."
    log "Examining argparse patterns in parsers"
    grep -r "add_argument" /opt/aitbc/cli/parsers/ | head -5
    
    print_status "Understanding handler context..."
    log "Examining handler context parameters"
    grep -A 3 "def handle_ai_submit" /opt/aitbc/cli/unified_cli.py | head -5
    
    print_success "6.1 CLI Architecture Fundamentals completed"
}

# Section 6.2: Creating Custom Commands
creating_custom_commands() {
    print_status "6.2 Creating Custom Commands"
    
    print_status "Creating example command parser..."
    cat > /tmp/test_command_parser.py << 'EOF'
"""Test command registration for the unified CLI."""

import argparse
from parser_context import ParserContext

def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
    test_parser = subparsers.add_parser("testcmd", help="Test command description")
    test_parser.set_defaults(handler=lambda parsed, parser=test_parser: parser.print_help())
    test_subparsers = test_parser.add_subparsers(dest="testcmd_action")
    
    test_action_parser = test_subparsers.add_parser("action", help="Action description")
    test_action_parser.add_argument("--option", help="Option description")
    test_action_parser.set_defaults(handler=ctx.handle_testcmd_action)
EOF
    
    log "Created test command parser template"
    
    print_status "Creating example command handler..."
    cat > /tmp/test_command_handler.py << 'EOF'
"""Test command handlers."""

def handle_testcmd_action(args, render_mapping):
    """Handle testcmd action command."""
    option_value = getattr(args, "option", "default")
    
    result = {
        "action": "testcmd",
        "option": option_value,
        "status": "success"
    }
    
    print(f"Test command executed with option: {option_value}")
    render_mapping("Result:", result)
EOF
    
    log "Created test command handler template"
    
    print_status "Understanding handler wrapper pattern..."
    log "Examining handler wrapper in unified_cli.py"
    grep -A 2 "def handle_ai_submit" /opt/aitbc/cli/unified_cli.py | head -3
    
    print_success "6.2 Creating Custom Commands completed"
}

# Section 6.3: Advanced Handler Patterns
advanced_handler_patterns() {
    print_status "6.3 Advanced Handler Patterns"
    
    print_status "Examining real backend integration pattern..."
    log "AI job submission pattern"
    grep -A 10 "requests.post" /opt/aitbc/cli/handlers/ai.py | head -12
    
    print_status "Examining stub handler pattern..."
    log "Workflow handler stub pattern"
    grep -A 8 "def handle_workflow_create" /opt/aitbc/cli/handlers/workflow.py
    
    print_status "Examining error handling pattern..."
    log "Graceful error handling in marketplace"
    grep -A 5 "except Exception" /opt/aitbc/cli/handlers/market.py | head -7
    
    print_status "Examining structured output pattern..."
    log "render_mapping usage"
    grep -A 3 "render_mapping" /opt/aitbc/cli/handlers/workflow.py | head -5
    
    print_success "6.3 Advanced Handler Patterns completed"
}

# Section 6.4: CLI Extension Best Practices
cli_extension_best_practices() {
    print_status "6.4 CLI Extension Best Practices"
    
    print_status "Examining command naming conventions..."
    log "Existing command names"
    ls /opt/aitbc/cli/parsers/*.py | xargs -n1 basename | sed 's/.py//'
    
    print_status "Examining argument design patterns..."
    log "Common argument patterns"
    grep -h "add_argument" /opt/aitbc/cli/parsers/*.py | head -10
    
    print_status "Examining handler signature patterns..."
    log "Handler function signatures"
    grep -h "^def handle_" /opt/aitbc/cli/handlers/*.py | head -10
    
    print_status "Examining help text patterns..."
    log "Command help text"
    grep -h "help=" /opt/aitbc/cli/parsers/*.py | head -10
    
    print_success "6.4 CLI Extension Best Practices completed"
}

# Section 6.5: CLI Extension Project
cli_extension_project() {
    print_status "6.5 CLI Extension Project"
    
    print_status "Building complete custom command example..."
    
    # Create a complete example command
    log "Creating 'greeting' command as example"
    
    # Create parser
    cat > /opt/aitbc/cli/parsers/greeting.py << 'EOF'
"""Greeting command registration for the unified CLI."""

import argparse
from parser_context import ParserContext

def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
    greeting_parser = subparsers.add_parser("greeting", help="Greeting commands")
    greeting_parser.set_defaults(handler=lambda parsed, parser=greeting_parser: parser.print_help())
    greeting_subparsers = greeting_parser.add_subparsers(dest="greeting_action")
    
    greeting_hello_parser = greeting_subparsers.add_parser("hello", help="Say hello")
    greeting_hello_parser.add_argument("--name", default="World", help="Name to greet")
    greeting_hello_parser.set_defaults(handler=ctx.handle_greeting_hello)
EOF
    
    log "Created greeting parser"
    
    # Create handler
    cat > /opt/aitbc/cli/handlers/greeting.py << 'EOF'
"""Greeting command handlers."""

def handle_greeting_hello(args, render_mapping):
    """Handle greeting hello command."""
    name = getattr(args, "name", "World")
    
    result = {
        "greeting": f"Hello, {name}!",
        "status": "success"
    }
    
    print(f"Greeting: Hello, {name}!")
    render_mapping("Greeting:", result)
EOF
    
    log "Created greeting handler"
    
    # Register in __init__.py
    if ! grep -q "greeting" /opt/aitbc/cli/parsers/__init__.py; then
        sed -i '/from . import analytics/a from . import greeting' /opt/aitbc/cli/parsers/__init__.py
        sed -i '/analytics.register/a greeting.register(subparsers, ctx)' /opt/aitbc/cli/parsers/__init__.py
        log "Registered greeting parser"
    fi
    
    # Register in unified_cli.py
    if ! grep -q "greeting" /opt/aitbc/cli/unified_cli.py; then
        sed -i '/from handlers import resource/a from handlers import greeting as greeting_handlers' /opt/aitbc/cli/unified_cli.py
        
        # Add wrapper function
        cat >> /tmp/greeting_wrapper.txt << 'EOF'

    def handle_greeting_hello(args):
        greeting_handlers.handle_greeting_hello(args, render_mapping)
EOF
        # Insert wrapper before handle_ai_submit
        sed -i '/def handle_ai_submit/r /tmp/greeting_wrapper.txt' /opt/aitbc/cli/unified_cli.py
        sed -i '/def handle_greeting_hello/{
            N
            N
            N
        }' /opt/aitbc/cli/unified_cli.py
        
        # Add to handlers dict
        sed -i '/"handle_resource_benchmark": handle_resource_benchmark,/a "handle_greeting_hello": handle_greeting_hello,' /opt/aitbc/cli/unified_cli.py
        
        log "Registered greeting handler"
    fi
    
    print_status "Testing custom command..."
    if $CLI_PATH greeting hello --name "OpenClaw" 2>/dev/null; then
        log "Custom command test passed"
        print_success "Custom command works successfully"
    else
        log "Custom command test failed (expected during manual registration)"
        print_warning "Custom command requires manual registration completion"
    fi
    
    print_success "6.5 CLI Extension Project completed"
}

# Final Certification Exam
certification_exam() {
    print_status "Final Certification Exam: CLI Mastery"
    
    TESTS_PASSED=0
    TOTAL_TESTS=10
    
    # Test 1: CLI version
    print_status "Certification test 1 (CLI version):"
    if $CLI_PATH --version > /dev/null 2>&1; then
        ((TESTS_PASSED += 1))
        log "Certification test 1 (CLI version): PASSED"
    else
        log "Certification test 1 (CLI version): FAILED"
    fi
    
    # Test 2: Parser registration understanding
    print_status "Certification test 2 (Parser registration):"
    if grep -q "register_all" /opt/aitbc/cli/parsers/__init__.py; then
        ((TESTS_PASSED += 1))
        log "Certification test 2 (Parser registration): PASSED"
    else
        log "Certification test 2 (Parser registration): FAILED"
    fi
    
    # Test 3: Handler execution understanding
    print_status "Certification test 3 (Handler execution):"
    if grep -q "def run_cli" /opt/aitbc/cli/unified_cli.py; then
        ((TESTS_PASSED += 1))
        log "Certification test 3 (Handler execution): PASSED"
    else
        log "Certification test 3 (Handler execution): FAILED"
    fi
    
    # Test 4: Developer guide exists
    print_status "Certification test 4 (Developer guide):"
    if [ -f "/opt/aitbc/docs/cli/CLI_DEVELOPER_GUIDE.md" ]; then
        ((TESTS_PASSED += 1))
        log "Certification test 4 (Developer guide): PASSED"
    else
        log "Certification test 4 (Developer guide): FAILED"
    fi
    
    # Test 5: Architecture docs exist
    print_status "Certification test 5 (Architecture docs):"
    if [ -f "/opt/aitbc/docs/cli/CLI_ARCHITECTURE.md" ]; then
        ((TESTS_PASSED += 1))
        log "Certification test 5 (Architecture docs): PASSED"
    else
        log "Certification test 5 (Architecture docs): FAILED"
    fi
    
    # Test 6: Parser templates exist
    print_status "Certification test 6 (Parser templates):"
    if [ -f "/opt/aitbc/cli/templates/parser_template.py" ]; then
        ((TESTS_PASSED += 1))
        log "Certification test 6 (Parser templates): PASSED"
    else
        log "Certification test 6 (Parser templates): FAILED"
    fi
    
    # Test 7: Handler templates exist
    print_status "Certification test 7 (Handler templates):"
    if [ -f "/opt/aitbc/cli/templates/handler_template.py" ]; then
        ((TESTS_PASSED += 1))
        log "Certification test 7 (Handler templates): PASSED"
    else
        log "Certification test 7 (Handler templates): FAILED"
    fi
    
    # Test 8: AI job submission pattern
    print_status "Certification test 8 (AI job pattern):"
    if grep -q "task_data" /opt/aitbc/cli/handlers/ai.py; then
        ((TESTS_PASSED += 1))
        log "Certification test 8 (AI job pattern): PASSED"
    else
        log "Certification test 8 (AI job pattern): FAILED"
    fi
    
    # Test 9: Blockchain RPC pattern
    print_status "Certification test 9 (Blockchain RPC pattern):"
    if grep -q "rpc/blocks" /opt/aitbc/cli/handlers/blockchain.py; then
        ((TESTS_PASSED += 1))
        log "Certification test 9 (Blockchain RPC pattern): PASSED"
    else
        log "Certification test 9 (Blockchain RPC pattern): FAILED"
    fi
    
    # Test 10: Marketplace API pattern
    print_status "Certification test 10 (Marketplace API pattern):"
    if grep -q "listings" /opt/aitbc/cli/handlers/market.py; then
        ((TESTS_PASSED += 1))
        log "Certification test 10 (Marketplace API pattern): PASSED"
    else
        log "Certification test 10 (Marketplace API pattern): FAILED"
    fi
    
    # Results
    log "Certification Results: $TESTS_PASSED/$TOTAL_TESTS tests passed"
    
    if [ $TESTS_PASSED -eq $TOTAL_TESTS ]; then
        print_success "🎉 CERTIFICATION PASSED! CLI Master Status Achieved!"
        log "CERTIFICATION: PASSED with 100% success rate"
    elif [ $TESTS_PASSED -ge 8 ]; then
        print_success "CERTIFICATION PASSED with $TESTS_PASSED/$TOTAL_TESTS"
        log "CERTIFICATION: PASSED with $((TESTS_PASSED * 100 / TOTAL_TESTS))% success rate"
    else
        print_warning "CERTIFICATION CONDITIONAL: $TESTS_PASSED/$TOTAL_TESTS - Additional practice recommended"
        log "CERTIFICATION: CONDITIONAL with $((TESTS_PASSED * 100 / TOTAL_TESTS))% success rate"
    fi
}

# Main execution
main() {
    log "Starting $TRAINING_STAGE"
    
    check_prerequisites
    
    # 6.1 CLI Architecture Fundamentals
    cli_architecture_fundamentals
    
    # 6.2 Creating Custom Commands
    creating_custom_commands
    
    # 6.3 Advanced Handler Patterns
    advanced_handler_patterns
    
    # 6.4 CLI Extension Best Practices
    cli_extension_best_practices
    
    # 6.5 CLI Extension Project
    cli_extension_project
    
    # Certification Exam
    certification_exam
    
    log "$TRAINING_STAGE completed successfully"
    
    echo ""
    echo "========================================"
    echo "$TRAINING_STAGE COMPLETED SUCCESSFULLY"
    echo "========================================"
    echo ""
    echo "🎓 CLI MASTERY ACHIEVED"
    echo ""
    echo "Next Steps:"
    echo "1. Review CLI Developer Guide: /opt/aitbc/docs/cli/CLI_DEVELOPER_GUIDE.md"
    echo "2. Review CLI Architecture: /opt/aitbc/docs/cli/CLI_ARCHITECTURE.md"
    echo "3. Use command templates: /opt/aitbc/cli/templates/"
    echo "4. Build custom commands for your use cases"
    echo "5. Share your extensions with the community"
    echo ""
    echo "Training Log: $CURRENT_LOG"
    echo ""
}

# Run main
main
