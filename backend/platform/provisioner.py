"""
Provisioning engine for Stuttgart KI Profis.
Automatically creates customer directories, configs, and price tables,
then launches the agent server instance.

Each customer gets:
  - A directory under agent/customers/<customer_id>/
  - config.yaml with their business data
  - price_table.yaml with standard services
  - A dedicated port on the agent server (or shared multi-tenant mode)
"""

import os
import sys
import signal
import yaml
import subprocess
import logging
from pathlib import Path

from . import database as db

log = logging.getLogger("hk-provisioner")

# Paths
AGENT_DIR = Path(__file__).parent.parent  # agent/
CUSTOMERS_DIR = AGENT_DIR / "customers"
TEMPLATES_DIR = AGENT_DIR / "templates"
VENV_PYTHON = AGENT_DIR.parent / "agent-venv" / "bin" / "python"


def provision_customer(customer_id: str) -> dict:
    """
    Full provisioning pipeline for a new customer:
    1. Create customer directory with config.yaml and price_table.yaml
    2. Mark status as 'provisioning' in DB
    3. Find free port and start agent instance
    4. Mark status as 'active' in DB
    5. Return instance details

    Returns dict with status, port, customer_dir, message.
    """
    # Get customer from database
    customer = db.get_customer_by_customer_id(customer_id)
    if not customer:
        return {"status": "error", "message": f"Customer '{customer_id}' not found"}

    db.update_customer(customer["id"], status="provisioning")

    # Check if already provisioned
    existing_instance = db.get_instance_by_customer(customer["id"])
    if existing_instance and existing_instance.get("status") == "running":
        log.info(f"Customer {customer_id} already provisioned, skipping config creation")
        db.update_customer(customer["id"], status="active")
        return {
            "status": "active",
            "port": existing_instance["port"],
            "customer_id": customer_id,
            "instance_id": existing_instance["id"],
            "message": f"Agent for {customer['company_name']} already running",
        }

    try:
        # 1. Create customer directory
        cust_dir = CUSTOMERS_DIR / customer_id
        cust_dir.mkdir(parents=True, exist_ok=True)

        # 2. Write company config
        config = {
            "company": {
                "name": customer["company_name"],
                "strasse": customer["street"],
                "plz_ort": customer["zip_city"],
                "tel": customer["phone"],
                "mail": customer["email"],
                "steuer": customer["vat_id"] or "",
                "geschaeftsfuehrer": "",
            },
            "whatsapp": {
                "number": customer["whatsapp_number"] or "",
            },
            "colors": {
                "primary": [25, 60, 120],
                "secondary": [100, 100, 100],
            },
            "logo_path": "",
            "defaults": {
                "zahlungsziel_tage": 14,
                "gueltig_bis_tage": 30,
            },
        }

        with open(cust_dir / "config.yaml", "w") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

        # 3. Write price table (from template or minimal)
        pt_data = {
            "hourly_rate": customer["hourly_rate"],
            "materials_markup": 1.15,
            "standard_services": [
                {"description": "Arbeitsstunde", "price": customer["hourly_rate"], "unit": "h"},
                {"description": "Anfahrt pauschal (Stadtgebiet)", "price": 35.00, "unit": "pauschal"},
                {"description": "Kleinmaterialpauschale", "price": 25.00, "unit": "pauschal"},
            ],
        }

        # Copy template price table if available
        template_path = TEMPLATES_DIR / "price_table.yaml"
        if template_path.exists():
            with open(template_path) as f:
                template_data = yaml.safe_load(f)
                if template_data:
                    template_data["hourly_rate"] = customer["hourly_rate"]
                    pt_data = template_data

        with open(cust_dir / "price_table.yaml", "w") as f:
            yaml.dump(pt_data, f, default_flow_style=False, allow_unicode=True)

        log.info(f"Customer directory created: {cust_dir}")

        # 4. Create instance record
        port = db.find_next_free_port(9000)
        instance = db.create_instance(customer["id"])
        config_path = str(cust_dir)
        db.update_instance(instance["id"], port=port, config_path=config_path)

        # 5. Would start the agent process here in production
        # For now, mark as active since the shared server handles all customers
        # In production: start a systemd service or Docker container
        _setup_systemd_service(customer_id, port, customer)

        db.update_instance(instance["id"], status="running", whatsapp_connected=0)
        db.update_customer(customer["id"], status="active")

        return {
            "status": "active",
            "port": port,
            "customer_id": customer_id,
            "customer_dir": str(cust_dir),
            "instance_id": instance["id"],
            "message": f"Agent for {customer['company_name']} is ready",
        }

    except Exception as e:
        log.error(f"Provisioning failed for {customer_id}: {e}")
        db.update_customer(customer["id"], status="error")
        return {"status": "error", "message": str(e)}


def _setup_systemd_service(customer_id: str, port: int, customer: dict):
    """
    Create a systemd service file for a dedicated agent instance.
    In production, this runs the Flask webhook server on a dedicated port.
    For the MVP, we use the shared multi-tenant server with AGENT_CUSTOMER env.

    For the initial launch, we rely on the existing shared server.py which
    already handles multi-tenant routing via resolve_customer().
    """
    # For MVP: the shared server handles all customers.
    # For dedicated instances (Enterprise plan), we'd create:
    #
    # [Unit]
    # Description=Stuttgart KI Profis Agent - {customer_id}
    # After=network.target
    #
    # [Service]
    # Type=simple
    # User=root
    # WorkingDirectory={AGENT_DIR.parent}
    # Environment=AGENT_CUSTOMER={customer_id}
    # Environment=TWILIO_ACCOUNT_SID=...
    # Environment=TWILIO_AUTH_TOKEN=...
    # Environment=OPENROUTER_API_KEY=...
    # ExecStart={VENV_PYTHON} -m agent.server --port {port}
    # Restart=always
    # RestartSec=10
    #
    # [Install]
    # WantedBy=multi-user.target
    pass


def teardown_customer(customer_id: str) -> dict:
    """Remove a customer's agent instance and config."""
    customer = db.get_customer_by_customer_id(customer_id)
    if not customer:
        return {"status": "error", "message": "Customer not found"}

    # Kill process if running
    instance = db.get_instance_by_customer(customer["id"])
    if instance and instance.get("pid"):
        try:
            os.kill(instance["pid"], signal.SIGTERM)
        except ProcessLookupError:
            pass

    db.update_customer(customer["id"], status="suspended")
    if instance:
        db.update_instance(instance["id"], status="stopped")

    return {"status": "ok", "message": f"Customer {customer_id} deactivated"}


def list_active_instances() -> list[dict]:
    """List all active customer instances with status."""
    conn = db.get_conn()
    try:
        rows = conn.execute("""
            SELECT c.customer_id, c.company_name, c.plan, c.status,
                   i.port, i.status as instance_status, i.whatsapp_connected,
                   i.last_seen, i.created_at
            FROM customers c
            LEFT JOIN instances i ON i.customer_id = c.id
            ORDER BY c.created_at DESC
        """).fetchall()
        return rows
    finally:
        conn.close()


def deploy_dedicated_instance(customer_id: str) -> dict:
    """
    Deploy a dedicated systemd service for a customer.
    Each customer gets their own agent server on a dedicated port.
    Only for Enterprise plan customers.

    The service:
    - Runs the Flask webhook on a dedicated port
    - Sets AGENT_CUSTOMER to this customer
    - Auto-restarts on failure
    - Is isolated from other customers
    """
    customer = db.get_customer_by_customer_id(customer_id)
    if not customer:
        return {"status": "error", "message": f"Customer '{customer_id}' not found"}

    # First ensure customer is provisioned (configs exist)
    if customer["status"] != "active":
        prov_result = provision_customer(customer_id)
        if prov_result.get("status") == "error":
            return prov_result
        customer = db.get_customer_by_customer_id(customer_id)

    inst = db.get_instance_by_customer(customer["id"])
    port = inst["port"] if inst else db.find_next_free_port(9000)

    service_name = f"hk-agent-{customer_id}"
    service_path = Path(f"/etc/systemd/system/{service_name}.service")

    python_path = VENV_PYTHON
    working_dir = AGENT_DIR.parent
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    twilio_token = os.environ.get("TWILIO_AUTH_TOKEN", "")

    service_content = f"""\
[Unit]
Description=Stuttgart KI Profis Agent - {customer['company_name']} ({customer_id})
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={working_dir}
Environment=AGENT_CUSTOMER={customer_id}
Environment=OPENROUTER_API_KEY={api_key}
Environment=TWILIO_ACCOUNT_SID={twilio_sid}
Environment=TWILIO_AUTH_TOKEN={twilio_token}
ExecStart={python_path} -m agent.server --port {port}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""

    try:
        import subprocess
        subprocess.run(["sudo", "tee", str(service_path)], input=service_content,
                       text=True, check=True, capture_output=True)
        subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True, capture_output=True)
        subprocess.run(["sudo", "systemctl", "enable", service_name], check=True, capture_output=True)
        subprocess.run(["sudo", "systemctl", "start", service_name], check=True, capture_output=True)

        # Update instance record
        if inst:
            db.update_instance(inst["id"], port=port, status="running", pid=0)
        db.update_customer(customer["id"], status="active")

        log.info(f"Dedicated instance deployed for {customer_id} on port {port}")

        return {
            "status": "active",
            "port": port,
            "service_name": service_name,
            "customer_id": customer_id,
            "message": f"Dedicated agent service '{service_name}' deployed on port {port}",
        }

    except subprocess.CalledProcessError as e:
        log.error(f"Failed to deploy systemd service: {e.stderr}")
        return {"status": "error", "message": f"Deployment failed: {e.stderr}"}
    except Exception as e:
        log.error(f"Deploy error: {e}")
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    """CLI: provision a customer directly."""
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        print("Usage: python -m agent.platform.provisioner <customer_id>")
        sys.exit(1)
    result = provision_customer(sys.argv[1])
    print(f"Result: {result}")