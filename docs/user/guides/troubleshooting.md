# Troubleshooting Guide

Common issues and solutions when using the AITBC network.

## Job Issues

### Job Stuck in "Pending" State

**Symptoms**: Job submitted but stays in `pending` for a long time.

**Causes**:
- No miners currently available
- Network congestion
- Model not supported by available miners

**Solutions**:
1. Wait a few minutes - miners may become available
2. Check network status at [Explorer](https://aitbc.bubuit.net/explorer/)
3. Try a different model (e.g., `llama3.2:1b` instead of `llama3.2`)
4. Cancel and resubmit during off-peak hours

```bash
# Check job status
./aitbc-cli.sh status <job_id>

# Cancel if needed
./aitbc-cli.sh cancel <job_id>
```

### Job Failed

**Symptoms**: Job status shows `failed` with an error message.

**Common Errors**:

| Error | Cause | Solution |
|-------|-------|----------|
| `Model not found` | Invalid model name | Check available models |
| `Prompt too long` | Input exceeds limit | Shorten your prompt |
| `Timeout` | Job took too long | Reduce `max_tokens` or simplify prompt |
| `Miner disconnected` | Miner went offline | Resubmit job |
| `Insufficient balance` | Not enough AITBC | Top up your balance |

### Unexpected Output

**Symptoms**: Job completed but output is wrong or truncated.

**Solutions**:
1. **Truncated output**: Increase `max_tokens` parameter
2. **Wrong format**: Be more specific in your prompt
3. **Gibberish**: Lower `temperature` (try 0.3-0.5)
4. **Off-topic**: Rephrase prompt to be clearer

## Connection Issues

### Cannot Connect to API

**Symptoms**: `Connection refused` or `timeout` errors.

**Solutions**:
1. Check your internet connection
2. Verify API URL: `https://aitbc.bubuit.net/api`
3. Check if service is up at [Explorer](https://aitbc.bubuit.net/explorer/)
4. Try again in a few minutes

```bash
# Test connectivity
curl -I https://aitbc.bubuit.net/api/health
```

### Authentication Failed

**Symptoms**: `401 Unauthorized` or `Invalid API key` errors.

**Solutions**:
1. Verify your API key is correct
2. Check if API key has expired
3. Ensure API key has required permissions
4. Generate a new API key if needed

## Wallet Issues

### Cannot Connect Wallet

**Symptoms**: Wallet connection fails or times out.

**Solutions**:
1. Ensure browser extension is installed and unlocked
2. Refresh the page and try again
3. Check if wallet is on correct network
4. Clear browser cache and cookies

### Transaction Not Showing

**Symptoms**: Sent tokens but balance not updated.

**Solutions**:
1. Wait for confirmation (may take a few minutes)
2. Check transaction in Explorer
3. Verify you sent to correct address
4. Contact support if still missing after 1 hour

### Insufficient Balance

**Symptoms**: `Insufficient balance` error when submitting job.

**Solutions**:
1. Check your current balance
2. Top up via [Exchange](https://aitbc.bubuit.net/Exchange/)
3. Wait for pending deposits to confirm

## CLI Issues

### Command Not Found

**Symptoms**: `aitbc-cli.sh: command not found`

**Solutions**:
```bash
# Make script executable
chmod +x aitbc-cli.sh

# Run with explicit path
./aitbc-cli.sh status

# Or add to PATH
export PATH=$PATH:$(pwd)
```

### Permission Denied

**Symptoms**: `Permission denied` when running CLI.

**Solutions**:
```bash
chmod +x aitbc-cli.sh
```

### SSL Certificate Error

**Symptoms**: `SSL certificate problem` or `certificate verify failed`

**Solutions**:
```bash
# Update CA certificates
sudo apt update && sudo apt install ca-certificates

# Or skip verification (not recommended for production)
curl -k https://aitbc.bubuit.net/api/health
```

## Performance Issues

### Slow Response Times

**Symptoms**: Jobs take longer than expected.

**Causes**:
- Large prompt or output
- Complex model
- Network congestion
- Miner hardware limitations

**Solutions**:
1. Use smaller models for simple tasks
2. Reduce `max_tokens` if full output not needed
3. Submit during off-peak hours
4. Use streaming for faster first-token response

### Rate Limited

**Symptoms**: `429 Too Many Requests` error.

**Solutions**:
1. Wait before retrying (check `Retry-After` header)
2. Reduce request frequency
3. Use exponential backoff in your code
4. Request higher rate limits if needed

## Getting Help

### Self-Service Resources

- **Documentation**: [https://aitbc.bubuit.net/docs/](https://aitbc.bubuit.net/docs/)
- **API Reference**: [https://aitbc.bubuit.net/api/docs](https://aitbc.bubuit.net/api/docs)
- **Explorer**: [https://aitbc.bubuit.net/explorer/](https://aitbc.bubuit.net/explorer/)

### Reporting Issues

When reporting an issue, include:
1. **Job ID** (if applicable)
2. **Error message** (exact text)
3. **Steps to reproduce**
4. **Expected vs actual behavior**
5. **Timestamp** of when issue occurred

### Debug Mode

Enable verbose logging for troubleshooting:

```bash
# CLI debug mode
DEBUG=1 ./aitbc-cli.sh submit "test"

# Python SDK
import logging
logging.basicConfig(level=logging.DEBUG)
```
