# Cisco ISE MCP Server

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](docker-compose.yml)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](requirements.txt)
[![Next.js](https://img.shields.io/badge/Next.js-16.0-black?logo=next.js&logoColor=white)](web-ui/package.json)

A comprehensive Model Context Protocol (MCP) server for Cisco Identity Services Engine (ISE), enabling AI agents like Claude to interact with the ISE External RESTful Services (ERS) API for intelligent network access control, identity, and TrustSec automation.

## Features

### Core Capabilities
- **Complete API Coverage**: Access to **1,007 operations across 33 ISE APIs** — 395 in ERS (by resource family below), 590 across the 30 Open API specs, 20 in Monitoring (MnT), and 2 in the API Service
  - Network (58 operations): Network access devices, device groups, RADIUS and TACACS+ servers and sequences
  - Identity (74 operations): Internal users, identity groups, endpoints, endpoint groups, profiling, REST ID stores
  - Policy (40 operations): Authorization profiles, downloadable ACLs, allowed protocols, certificate profiles
  - TrustSec (69 operations): SGTs, SGACLs, egress matrix, SG mappings, SXP bindings, CTS queries
  - Guest (90 operations): Guest users and types, sponsor groups, and the guest, sponsor, hotspot, BYOD and self-registration portals
  - Threat (11 operations): ANC policies and endpoint containment actions
  - Deployment (53 operations): Nodes, certificates, Active Directory, LDAP, pxGrid, support bundles

  And beyond ERS:
  - **Open API** (30 specs, 590 operations): policy sets and authorization rules, TrustSec
    classification policy, certificates, deployment, upgrade, backup, licensing, alarms,
    webhooks, pxGrid, and more
  - **Monitoring / MnT** (20 operations): active sessions, posture and profiler counts,
    session lookup by MAC, IP or username — the only live-state API here
  - **API Service** (2 operations): enables or disables the Open API

  > **Tool profiles matter at this scale.** 1,007 tools is well beyond what an MCP
  > client surfaces (typically 40–128). There is one profile per category, and the
  > Administrator role bypasses filtering entirely — see
  > [docs/AVAILABLE_OPERATIONS.md](docs/AVAILABLE_OPERATIONS.md#tool-profiles).

- **Security First**:
  - HTTPS with self-signed certificates (auto-generated)
  - Multi-user authentication with role-based access control (RBAC)
  - Read-only mode by default with explicit edit mode enablement
  - Fernet-encrypted credential storage
  - Complete audit logging with client IP tracking
  - Granular operation whitelisting per role

- **Web Management UI**:
  - Next.js-based management interface with HTTPS
  - User and role management
  - Real-time system health monitoring
  - Audit log viewer with CSV export
  - ISE deployment management with connection testing
  - Security configuration dashboard
  - API guidance and workflow management

- **Enterprise Ready**:
  - PostgreSQL database for persistence
  - Docker-based deployment on an external bridge network
  - Complete audit trail for compliance
  - LDAP integration support

## Quick Start

### Prerequisites

- **Docker** 20.10+ and Docker Compose 2.0+
- **Cisco ISE** 3.1+ with the ERS service enabled
  - Administration > System > Settings > API Settings > ERS Settings -> enable **ERS (Read/Write)** on the Primary PAN
  - An admin account in the **ERS Admin** group (read/write) or **ERS Operator** group (read-only)
- **Node.js** 18+ (for remote MCP access via mcp-remote)

### 1. Clone and Configure

```bash
git clone https://github.com/ArchiTechGit/ise-mcp.git
cd ise-mcp

# Create environment file with your server's IP address
echo "CERT_SERVER_IP=YOUR_SERVER_IP" > .env
```

Replace `YOUR_SERVER_IP` with your server's actual IP address (e.g., `192.168.1.213`).

### 2. Start Services

```bash
bash scripts/preflight-network.sh
docker compose up -d --build
```

This will:
- Generate self-signed SSL certificates automatically
- Start PostgreSQL database (port 15436)
- Start Web API with HTTPS (port 8448)
- Start Web UI with HTTPS (port 7447)
- Start MCP Server for Claude integration

### 3. Initial Setup

1. Open your browser and navigate to:
   ```
   https://YOUR_SERVER_IP:7447
   ```

2. Accept the self-signed certificate warning

3. Complete the initial admin setup:
   - Username: `admin`
   - Email: `admin@example.com`
   - Password: `Admin123!` (or your preferred password)

4. Configure your first ISE deployment:
   - Navigate to **ISE Deployments** page
   - Click "Add New Cluster"
   - Enter the Primary PAN URL **including the ERS port**, e.g. `https://ise.example.com:9060`
   - Enter the ERS admin username and password
   - Click "Test Connection" to verify
   - Save the deployment configuration

### 4. Configure Claude Desktop

Add to your Claude Desktop configuration:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
**Linux:** `~/.config/Claude/claude_desktop_config.json`

#### Remote Deployment (Recommended)

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

> **Note:** Since we use self-signed certificates, you may need to set `NODE_TLS_REJECT_UNAUTHORIZED=0` in your environment or accept the certificate in your system's trust store.

#### Local Deployment (same machine as Docker)

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

Restart Claude Desktop, and you'll see the ISE tools available!

## Architecture

```
                      External Clients
                  (Browser, Claude Desktop)
                           |
                    [HTTPS/TLS]
                           |
           +---------------+---------------+
           |                               |
      Port 7447                       Port 8448
           |                               |
+----------+----------+    +---------------+--------------+
|       Web UI        |    |           Web API            |
|      (Next.js)      |--->|          (FastAPI)           |
|      HTTPS Proxy    |    |  +----------+  +---------+   |
+---------------------+    |  | REST API |  | MCP SSE |   |
                           |  +----------+  +---------+   |
                           +---------------+--------------+
                                           |
                    +----------------------+----------------------+
                    |                      |                      |
           +--------+--------+    +--------+--------+    +--------+--------+
           |   PostgreSQL    |    |   MCP Server    |    |   Cisco ISE     |
           |   Port 15436    |    |   (stdio)       |    |  Deployments    |
           +-----------------+    +-----------------+    +-----------------+

Certificate Volume: /app/certs/ (auto-generated on first startup)
```

## Port Summary

| Service | Port | Protocol | Description |
|---------|------|----------|-------------|
| Web UI | 7447 | HTTPS | Management interface |
| Web API | 8448 | HTTPS | REST API and MCP SSE endpoint |
| PostgreSQL | 15436 | TCP | Database (mapped from 5432) |
| Internal HTTP | 7104 | HTTP | Internal proxy communication |

These defaults are unique per stack so several of these MCP servers can run side by side on one host
(nexus=7443/8444, catalyst=7444/8445, fmc=7445/8446, vcenter=7446/8447, ise=7447/8448).

### Cisco ISE ports

| Port | Purpose | Setting |
|------|---------|---------|
| 9060 | ERS API - every operation except TrustSec (CTS) | from `ISE_HOST_URL` |
| 9063 | TrustSec (CTS) operations under `/ctsapi/` | `ISE_CTS_PORT` |
| 443  | API gateway - Open API (`/api/v1/`), API Service and MnT (`/admin/API/`) | `ISE_ADMIN_PORT` |

Set `ISE_HOST_URL` to the Primary PAN including `:9060`. Requests to the other families are re-pointed
automatically; set the corresponding setting to `0` if a proxy serves them on one port.

## Environment Variables

### Required for Production

Create a `.env` file with:

```env
# Your server's IP address (for SSL certificate SAN)
CERT_SERVER_IP=192.168.1.213

# Security (generate unique keys for production)
ENCRYPTION_KEY=your-unique-fernet-key
SESSION_SECRET_KEY=your-random-secret-key

# External Docker network (must already exist)
DOCKER_EXTERNAL_NETWORK=openshell-cluster-nemoclaw

# Required by Web UI runtime proxy target
# Docker Compose sets this to http://ise_mcp_web_api:7104 by default
BACKEND_API_URL=http://ise_mcp_web_api:7104

# Optional: Cisco ISE defaults (can be configured via Web UI)
# The URL must include the ERS port - ERS does not answer on 443
ISE_HOST_URL=https://ise.example.com:9060
ISE_USERNAME=ersadmin
ISE_PASSWORD=YourPassword
ISE_CTS_PORT=9063
ISE_ADMIN_PORT=443
```

**Generate Encryption Key:**
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Optional Variables

```env
# SSL Certificate Configuration
CERT_DAYS=365                    # Certificate validity (default: 365)
CERT_CN=ise-mcp                  # Certificate common name

# Security
EDIT_MODE_ENABLED=false          # Enable write operations
MCP_API_TOKEN=your-token         # Optional: Require token for MCP access

# Logging
LOG_LEVEL=INFO                   # DEBUG, INFO, WARNING, ERROR
```

## Security

### HTTPS Configuration

Self-signed certificates are automatically generated on first startup:
- Stored in Docker volume `ise-mcp-certs`
- Valid for 365 days (configurable via `CERT_DAYS`)
- Includes localhost, 127.0.0.1, and your server IP in SAN

To regenerate certificates:
```bash
docker volume rm ise-mcp-certs
docker compose up -d
```

### Multi-User RBAC

The platform supports multiple users with role-based access control:

- **Admin Role**: Full access to all operations
- **Operator Role**: Read access + specific write operations
- **Viewer Role**: Read-only access

Users can be managed through the Web UI under **Security > Users**.

### Best Practices

1. **Change default admin password** after initial setup
2. **Keep `EDIT_MODE_ENABLED=false`** unless write operations are needed
3. **Use strong encryption keys** for production
4. **Review audit logs** regularly for unauthorized activity
5. **Limit network access** to the server

## Documentation

- **[Quick Start Guide](QUICKSTART.md)** - Get up and running in 5 minutes
- **[Architecture Overview](docs/ARCHITECTURE.md)** - System design and components
- **[User Guide](docs/USER_GUIDE.md)** - Comprehensive usage documentation
- **[Web UI Guide](docs/WEB_UI_GUIDE.md)** - Managing the system via web interface
- **[Claude Desktop Setup](docs/CLAUDE_DESKTOP_SETUP.md)** - Detailed Claude integration
- **[Deployment Guide](docs/DEPLOYMENT.md)** - Production deployment recommendations
- **[Multi-User RBAC](docs/MULTI_USER_RBAC.md)** - Role-based access control
- **[API Guidance System](docs/API_GUIDANCE_SYSTEM.md)** - Customizing API behavior

## Troubleshooting

### Check Container Status
```bash
docker compose ps
docker compose logs -f
```

### Certificate Issues
```bash
# View certificate details
docker compose exec ise_mcp_web_api openssl x509 -in /app/certs/server.crt -text -noout

# Regenerate certificates
docker volume rm ise-mcp-certs
docker compose up -d
```

### Database Issues
```bash
# Connect to database
docker compose exec ise_mcp_postgres psql -U mcp_user -d ise_mcp

# Check tables
\dt

# View audit logs
SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 10;
```

### Network Connectivity
```bash
# Test API endpoint
curl -k https://localhost:8448/api/health

# Test Web UI
curl -k https://localhost:7447
```

## Development

### Local Development Setup

```bash
# Clone repository
git clone https://github.com/ArchiTechGit/ise-mcp.git
cd ise-mcp

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start database only
docker compose up postgres -d

# Run API locally
python src/api/web_api.py

# Run Web UI in dev mode
cd web-ui
npm install
npm run dev
```

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- **Anthropic** - For the Claude AI platform and MCP protocol
- **Cisco** - For the Identity Services Engine ERS API
- **FastMCP** - For the excellent MCP framework

---

**Made with care for network automation**
