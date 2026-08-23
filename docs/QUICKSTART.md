# Quick Start Guide

## 5-Minute Setup

### 1. Prerequisites

```bash
# Verify Docker is installed
docker --version
docker compose version
```

### 2. Clone and Configure

```bash
git clone https://github.com/ArchiTechGit/ise-mcp.git
cd ise-mcp

# Configure your server's IP address (required for SSL certificate)
echo "CERT_SERVER_IP=YOUR_SERVER_IP" > .env
```

Replace `YOUR_SERVER_IP` with your server's IP address (e.g., `192.168.1.213`).

If you're using a pre-existing Docker bridge network, set it in `.env`:

```bash
echo "DOCKER_EXTERNAL_NETWORK=openshell-cluster-nemoclaw" >> .env
```

Ensure that network already exists:

```bash
docker network create --driver bridge openshell-cluster-nemoclaw
```

### 3. Start Services

```bash
bash scripts/preflight-network.sh
docker compose up -d --build
```

Wait 1-2 minutes for all services to start. The first startup will:
- Generate self-signed SSL certificates
- Initialize the PostgreSQL database
- Start all services

### 4. Verify Deployment

```bash
# Check container status
docker compose ps

# View logs
docker compose logs -f

# Test API health
curl -k https://localhost:8448/api/health
```

### 5. Initial Setup

1. Open browser: `https://YOUR_SERVER_IP:7447`
2. Accept the self-signed certificate warning
3. Create admin account:
   - Username: `admin`
   - Email: `admin@example.com`
   - Password: `Admin123!`

### 6. Add Your Cluster

1. Navigate to **Clusters** page
2. Click **Add New Cluster**
3. Fill in details:
   - Name: `my-cluster`
   - URL: `https://ise.example.com:9060`
   - Username: `admin`
   - Password: Your password
   - SSL Verification: Off (for self-signed certs)
4. Click **Test Connection**
5. Click **Create Cluster**

## Using with Claude Desktop

### Configuration

Add to your Claude Desktop config file:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
**Linux:** `~/.config/Claude/claude_desktop_config.json`

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

Replace `YOUR_SERVER_IP` with your server's IP address.

### Restart and Test

1. Restart Claude Desktop
2. Look for MCP icon showing "ise" connected
3. Try: "List all network devices in my ISE deployment"

## Example Queries

### Read-Only Operations (Always Allowed)

```
"Show me all network devices in my ISE deployment"

"What does ISE know about the endpoint with MAC 00:11:22:33:44:55?"

"List the TrustSec security group tags"

"Show inventory of all devices"
```

### Write Operations (Requires Edit Mode)

Enable edit mode in Web UI > Security, then:

```
"Onboard a new network device called 'branch-sw-01' at 10.1.1.1"

"Update the description of the network device 'branch-sw-01'"

"Delete the network device 'decommissioned-sw'"
```

## Access Points

| Service | URL | Description |
|---------|-----|-------------|
| Web UI | `https://YOUR_SERVER_IP:7447` | Management dashboard |
| Web API | `https://YOUR_SERVER_IP:8448` | REST API |
| API Docs | `https://YOUR_SERVER_IP:8448/docs` | Swagger UI |
| MCP SSE | `https://YOUR_SERVER_IP:8448/mcp/sse` | Claude endpoint |
| PostgreSQL | `localhost:15436` | Database |

## Troubleshooting

### Container Won't Start

```bash
# Check status
docker compose ps

# View logs
docker compose logs ise_mcp_web_api
docker compose logs ise_mcp_web_ui

# Restart
docker compose down && docker compose up -d
```

### Certificate Issues

```bash
# Regenerate certificates
docker volume rm ise-mcp-certs
docker compose up -d
```

### Authentication Failures

```bash
# Test Cisco ISE connection manually
curl -k -X POST https://ise.example.com:9060/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"yourpass"}'
```

### Database Issues

```bash
# Connect to database
docker compose exec ise_mcp_postgres psql -U mcp_user -d ise_mcp

# Full reset (WARNING: deletes all data!)
docker compose down -v
docker compose up -d --build
```

## Common Commands

```bash
# Start services
docker compose up -d

# Stop services
docker compose down

# View logs
docker compose logs -f

# Restart a service
docker compose restart ise_mcp_web_ui

# Rebuild and restart
docker compose up -d --build

# Clean up unused images
docker image prune -f
```

## Security Reminders

- Keep `EDIT_MODE_ENABLED=false` unless actively making changes
- Change default admin password after first login
- Protect your `.env` file (never commit to git)
- Review audit logs regularly in Web UI

## Next Steps

1. **Read documentation**: Check `docs/DEPLOYMENT.md` for production setup
2. **Configure users**: Add team members with roles in Web UI
3. **Explore APIs**: Use Claude to discover available operations
4. **Monitor**: Review audit logs for operation history

## Getting Help

- Issues: https://github.com/ArchiTechGit/ise-mcp/issues
- Documentation: `docs/` directory
- Troubleshooting: `docs/DEPLOYMENT.md#troubleshooting`

Happy automating!
