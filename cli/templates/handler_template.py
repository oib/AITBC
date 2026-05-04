"""{{COMMAND_NAME}} command handlers."""

def handle_{{COMMAND_NAME}}_action(args, render_mapping):
    """Handle {{COMMAND_NAME}} action command."""
    option_value = getattr(args, "option", "default")
    
    result = {
        "action": "{{COMMAND_NAME}}",
        "option": option_value,
        "status": "success",
        "timestamp": __import__('datetime').datetime.now().isoformat()
    }
    
    print(f"{{COMMAND_NAME}} executed with option: {option_value}")
    render_mapping("Result:", result)
