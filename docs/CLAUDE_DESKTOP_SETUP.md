# Claude Desktop Integration Guide

## Overview

This guide explains how to connect Claude Desktop to the Cisco ISE MCP Server, enabling Claude to interact with your Cisco ISE infrastructure.

## Prerequisites

- Cisco ISE MCP Server deployed and running
- Claude Desktop installed
- For remote connections: Node.js 18+ installed locally

## Quick Setup

### Remote Connection (Recommended)

For accessing the MCP server running on a remote host:

**Step 1:** Locate your Claude Desktop configuration file:

| OS | Path |
|----|------|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

**Step 2:** Add the MCP server configuration:

```json
{
  "mcpServers": {
    "ise": {
      "command": "npx",
      "args": [
        "mcp-remote@latest",
        "https://YOUR_SERVER_IP:8448/mcp/sse",
        "--transport",
        "sse-only"
      ]
    }
  }
}
```

Replace `YOUR_SERVER_IP` with your server's IP address (e.g., `192.168.1.213`).

**Step 3:** Restart Claude Desktop

- macOS: Cmd+Q to quit, then relaunch
- Windows: Close and reopen the application
- Linux: Close and reopen the application

### Local Connection

For Claude Desktop running on the same machine as Docker:

```json
{
  "mcpServers": {
    "ise": {
      "command": "docker",
      "args": [
        "exec",
        "-i",
        "ise_mcp_mcp_server",
        "python",
        "src/main.py"
      ]
    }
  }
}
```

## Handling Self-Signed Certificates

Since the MCP server uses self-signed certificates, you may encounter SSL/TLS errors.

### Option 1: Accept Self-Signed Certificates (Development)

Set the environment variable before running Claude Desktop:

**macOS/Linux:**
```bash
export NODE_TLS_REJECT_UNAUTHORIZED=0
open -a "Claude"
```

**Windows (PowerShell):**
```powershell
$env:NODE_TLS_REJECT_UNAUTHORIZED=0
& "C:\Path\To\Claude.exe"
```

### Option 2: Add Certificate to Trust Store (Production)

1. Download the server certificate:
   ```bash
   openssl s_client -connect YOUR_SERVER_IP:8448 -showcerts </dev/null 2>/dev/null | \
     openssl x509 -outform PEM > ise-mcp.crt
   ```

2. Add to your system's trust store:
   - **macOS:** Double-click the .crt file and add to Keychain Access
   - **Windows:** Right-click > Install Certificate
   - **Linux:** Copy to `/usr/local/share/ca-certificates/` and run `update-ca-certificates`

## Verifying the Connection

After restarting Claude Desktop:

1. Look for the MCP server indicator (hammer icon) in Claude Desktop
2. You should see "ise" listed as an available server
3. The indicator should show a green status

### Test Query

Try asking Claude:

```
"List all network devices in my ISE deployment"
```

or

```
"Show me the nodes in my ISE deployment"
```

## Available Operations

### Read Operations (Always Available)

- List and inspect network access devices and device groups
- Look up internal users, identity groups, and endpoints
- Read authorization profiles, dACLs, and allowed protocol services
- Review TrustSec SGTs, SGACLs, and the egress matrix
- Query guest accounts, sponsor groups, and portals
- Inspect deployment nodes, certificates, and Active Directory join points

### Write Operations (Requires Edit Mode)

Write operations are disabled by default. To enable:

1. Go to Web UI: `https://YOUR_SERVER_IP:7447`
2. Navigate to **Security** page
3. Enable **Edit Mode**
4. Optionally whitelist specific operations

Once enabled, you can:
- Onboard, update, and delete network access devices
- Create and manage internal users, identity groups, and endpoints
- Edit authorization profiles, dACLs, and allowed protocols
- Change TrustSec SGTs, SGACLs, and matrix cells
- Manage the guest account lifecycle
- Apply and clear ANC containment actions

## Secure Access with API Token

For additional security, you can require an API token:

**Step 1:** Set the token in your deployment's `.env` file:

```env
MCP_API_TOKEN=your-secure-token-here
```

**Step 2:** Restart the services:

```bash
docker compose down
docker compose up -d
```

**Step 3:** Update Claude Desktop configuration:

```json
{
  "mcpServers": {
    "ise": {
      "command": "npx",
      "args": [
        "mcp-remote@latest",
        "https://YOUR_SERVER_IP:8448/mcp/sse",
        "--transport",
        "sse-only",
        "--header",
        "Authorization: Bearer your-secure-token-here"
      ]
    }
  }
}
```

## Troubleshooting

### Server Not Showing Up

1. **Check Docker containers are running:**
   ```bash
   docker compose ps
   ```

2. **Check server logs:**
   ```bash
   docker compose logs -f ise_mcp_mcp_server
   ```

3. **Verify Claude Desktop config syntax:**
   ```bash
   cat ~/Library/Application\ Support/Claude/claude_desktop_config.json | python -m json.tool
   ```

4. **Test the SSE endpoint:**
   ```bash
   curl -k https://YOUR_SERVER_IP:8448/mcp/sse
   ```

### Permission Errors

- Check edit mode setting in Web UI
- Verify your user has appropriate role assignments
- Review audit logs: `https://YOUR_SERVER_IP:7447/audit`

### Connection Errors

1. **Test network connectivity:**
   ```bash
   curl -k https://YOUR_SERVER_IP:8448/api/health
   ```

2. **Check firewall rules:**
   - Port 8448 must be accessible

3. **Verify SSL certificate:**
   ```bash
   openssl s_client -connect YOUR_SERVER_IP:8448 -servername YOUR_SERVER_IP
   ```

### SSL/Certificate Errors

If you see "self-signed certificate" or "unable to verify" errors:

1. Use `NODE_TLS_REJECT_UNAUTHORIZED=0` for development
2. Add the certificate to your system trust store for production
3. Or use proper CA-signed certificates

## Monitoring Usage

### View Real-Time Logs

```bash
docker compose logs -f ise_mcp_mcp_server
```

### Audit Log Access

All MCP operations are logged. View them at:
- Web UI: `https://YOUR_SERVER_IP:7447/audit`
- Database:
  ```bash
  docker compose exec ise_mcp_postgres psql -U mcp_user -d ise_mcp -c \
    "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 20;"
  ```

## Example Queries

### Read-Only Examples

```
"Show me all network devices configured in ISE"

"What does ISE know about the endpoint with MAC 00:11:22:33:44:55?"

"List every network device whose name contains 'branch'"

"Get the configuration of the network device 'branch-sw-01'"

"Show me the TrustSec egress matrix"

"Which nodes are in my ISE deployment and what personas do they run?"
```

### Write Mode Examples (After Enabling)

```
"Onboard a new network device called 'branch-sw-01' at 10.1.1.1"

"Add the endpoint 00:11:22:33:44:55 to the Blocked_List identity group"

"Quarantine the endpoint 00:11:22:33:44:55 using the ANC policy 'Quarantine'"
```

## Best Practices

1. **Start Read-Only:** Test queries before enabling write mode
2. **Use Specific Queries:** Include device names, MAC addresses, and UUIDs
3. **Monitor Logs:** Keep `docker compose logs -f` running during testing
4. **Review Audit:** Check audit logs after operations
5. **Limit Access:** Use API tokens in shared environments
