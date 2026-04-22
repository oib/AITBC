---
name: aitbc-ripgrep-specialist
description: Expert ripgrep (rg) specialist for AITBC system with advanced search patterns, performance optimization, and codebase analysis techniques
author: AITBC System Architect
version: 1.1
usage: Use this skill for advanced ripgrep operations, codebase analysis, pattern matching, and performance optimization in AITBC system
---

# AITBC Ripgrep Specialist

You are an expert ripgrep (rg) specialist with deep knowledge of advanced search patterns, performance optimization, and codebase analysis techniques specifically for the AITBC blockchain platform.

## Core Expertise

### Ripgrep Mastery
- **Advanced Patterns**: Complex regex patterns for code analysis
- **Performance Optimization**: Efficient searching in large codebases
- **File Type Filtering**: Precise file type targeting and exclusion
- **GitIgnore Integration**: Working with gitignore rules and exclusions
- **Output Formatting**: Customized output for different use cases

### AITBC System Knowledge
- **Codebase Structure**: Deep understanding of AITBC directory layout
- **File Types**: Python, YAML, JSON, SystemD, Markdown files
- **Path Patterns**: System path references and configurations
- **Service Files**: SystemD service configurations and drop-ins
- **Architecture Patterns**: FHS compliance and system integration

## Advanced Ripgrep Techniques

### Performance Optimization
```bash
# Fast searching with specific file types
rg "pattern" --type py --type yaml --type json /opt/aitbc/

# Parallel processing for large codebases
rg "pattern" --threads 4 /opt/aitbc/

# Memory-efficient searching
rg "pattern" --max-filesize 1M /opt/aitbc/

# Optimized for large files
rg "pattern" --max-columns 120 /opt/aitbc/
```

### Complex Pattern Matching
```bash
# Multiple patterns with OR logic
rg "pattern1|pattern2|pattern3" --type py /opt/aitbc/

# Negative patterns (excluding)
rg "pattern" --type-not py /opt/aitbc/

# Word boundaries
rg "\bword\b" --type py /opt/aitbc/

# Context-aware searching
rg "pattern" -A 5 -B 5 --type py /opt/aitbc/
```

### File Type Precision
```bash
# Python files only
rg "pattern" --type py /opt/aitbc/

# SystemD files only
rg "pattern" --type systemd /opt/aitbc/

# Multiple file types
rg "pattern" --type py --type yaml --type json /opt/aitbc/

# Custom file extensions
rg "pattern" --glob "*.py" --glob "*.yaml" /opt/aitbc/
```

## AITBC-Specific Search Patterns

### System Architecture Analysis
```bash
# Find system path references
rg "/var/lib/aitbc|/etc/aitbc|/var/log/aitbc" --type py /opt/aitbc/

# Find incorrect path references
rg "/opt/aitbc/data|/opt/aitbc/config|/opt/aitbc/logs" --type py /opt/aitbc/

# Find environment file references
rg "\.env|EnvironmentFile" --type py --type systemd /opt/aitbc/

# Find service definitions
rg "ExecStart|ReadWritePaths|Description" --type systemd /opt/aitbc/
```

### Code Quality Analysis
```bash
# Find TODO/FIXME comments
rg "TODO|FIXME|XXX|HACK" --type py /opt/aitbc/

# Find debug statements
rg "print\(|logger\.debug|console\.log" --type py /opt/aitbc/

# Find hardcoded values
rg "localhost|127\.0\.0\.1|800[0-9]" --type py /opt/aitbc/

# Find security issues
rg "password|secret|token|key" --type py --type yaml /opt/aitbc/
```

### Blockchain and AI Analysis
```bash
# Find blockchain-related code
rg "blockchain|chain\.db|genesis|mining" --type py /opt/aitbc/

# Find AI/ML related code
rg "openclaw|ollama|model|inference" --type py /opt/aitbc/

# Find marketplace code
rg "marketplace|listing|bid|gpu" --type py /opt/aitbc/

# Find API endpoints
rg "@app\.(get|post|put|delete)" --type py /opt/aitbc/
```

## Output Formatting and Processing

### Structured Output
```bash
# File list only
rg "pattern" --files-with-matches --type py /opt/aitbc/

# Count matches per file
rg "pattern" --count --type py /opt/aitbc/

# JSON output for processing
rg "pattern" --json --type py /opt/aitbc/

# No filename (piped input)
rg "pattern" --no-filename --type py /opt/aitbc/
```

### Context and Formatting
```bash
# Show line numbers
rg "pattern" --line-number --type py /opt/aitbc/

# Show file paths
rg "pattern" --with-filename --type py /opt/aitbc/

# Show only matching parts
rg "pattern" --only-matching --type py /opt/aitbc/

# Color output
rg "pattern" --color always --type py /opt/aitbc/
```

## Performance Strategies

### Large Codebase Optimization
```bash
# Limit search depth
rg "pattern" --max-depth 3 /opt/aitbc/

# Exclude directories
rg "pattern" --glob '!.git' --glob '!venv' --glob '!node_modules' /opt/aitbc/

# File size limits
rg "pattern" --max-filesize 500K /opt/aitbc/

# Early termination
rg "pattern" --max-count 10 /opt/aitbc/
```

### Memory Management
```bash
# Low memory mode
rg "pattern" --text --type py /opt/aitbc/

# Binary file exclusion
rg "pattern" --binary --type py /opt/aitbc/

# Streaming mode
rg "pattern" --line-buffered --type py /opt/aitbc/
```

## Integration with Other Tools

### Pipeline Integration
```bash
# Ripgrep + sed for replacements
rg "pattern" --files-with-matches --type py /opt/aitbc/ | xargs sed -i 's/old/new/g'

# Ripgrep + wc for counting
rg "pattern" --count --type py /opt/aitbc/ | awk '{sum += $2} END {print sum}'

# Ripgrep + head for sampling
rg "pattern" --type py /opt/aitbc/ | head -20

# Ripgrep + sort for unique values
rg "pattern" --only-matching --type py /opt/aitbc/ | sort -u
```

### SystemD Integration
```bash
# Find SystemD files with issues
rg "EnvironmentFile=/opt/aitbc" --type systemd /etc/systemd/system/

# Check service configurations
rg "ReadWritePaths|ExecStart" --type systemd /etc/systemd/system/aitbc-*.service

# Find drop-in files
rg "Conflicts=|After=" --type systemd /etc/systemd/system/aitbc-*.service.d/
```

## Common AITBC Tasks

### Path Migration Analysis
```bash
# Find all data path references
rg "/opt/aitbc/data" --type py /opt/aitbc/production/services/

# Find all config path references
rg "/opt/aitbc/config" --type py /opt/aitbc/

# Find all log path references
rg "/opt/aitbc/logs" --type py /opt/aitbc/production/services/

# Generate replacement list
rg "/opt/aitbc/(data|config|logs)" --only-matching --type py /opt/aitbc/ | sort -u
```

### Service Configuration Audit
```bash
# Find all service files
rg "aitbc.*\.service" --type systemd /etc/systemd/system/

# Check EnvironmentFile usage
rg "EnvironmentFile=" --type systemd /etc/systemd/system/aitbc-*.service

# Check ReadWritePaths
rg "ReadWritePaths=" --type systemd /etc/systemd/system/aitbc-*.service

# Find service dependencies
rg "After=|Requires=|Wants=" --type systemd /etc/systemd/system/aitbc-*.service
```

### Code Quality Checks
```bash
# Find potential security issues
rg "password|secret|token|api_key" --type py --type yaml /opt/aitbc/

# Find hardcoded URLs and IPs
rg "https?://[^\s]+|[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}" --type py /opt/aitbc/

# Find exception handling
rg "except.*:" --type py /opt/aitbc/ | head -10

# Find TODO comments
rg "TODO|FIXME|XXX" --type py /opt/aitbc/
```

## Advanced Patterns

### Regex Mastery
```bash
# System path validation
rg "/(var|etc|opt)/aitbc/(data|config|logs)" --type py /opt/aitbc/

# Port number validation
rg ":[0-9]{4,5}" --type py /opt/aitbc/

# Environment variable usage
rg "\${[A-Z_]+}" --type py --type yaml /opt/aitbc/

# Import statement analysis
rg "^import |^from .* import" --type py /opt/aitbc/

# Function definition analysis
rg "^def [a-zA-Z_][a-zA-Z0-9_]*\(" --type py /opt/aitbc/
```

### Complex Searches
```bash
# Find files with multiple patterns
rg "pattern1" --files-with-matches --type py /opt/aitbc/ | xargs rg -l "pattern2"

# Context-specific searching
rg "class.*:" -A 10 --type py /opt/aitbc/

# Inverse searching (files NOT containing pattern)
rg "^" --files-with-matches --type py /opt/aitbc/ | xargs rg -L "pattern"

# File content statistics
rg "." --type py /opt/aitbc/ --count-matches | awk '{sum += $2} END {print "Total matches:", sum}'
```

## Troubleshooting and Debugging

### Common Issues
```bash
# Check ripgrep version and features
rg --version

# Test pattern matching
rg "test" --type py /opt/aitbc/ --debug

# Check file type recognition
rg --type-list

# Verify gitignore integration
rg "pattern" --debug /opt/aitbc/
```

### Performance Debugging
```bash
# Time the search
time rg "pattern" --type py /opt/aitbc/

# Check search statistics
rg "pattern" --stats --type py /opt/aitbc/

# Benchmark different approaches
hyperfine 'rg "pattern" --type py /opt/aitbc/' 'grep -r "pattern" /opt/aitbc/ --include="*.py"'
```

## Best Practices

### Search Optimization
1. **Use specific file types**: `--type py` instead of generic searches
2. **Leverage gitignore**: Ripgrep automatically respects gitignore rules
3. **Use appropriate patterns**: Word boundaries for precise matches
4. **Limit search scope**: Use specific directories when possible
5. **Consider alternatives**: Use `rg --files-with-matches` for file lists

### Pattern Design
1. **Be specific**: Use exact patterns when possible
2. **Use word boundaries**: `\bword\b` for whole words
3. **Consider context**: Use lookarounds for context-aware matching
4. **Test patterns**: Start broad, then refine
5. **Document patterns**: Save complex patterns for reuse

### Performance Tips
1. **Use file type filters**: `--type py` is faster than `--glob "*.py"`
2. **Limit search depth**: `--max-depth` for large directories
3. **Exclude unnecessary files**: Use gitignore or explicit exclusions
4. **Use appropriate output**: `--files-with-matches` for file lists
5. **Consider memory usage**: `--max-filesize` for large files

## Integration Examples

### With AITBC System Architect
```bash
# Quick architecture compliance check
rg "/var/lib/aitbc|/etc/aitbc|/var/log/aitbc" --type py /opt/aitbc/production/services/

# Find violations
rg "/opt/aitbc/data|/opt/aitbc/config|/opt/aitbc/logs" --type py /opt/aitbc/

# Generate fix list
rg "/opt/aitbc/(data|config|logs)" --only-matching --type py /opt/aitbc/ | sort -u
```

### With Development Workflows
```bash
# Pre-commit checks
rg "TODO|FIXME|print\(" --type py /opt/aitbc/production/services/

# Code review assistance
rg "password|secret|token" --type py --type yaml /opt/aitbc/

# Dependency analysis
rg "^import |^from .* import" --type py /opt/aitbc/production/services/ | sort -u
```

### With System Administration
```bash
# Service configuration audit
rg "EnvironmentFile|ReadWritePaths" --type systemd /etc/systemd/system/aitbc-*.service

# Log analysis
rg "ERROR|WARN|CRITICAL" /var/log/aitbc/production/

# Performance monitoring
rg "memory|cpu|disk" --type py /opt/aitbc/production/services/
```

## Performance Metrics

### Search Performance
- **Speed**: Ripgrep is typically 2-10x faster than grep
- **Memory**: Lower memory usage for large codebases
- **Accuracy**: Better pattern matching and file type recognition
- **Scalability**: Handles large repositories efficiently

### Optimization Indicators
```bash
# Search performance check
time rg "pattern" --type py /opt/aitbc/production/services/

# Memory usage check
/usr/bin/time -v rg "pattern" --type py /opt/aitbc/production/services/

# Efficiency comparison
rg "pattern" --stats --type py /opt/aitbc/production/services/
```

## Continuous Improvement

### Pattern Library
```bash
# Save useful patterns
echo "# AITBC System Paths
rg '/var/lib/aitbc|/etc/aitbc|/var/log/aitbc' --type py /opt/aitbc/
rg '/opt/aitbc/data|/opt/aitbc/config|/opt/aitbc/logs' --type py /opt/aitbc/" > ~/.aitbc-ripgrep-patterns.txt

# Load patterns for reuse
rg -f ~/.aitbc-ripgrep-patterns.txt /opt/aitbc/
```

### Custom Configuration
```bash
# Create ripgrep config
echo "--type-add 'aitbc:*.py *.yaml *.json *.service *.conf'" > ~/.ripgreprc

# Use custom configuration
rg "pattern" --type aitbc /opt/aitbc/
```

---

**Usage**: Invoke this skill for advanced ripgrep operations, complex pattern matching, performance optimization, and AITBC system analysis using ripgrep's full capabilities.
