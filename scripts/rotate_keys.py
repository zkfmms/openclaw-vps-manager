#!/usr/bin/env python3
"""SSH key rotation script."""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import AsyncSessionLocal
from sqlalchemy import select, update
from services.ssh_manager import SSHKeyManager
from config import get_settings
import paramiko


async def rotate_all_ssh_keys():
    """Rotate SSH keys for all VPS servers."""
    settings = get_settings()

    print("Starting SSH key rotation...")

    async with AsyncSessionLocal() as db:
        # Get all VPS servers
        from database import VPSServer
        result = await db.execute(select(VPSServer))
        vps_list = result.scalars().all()

        print(f"Found {len(vps_list)} VPS servers to update")

        ssh_key_manager = SSHKeyManager()

        for vps in vps_list:
            print(f"\nRotating key for VPS {vps.id} ({vps.hostname})...")

            try:
                # Backup old key
                old_key_path = Path(vps.ssh_key_path)
                if old_key_path.exists():
                    backup_path = Path(str(old_key_path) + ".backup")
                    old_key_path.rename(backup_path)
                    print(f"  Backed up old key to {backup_path}")

                # Generate new key pair
                private_key_path, public_key_path = ssh_key_manager.generate_keypair(
                    key_type=settings.ssh_key_type,
                    passphrase=settings.ssh_key_passphrase,
                )

                # Read public key content
                public_key_content = public_key_path.read_text()

                # Rename keys to use VPS ID
                new_private_key_path = settings.get_ssh_key_path(vps.id)
                new_public_key_path = Path(str(new_private_key_path) + ".pub")

                private_key_path.rename(new_private_key_path)
                public_key_path.rename(new_public_key_path)

                print(f"  Generated new key pair")
                print(f"  Public key: {public_key_content}")

                # Update VPS record
                vps.ssh_key_path = str(new_private_key_path)
                await db.commit()

                print(f"  Updated VPS {vps.id} successfully")

            except Exception as e:
                print(f"  Error rotating key for VPS {vps.id}: {e}")
                # Restore backup if it exists
                backup_path = Path(vps.ssh_key_path + ".backup")
                if backup_path.exists():
                    backup_path.rename(vps.ssh_key_path)
                    print(f"  Restored backup key")

        print("\nSSH key rotation complete!")
        print("\nNext steps:")
        print("1. Update authorized_keys files on all VPS servers with new public keys")
        print("2. Test SSH connectivity")
        print("3. Remove .backup files once verified")


async def rotate_single_vps_key(vps_id: int):
    """Rotate SSH key for a specific VPS."""
    settings = get_settings()

    print(f"Rotating SSH key for VPS {vps_id}...")

    async with AsyncSessionLocal() as db:
        from database import VPSServer
        result = await db.execute(select(VPSServer).where(VPSServer.id == vps_id))
        vps = result.scalar_one_or_none()

        if not vps:
            print(f"VPS {vps_id} not found")
            return

        ssh_key_manager = SSHKeyManager()

        try:
            # Backup old key
            old_key_path = Path(vps.ssh_key_path)
            if old_key_path.exists():
                backup_path = Path(str(old_key_path) + ".backup")
                old_key_path.rename(backup_path)
                print(f"Backed up old key to {backup_path}")

            # Generate new key pair
            private_key_path, public_key_path = ssh_key_manager.generate_keypair(
                key_type=settings.ssh_key_type,
                passphrase=settings.ssh_key_passphrase,
            )

            # Read public key content
            public_key_content = public_key_path.read_text()

            # Rename keys to use VPS ID
            new_private_key_path = settings.get_ssh_key_path(vps.id)
            new_public_key_path = Path(str(new_private_key_path) + ".pub")

            private_key_path.rename(new_private_key_path)
            public_key_path.rename(new_public_key_path)

            print(f"Generated new key pair")
            print(f"\nPublic key to add to authorized_keys:")
            print(public_key_content)

            # Update VPS record
            vps.ssh_key_path = str(new_private_key_path)
            await db.commit()

            print(f"\nUpdated VPS {vps.id} successfully")

        except Exception as e:
            print(f"Error rotating key for VPS {vps_id}: {e}")
            # Restore backup if it exists
            backup_path = Path(vps.ssh_key_path + ".backup")
            if backup_path.exists():
                backup_path.rename(vps.ssh_key_path)
                print("Restored backup key")


async def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description="Rotate SSH keys for VPS Manager")
    parser.add_argument(
        "--vps-id",
        type=int,
        help="Rotate key for specific VPS ID only",
    )
    args = parser.parse_args()

    if args.vps_id:
        await rotate_single_vps_key(args.vps_id)
    else:
        await rotate_all_ssh_keys()


if __name__ == "__main__":
    asyncio.run(main())
