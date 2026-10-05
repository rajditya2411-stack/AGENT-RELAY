"""
AgentRelay v2.0 — Unified Command Line Interface (CLI)
Entrypoint for starting the gateway, running the desktop bridge, managing the vault, and verifying audit logs.
"""

import argparse
import asyncio
import os
import sys
import uvicorn

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from agentrelay import __version__


def main():
    parser = argparse.ArgumentParser(
        prog="agentrelay",
        description="⚡ AgentRelay v2.0 — Universal Operating System for Personal Autonomous Agents",
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: start
    start_parser = subparsers.add_parser("start", help="Start the AgentRelay Gateway Server")
    start_parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    start_parser.add_argument("--port", type=int, default=58765, help="Port to listen on (default: 58765)")
    start_parser.add_argument("--reload", action="store_true", help="Enable auto-reload for local development")
    start_parser.add_argument("--mode", choices=["ALL", "DEV_SHIELD", "FRONTIER_AGENT"], default="ALL", help="Initial operational mode filter")

    # Command: bridge
    bridge_parser = subparsers.add_parser("bridge", help="Run the local Desktop Bridge PTY process")
    bridge_parser.add_argument("--relay", default="ws://localhost:58765/ws/bridge", help="Relay server WebSocket URL")
    bridge_parser.add_argument("--device", default="my-pc", help="Unique device identifier")
    bridge_parser.add_argument("--token", default="default_secret", help="Pairing secret token")

    # Command: audit
    audit_parser = subparsers.add_parser("audit", help="Audit ledger commands")
    audit_sub = audit_parser.add_subparsers(dest="audit_command", help="Audit subcommands")
    audit_sub.add_parser("verify", help="Verify cryptographic chain and tamper-evident signatures")
    audit_export = audit_sub.add_parser("export", help="Export compliance JSON bundle")
    audit_export.add_argument("--output", default="compliance_bundle.json", help="Destination file path")

    # Command: vault
    vault_parser = subparsers.add_parser("vault", help="Encrypted BYOK vault commands")
    vault_parser.add_argument("--passphrase", default="agentrelay_master_passphrase", help="Master passphrase for vault")
    vault_sub = vault_parser.add_subparsers(dest="vault_command", help="Vault subcommands")
    vault_sub.add_parser("status", help="Show vault lock status and configured providers")
    vault_set = vault_sub.add_parser("set", help="Store or rotate a provider API key")
    vault_set.add_argument("provider", help="Provider name (xai, openai, anthropic, meta_graph)")
    vault_set.add_argument("key", help="API key string")
    vault_sub.add_parser("wipe", help="Emergency wipe of all credentials")

    args = parser.parse_args()

    if args.command == "start":
        print(f"⚡ Starting AgentRelay v2.0 Gateway on http://{args.host}:{args.port}")
        from agentrelay.server.app import create_app
        app = create_app()
        uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)

    elif args.command == "bridge":
        import subprocess
        bridge_script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bridge.py")
        cmd = [sys.executable, bridge_script, "--relay", args.relay, "--device", args.device, "--token", args.token]
        sys.exit(subprocess.call(cmd))

    elif args.command == "audit":
        from agentrelay.server.audit_logger import AuditLogger
        logger = AuditLogger()
        if args.audit_command == "verify":
            valid, reason = logger.verify_integrity()
            if valid:
                print(f"✅ Cryptographic chain verified intact! Total entries: {len(logger.entries)} (Algorithm: {logger.signing_algorithm})")
                sys.exit(0)
            else:
                print(f"❌ Verification failed: {reason}")
                sys.exit(1)
        elif args.audit_command == "export":
            logger.export_compliance_bundle(output_path=args.output)
            print(f"📜 Exported compliance bundle to {args.output}")

    elif args.command == "vault":
        from agentrelay.server.vault import Vault
        vault = Vault(passphrase=args.passphrase)
        if args.vault_command == "status":
            print(f"Vault Path: {vault.vault_path}")
            print(f"Unlocked: {vault.is_unlocked}")
            print(f"Configured Providers: {', '.join(vault.list_configured_providers()) or 'None'}")
        elif args.vault_command == "set":
            vault.set_key(args.provider, args.key)
            print(f"✅ Stored encrypted key for '{args.provider}'.")
        elif args.vault_command == "wipe":
            vault.wipe_all()
            print("🚨 All vault credentials wiped.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
