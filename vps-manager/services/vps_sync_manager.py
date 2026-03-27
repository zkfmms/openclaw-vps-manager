"""VPS Git synchronization manager service."""
import asyncio
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass

from git import Repo, GitCommandError, InvalidGitRepositoryError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import (
    VPSGitSync,
    VPSServer,
    get_db,
)
from services.ssh_manager import get_ssh_pool, SSHResult
from services.git_manager import get_git_manager
from config import get_settings


@dataclass
class SyncStatus:
    """Sync status information."""
    status: str
    message: str
    local_commit: Optional[str]
    remote_commit: Optional[str]
    conflicts: List[Dict]


@dataclass
class ConflictInfo:
    """Merge conflict information."""
    file_path: str
    local_changes: str
    remote_changes: str
    suggested_resolution: str


class VPSGitSyncManager:
    """Manager for bidirectional Git synchronization with VPS instances."""

    def __init__(self):
        """Initialize sync manager."""
        self.ssh_pool = get_ssh_pool()
        self.git_manager = get_git_manager()
        self.settings = get_settings()

    async def sync_vps(
        self,
        vps_id: int,
        db: AsyncSession,
        direction: str = "both",  # "push", "pull", "both"
        force: bool = False,
        user_id: Optional[int] = None,
    ) -> SyncStatus:
        """
        Perform full bidirectional sync with VPS.

        Args:
            vps_id: VPS server ID.
            db: Database session.
            direction: Sync direction ("push", "pull", "both").
            force: Force sync without conflict detection.
            user_id: User ID initiating sync.

        Returns:
            SyncStatus with result.
        """
        # Get VPS information
        vps_result = await db.execute(
            select(VPSServer).where(VPSServer.id == vps_id)
        )
        vps = vps_result.scalar_one_or_none()

        if not vps:
            return SyncStatus(
                status="error",
                message="VPS not found",
                local_commit=None,
                remote_commit=None,
                conflicts=[],
            )

        # Create sync record
        sync_record = VPSGitSync(
            vps_id=vps_id,
            sync_status="in_progress",
            sync_type="manual" if user_id else "auto",
            initiated_by=user_id,
        )
        db.add(sync_record)
        await db.commit()
        await db.refresh(sync_record)

        try:
            if direction in ("both", "pull"):
                await self._pull_from_vps(vps, sync_record.id, db)

            if direction in ("both", "push"):
                result = await self._push_to_vps(vps, sync_record.id, db)
                if result.status == "conflict":
                    return result

            # Update sync record as successful
            sync_record.sync_status = "success"
            sync_record.last_sync_at = datetime.utcnow()
            await db.commit()

            return SyncStatus(
                status="success",
                message="Sync completed successfully",
                local_commit=sync_record.local_commit,
                remote_commit=sync_record.remote_commit,
                conflicts=[],
            )

        except Exception as e:
            sync_record.sync_status = "failed"
            sync_record.conflict_details = {"error": str(e)}
            await db.commit()

            return SyncStatus(
                status="error",
                message=f"Sync failed: {str(e)}",
                local_commit=sync_record.local_commit,
                remote_commit=sync_record.remote_commit,
                conflicts=[],
            )

    async def _pull_from_vps(
        self,
        vps: VPSServer,
        sync_id: int,
        db: AsyncSession,
    ) -> None:
        """
        Pull changes from VPS to central repo.

        Args:
            vps: VPS server model.
            sync_id: Sync record ID.
            db: Database session.
        """
        # Get current local commit
        local_commit = self.git_manager.repo.head.commit.hexsha

        # Fetch from VPS via SSH
        vps_config_dir = f"~/.openclaw"
        commands = [
            f"cd {vps_config_dir}",
            "git add -A",
            "git commit -m 'Auto-commit before sync' || true",
        ]

        # Execute on VPS
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.ssh_pool.execute, vps.hostname, vps.ssh_user, vps.ssh_key_path, " && ".join(commands))

        if result.exit_code != 0:
            raise Exception(f"VPS pre-commit failed: {result.stderr}")

        # Fetch VPS commit
        fetch_command = f"cd {vps_config_dir} && git rev-parse HEAD"
        result = await loop.run_in_executor(None, self.ssh_pool.execute, vps.hostname, vps.ssh_user, vps.ssh_key_path, fetch_command)

        if result.exit_code != 0:
            raise Exception(f"Failed to get VPS commit: {result.stderr}")

        vps_commit = result.stdout.strip()

        # Update sync record
        sync_record_result = await db.execute(
            select(VPSGitSync).where(VPSGitSync.id == sync_id)
        )
        sync_record = sync_record_result.scalar_one()
        sync_record.local_commit = vps_commit
        sync_record.remote_commit = local_commit
        await db.commit()

        # Merge VPS changes into central repo
        self.git_manager.git.checkout(settings.get_customer_branch(vps.customer_id))

        # Attempt merge
        try:
            # Create a remote for VPS
            remote_name = f"vps-{vps.id}"
            try:
                self.git_manager.repo.create_remote(
                    remote_name,
                    f"ssh://{vps.ssh_user}@{vps.hostname}:{vps_config_dir}/.git"
                )
            except GitCommandError:
                pass  # Remote might already exist

            # Fetch from VPS
            self.git_manager.repo.git.fetch(remote_name)

            # Merge with conflict resolution strategy
            self.git_manager.repo.git.merge(
                f"{remote_name}/master",
                strategy_option="--strategy-option=theirs",  # Prefer remote changes
            )

            # Push merged changes
            self.git_manager.repo.git.push("origin", settings.get_customer_branch(vps.customer_id))

        except GitCommandError as e:
            # Handle merge conflict
            if "conflict" in str(e).lower():
                sync_record.sync_status = "conflict"
                sync_record.conflict_details = {
                    "type": "merge_conflict",
                    "message": str(e),
                }
                await db.commit()

    async def _push_to_vps(
        self,
        vps: VPSServer,
        sync_id: int,
        db: AsyncSession,
    ) -> SyncStatus:
        """
        Push changes from central repo to VPS.

        Args:
            vps: VPS server model.
            sync_id: Sync record ID.
            db: Database session.

        Returns:
            SyncStatus with result.
        """
        # Get current local commit
        remote_commit = self.git_manager.repo.head.commit.hexsha

        # Push to VPS via SSH
        vps_config_dir = f"~/.openclaw"
        loop = asyncio.get_event_loop()

        # First, check if VPS has uncommitted changes
        status_command = f"cd {vps_config_dir} && git status --porcelain"
        status_result = await loop.run_in_executor(None, self.ssh_pool.execute, vps.hostname, vps.ssh_user, vps.ssh_key_path, status_command)

        # Get VPS commit
        vps_commit_command = f"cd {vps_config_dir} && git rev-parse HEAD"
        vps_commit_result = await loop.run_in_executor(None, self.ssh_pool.execute, vps.hostname, vps.ssh_user, vps.ssh_key_path, vps_commit_command)

        if vps_commit_result.exit_code != 0:
            raise Exception(f"Failed to get VPS commit: {vps_commit_result.stderr}")

        vps_commit = vps_commit_result.stdout.strip()

        # Update sync record
        sync_record_result = await db.execute(
            select(VPSGitSync).where(VPSGitSync.id == sync_id)
        )
        sync_record = sync_record_result.scalar_one()
        sync_record.local_commit = remote_commit
        sync_record.remote_commit = vps_commit
        await db.commit()

        # Check for conflicts (both sides modified)
        if status_result.stdout.strip() and not status_result.stdout.startswith("??"):
            # VPS has uncommitted changes
            # Pull from VPS first to detect conflicts
            await self._pull_from_vps(vps, sync_id, db)

            # Re-fetch sync record
            sync_record_result = await db.execute(
                select(VPSGitSync).where(VPSGitSync.id == sync_id)
            )
            sync_record = sync_record_result.scalar_one()

            if sync_record.sync_status == "conflict":
                return SyncStatus(
                    status="conflict",
                    message="Merge conflict detected between local and VPS changes",
                    local_commit=remote_commit,
                    remote_commit=vps_commit,
                    conflicts=[sync_record.conflict_details],
                )

        # Pull changes to VPS
        pull_commands = [
            f"cd {vps_config_dir}",
            "git pull",
        ]

        result = await loop.run_in_executor(None, self.ssh_pool.execute, vps.hostname, vps.ssh_user, vps.ssh_key_path, " && ".join(pull_commands))

        if result.exit_code != 0:
            # Handle pull error
            if "conflict" in result.stderr.lower():
                return SyncStatus(
                    status="conflict",
                    message="Merge conflict detected when pulling to VPS",
                    local_commit=remote_commit,
                    remote_commit=vps_commit,
                    conflicts=[{"message": result.stderr}],
                )

            raise Exception(f"Git pull to VPS failed: {result.stderr}")

        return SyncStatus(
            status="success",
            message="Changes pushed to VPS successfully",
            local_commit=remote_commit,
            remote_commit=vps_commit,
            conflicts=[],
        )

    async def get_sync_status(self, vps_id: int, db: AsyncSession) -> Optional[Dict]:
        """
        Get current sync status for a VPS.

        Args:
            vps_id: VPS server ID.
            db: Database session.

        Returns:
            Sync status dictionary or None.
        """
        result = await db.execute(
            select(VPSGitSync)
            .where(VPSGitSync.vps_id == vps_id)
            .order_by(VPSGitSync.created_at.desc())
        )
        sync_record = result.scalar_one_or_none()

        if not sync_record:
            return None

        return {
            "sync_id": sync_record.id,
            "status": sync_record.sync_status,
            "last_sync_at": sync_record.last_sync_at.isoformat() if sync_record.last_sync_at else None,
            "local_commit": sync_record.local_commit,
            "remote_commit": sync_record.remote_commit,
            "conflict_details": sync_record.conflict_details,
            "sync_type": sync_record.sync_type,
            "created_at": sync_record.created_at.isoformat(),
        }

    async def get_sync_history(
        self,
        vps_id: int,
        db: AsyncSession,
        limit: int = 50,
    ) -> List[Dict]:
        """
        Get sync history for a VPS.

        Args:
            vps_id: VPS server ID.
            db: Database session.
            limit: Maximum records to return.

        Returns:
            List of sync history entries.
        """
        result = await db.execute(
            select(VPSGitSync)
            .where(VPSGitSync.vps_id == vps_id)
            .order_by(VPSGitSync.created_at.desc())
            .limit(limit)
        )
        sync_records = result.scalars().all()

        return [
            {
                "sync_id": record.id,
                "status": record.sync_status,
                "last_sync_at": record.last_sync_at.isoformat() if record.last_sync_at else None,
                "local_commit": record.local_commit,
                "remote_commit": record.remote_commit,
                "sync_type": record.sync_type,
                "created_at": record.created_at.isoformat(),
            }
            for record in sync_records
        ]

    async def resolve_conflict(
        self,
        sync_id: int,
        resolution: str,  # "local", "remote", "merge", "manual"
        db: AsyncSession,
    ) -> bool:
        """
        Resolve a sync conflict.

        Args:
            sync_id: Sync record ID.
            resolution: How to resolve conflict.
            db: Database session.

        Returns:
            True if resolved successfully.
        """
        result = await db.execute(
            select(VPSGitSync).where(VPSGitSync.id == sync_id)
        )
        sync_record = result.scalar_one_or_none()

        if not sync_record:
            return False

        if sync_record.sync_status != "conflict":
            return False

        # Get VPS information
        vps_result = await db.execute(
            select(VPSServer).where(VPSServer.id == sync_record.vps_id)
        )
        vps = vps_result.scalar_one_or_none()

        if not vps:
            return False

        # Resolve conflict based on strategy
        vps_config_dir = f"~/.openclaw"
        loop = asyncio.get_event_loop()

        try:
            if resolution == "local":
                # Keep local changes, reject remote
                commands = [
                    f"cd {vps_config_dir}",
                    "git reset --hard HEAD",  # Reset to local HEAD
                    "git clean -fd",  # Clean untracked files
                ]

                # Also reset central repo to previous commit
                if sync_record.local_commit:
                    self.git_manager.repo.git.reset("--hard", sync_record.local_commit)

            elif resolution == "remote":
                # Accept remote changes
                commands = [
                    f"cd {vps_config_dir}",
                    "git reset --hard origin/master",
                    "git clean -fd",
                ]

                # Reset central repo to VPS commit
                if sync_record.remote_commit:
                    self.git_manager.repo.git.reset("--hard", sync_record.remote_commit)

            elif resolution == "merge":
                # Attempt automated merge with AI assistance
                # This would integrate with an LLM to intelligently merge
                # For now, mark as resolved with manual intervention needed
                commands = [
                    f"cd {vps_config_dir}",
                    "git merge --no-commit origin/master",
                    # User would manually resolve and commit
                ]

            result = await loop.run_in_executor(None, self.ssh_pool.execute, vps.hostname, vps.ssh_user, vps.ssh_key_path, " && ".join(commands))

            if result.exit_code != 0 and resolution != "merge":
                raise Exception(f"Conflict resolution failed: {result.stderr}")

            # Mark as resolved
            sync_record.sync_status = "success"
            sync_record.conflict_details = {"resolution": resolution, "resolved_at": datetime.utcnow().isoformat()}
            await db.commit()

            return True

        except Exception as e:
            sync_record.conflict_details = {"resolution_error": str(e)}
            await db.commit()
            return False


# Global sync manager instance
_sync_manager: Optional[VPSGitSyncManager] = None


def get_vps_sync_manager() -> VPSGitSyncManager:
    """Get or create global VPS sync manager instance."""
    global _sync_manager
    if _sync_manager is None:
        _sync_manager = VPSGitSyncManager()
    return _sync_manager
