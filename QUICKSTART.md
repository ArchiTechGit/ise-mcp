# Cisco ISE MCP Server - Quick Start Guide

Get up and running in 5 minutes!

## What You Get

A complete Cisco ISE management system with:
- **MCP Server**: 1,007 operations across 33 ISE APIs — ERS, the 30 Open API specs (policy sets, TrustSec, certificates, deployment, …), Monitoring/MnT, and the API Service
- **Web API**: FastAPI REST backend with HTTPS
- **Web UI**: Next.js/React dashboard with authentication
- **PostgreSQL**: Database with encrypted credentials and audit logging
- **HTTPS**: Self-signed certificates auto-generated

## Quick Start

### Step 1: Clone and Configure

```bash
git clone https://github.com/ArchiTechGit/ise-mcp.git
cd ise-mcp

# Configure your server's IP address
echo "CERT_SERVER_IP=YOUR_SERVER_IP" > .env
```

Replace `YOUR_SERVER_IP` with your server's IP address (e.g., `192.168.1.213`).

If you need to use an existing Docker bridge network, add this to `.env`:

```bash
echo "DOCKER_EXTERNAL_NETWORK=openshell-cluster-nemoclaw" >> .env
```

Make sure that network already exists:

```bash
docker network create --driver bridge openshell-cluster-nemoclaw
```

### Step 2: Start Services

```bash
bash scripts/preflight-network.sh
docker compose up -d --build
```

Wait for all services to start (about 1-2 minutes on first run).

### Step 3: Access Web UI

1. Open browser: `https://YOUR_SERVER_IP:7447`
2. Accept the self-signed certificate warning
3. Create admin account:
   - Username: `admin`
   - Email: `admin@example.com`
   - Password: `Admin123!`

### Step 4: Add Your ISE Deployment

First, make sure ERS is enabled on the Primary PAN:
**Administration > System > Settings > API Settings > ERS Settings** -> enable **ERS (Read/Write)**,
and confirm your admin account is in the **ERS Admin** group.

1. Navigate to **ISE Deployments** page
2. Click **Add New Cluster**
3. Enter details:
   - Name: `my-ise-deployment`
   - URL: `https://ise.example.com:9060` (the ERS port is required - ERS does not answer on 443)
   - Username: `ersadmin`
   - Password: Your password
   - SSL Verification: Off (for self-signed certs)
4. Click **Test Connection** to verify
5. Click **Create Cluster**

### Step 5: Configure Claude Desktop

Add to your Claude Desktop config:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

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

Restart Claude Desktop and try: "List all network devices in my ISE deployment"

## Access Points

| Service | URL | Description |
|---------|-----|-------------|
| Web UI | `https://YOUR_SERVER_IP:7447` | Management dashboard |
| Web API | `https://YOUR_SERVER_IP:8448` | REST API |
| API Docs | `https://YOUR_SERVER_IP:8448/docs` | Swagger documentation |
| MCP SSE | `https://YOUR_SERVER_IP:8448/mcp/sse` | Claude Desktop endpoint |

## Common Commands

```bash
# Check status
docker compose ps

# View logs
docker compose logs -f

# Restart services
docker compose restart

# Stop everything
docker compose down

# Clean restart (keeps data)
docker compose down && docker compose up -d

# Full reset (WARNING: deletes all data!)
docker compose down -v
docker volume rm ise-mcp-certs
docker compose up -d --build
```

## Troubleshooting

### Can't access Web UI
```bash
# Check containers are running
docker compose ps

# Check for errors
docker compose logs ise_mcp_web_ui
docker compose logs ise_mcp_web_api
```

### Certificate issues
```bash
# Regenerate certificates
docker volume rm ise-mcp-certs
docker compose up -d
```

### Database issues
```bash
# Connect to database
docker compose exec ise_mcp_postgres psql -U mcp_user -d ise_mcp

# Check tables
\dt
```

## Next Steps

1. **Add more deployments**: Configure additional ISE deployments
2. **Set up users**: Add team members with role-based access
3. **Enable edit mode**: Allow write operations when needed
4. **Review audit logs**: Monitor all API operations
5. **Read the docs**: Check `docs/` folder for detailed guides

## Documentation

- [Deployment Guide](docs/DEPLOYMENT.md) - Production setup
- [Claude Desktop Setup](docs/CLAUDE_DESKTOP_SETUP.md) - MCP integration
- [Multi-User RBAC](docs/MULTI_USER_RBAC.md) - User management
- [API Guidance](docs/API_GUIDANCE_SYSTEM.md) - Customizing API behavior

---

**Ready to use!**
