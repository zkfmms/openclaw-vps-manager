"""Git configuration management service."""
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from git import Repo, GitCommandError
from git.exc import InvalidGitRepositoryError

from config import get_settings
from services.encryption import get_encryption_service

settings = get_settings()


class GitManager:
    """Service for managing Git-based configuration repository."""

    def __init__(self, repo_path: Optional[Path] = None):
        """
        Initialize Git manager.

        Args:
            repo_path: Path to Git repository. If None, uses configured path.
        """
        self.repo_path = Path(repo_path) if repo_path else Path(settings.git_repo_path)
        self.repo: Optional[Repo] = None
        self.encryption = get_encryption_service()
        self._initialize_repo()

    def _initialize_repo(self) -> None:
        """Initialize Git repository if it doesn't exist."""
        try:
            self.repo = Repo(self.repo_path)
        except InvalidGitRepositoryError:
            # Create new repository
            self.repo = Repo.init(self.repo_path)
            self._create_base_structure()
            self._initial_commit()

    def _create_base_structure(self) -> None:
        """Create base directory structure."""
        # Create main directory and skills subdirectory
        main_dir = self.repo_path / "main"
        skills_dir = main_dir / "skills"
        deployments_dir = self.repo_path / "deployments"

        for directory in [main_dir, skills_dir, deployments_dir]:
            directory.mkdir(parents=True, exist_ok=True)

        # Create .gitignore to exclude sensitive files from Git
        self._create_gitignore()

    def _create_gitignore(self) -> None:
        """Create .gitignore for the Git repository."""
        gitignore_path = self.repo_path / ".gitignore"
        gitignore_content = """# Security: Ignore unencrypted configuration files
# Only encrypted versions (.enc) should be in the repository

# Unencrypted JSON files (sensitive configs)
openclaw.json
openclaw.json.bak
openclaw.json.tmp
*.json
*.json.bak
*.json.tmp

# Keep encrypted versions
!openclaw.json.enc
!*.json.enc

# Temporary and backup files
*.tmp
*.bak
*~
*.swp
*.swo

# Backup SSH keys (should be in separate secure location)
*.key.bak
*.pem.bak
id_ed25519.bak
id_rsa.bak

# Secrets directories
credentials/
secrets/
tokens/
.credentials/
.secrets/
.tokens/

# Log files
*.log

# OS files
.DS_Store
Thumbs.db

# IDE files
.vscode/
.idea/
"""
        gitignore_path.write_text(gitignore_content)

    def _create_openclaw_template(self) -> None:
        """Create OpenClaw configuration template."""
        template_path = self.repo_path / "main" / "openclaw.json.template"
        template = {
            "agent": {
                "model": "anthropic/claude-sonnet-4-6",
            },
            "gateway": {
                "port": 18789,
                "bind": "loopback",
                "auth": {
                    "mode": "token",
                    "token": {
                        "source": "env",
                        "provider": "default",
                        "id": "OPENCLAW_GATEWAY_TOKEN"
                    }
                }
            },
            "skills": {
                "load": {
                    "extraDirs": ["~/.openclaw/workspace/skills"],
                    "watch": True,
                },
                "entries": {}
            }
        }

        template_path.write_text(json.dumps(template, indent=2))

    def _create_agents_template(self) -> None:
        """Create AGENTS.md template."""
        template_path = self.repo_path / "main" / "AGENTS.md.template"
        template = """# OpenClaw Agents Configuration

This file contains agent definitions for OpenClaw.

## Agent Structure

```yaml
agent_name:
  model: anthropic/claude-sonnet-4-6
  system: "You are a helpful assistant..."
  temperature: 0.7
  max_tokens: 4096
```

## Example Agents

```yaml
assistant:
  model: anthropic/claude-sonnet-4-6
  system: "You are a helpful AI assistant for OpenClaw."
  temperature: 0.7
  max_tokens: 4096

coder:
  model: anthropic/claude-opus-4-6
  system: "You are an expert software developer."
  temperature: 0.3
  max_tokens: 8192
```
"""
        template_path.write_text(template)

    def _initial_commit(self) -> None:
        """Create initial commit with base structure."""
        self.repo.git.add(A=True)
        self.repo.index.commit("Initial commit: base structure and templates")

    def create_customer_branch(self, customer_id: int, customer_name: str) -> str:
        """
        Create isolated Git branch for a customer.

        Args:
            customer_id: Customer ID.
            customer_name: Customer name.

        Returns:
            Branch name.
        """
        branch_name = settings.get_customer_branch(customer_id)

        # Create customer-specific directory structure
        customer_dir = self.repo_path / f"customer-{customer_id}"
        customer_dir.mkdir(parents=True, exist_ok=True)

        # Copy templates to customer directory
        import shutil
        for template_file in (self.repo_path / "main").glob("*.template"):
            # Create local unencrypted copy for reference (not committed)
            dest = customer_dir / template_file.name.replace(".template", "")
            shutil.copy(template_file, dest)

            # Create encrypted version to commit to Git
            encrypted_dest = customer_dir / (template_file.name.replace(".template", "") + ".enc")
            template_content = json.loads(template_file.read_text())
            encrypted_content = self.encryption.encrypt_dict(template_content)
            encrypted_dest.write_text(encrypted_content)

        # Create skills and workspace directories
        (customer_dir / "skills").mkdir(parents=True, exist_ok=True)
        (customer_dir / "workspace").mkdir(parents=True, exist_ok=True)

        # Create deployment tracking directory
        deployments_dir = self.repo_path / "deployments" / f"customer-{customer_id}"
        deployments_dir.mkdir(parents=True, exist_ok=True)

        # Stage and commit (only add encrypted files and directories)
        self.repo.git.add(f"{customer_dir}/*.enc")
        self.repo.git.add(f"{customer_dir}/skills")
        self.repo.git.add(f"{customer_dir}/workspace")
        self.repo.git.add(f"deployments/customer-{customer_id}")
        commit_message = f"Initialize customer branch: {customer_name} (ID: {customer_id})"
        self.repo.index.commit(commit_message)

        # Create and checkout branch
        try:
            self.repo.git.checkout("-b", branch_name)
        except GitCommandError:
            # Branch might already exist
            self.repo.git.checkout(branch_name)

        return branch_name

    def update_vps_config(
        self,
        config: Dict[str, Any],
        vps_id: int,
        user_id: int,
        commit_message: Optional[str] = None,
    ) -> str:
        """
        Update VPS configuration in VPS-specific directory.

        Args:
            config: OpenClaw configuration dictionary.
            vps_id: VPS ID for directory name.
            user_id: ID of user making the change.
            commit_message: Optional commit message.

        Returns:
            Git commit hash.
        """
        # Filter out sensitive information before saving
        filtered_config = self._filter_sensitive_config(config)

        # Use VPS-specific directory if vps_id is set
        if hasattr(self, 'vps_dir'):
            target_dir = self.vps_dir
        else:
            # Fallback for legacy operations
            target_dir = self.repo_path

        # Ensure VPS directory exists
        vps_dir_name = f"vps-{vps_id}"
        vps_dir = self.repo_path / vps_dir_name
        vps_dir.mkdir(parents=True, exist_ok=True)

        # Encrypt and save configuration
        config_file = vps_dir / "openclaw.json"
        config_encrypted = vps_dir / "openclaw.json.enc"

        # Save unencrypted version for local use only (excluded from Git by .gitignore)
        config_file.write_text(json.dumps(filtered_config, indent=2))

        # Save encrypted version to Git
        encrypted_config = self.encryption.encrypt_dict(filtered_config)
        config_encrypted.write_text(encrypted_config)

        # Commit changes (only add encrypted file to Git)
        if commit_message is None:
            commit_message = f"Update VPS {vps_id} configuration by user {user_id}"

        # Add file relative to repo root
        file_to_add = config_encrypted.relative_to(self.repo_path)
        self.repo.git.add(str(file_to_add))
        commit_hash = self.repo.index.commit(commit_message)

        return commit_hash.hexsha

    def _filter_sensitive_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter out sensitive information from configuration.

        This removes tokens, API keys, and other secrets that should not be
        committed to the Git repository, while preserving the configuration structure.

        Args:
            config: Original configuration dictionary.

        Returns:
            Filtered configuration dictionary with sensitive fields removed.
        """
        filtered = {}
        sensitive_patterns = [
            'token',
            'apiKey',
            'api_key',
            'secret',
            'password',
            'credential',
        ]

        for key, value in config.items():
            if key == 'channels':
                # Filter channel tokens
                filtered[key] = self._filter_sensitive_fields(value, sensitive_patterns)
            elif key == 'gateway':
                # Filter gateway auth tokens
                filtered[key] = self._filter_sensitive_fields(value, sensitive_patterns)
            elif key == 'secrets':
                # Skip entire secrets section
                continue
            else:
                # Keep other sections as-is
                filtered[key] = value

        return filtered

    def _filter_sensitive_fields(self, data: Any, patterns: List[str]) -> Any:
        """
        Recursively filter sensitive fields from a data structure.

        Args:
            data: Data structure to filter (dict, list, or primitive).
            patterns: List of field names to filter out.

        Returns:
            Filtered data structure.
        """
        if isinstance(data, dict):
            filtered = {}
            for key, value in data.items():
                if any(pattern in key.lower() for pattern in patterns):
                    # Skip sensitive field
                    continue
                elif isinstance(value, (dict, list)):
                    # Recursively filter nested structures
                    filtered[key] = self._filter_sensitive_fields(value, patterns)
                else:
                    filtered[key] = value
            return filtered
        elif isinstance(data, list):
            return [self._filter_sensitive_fields(item, patterns) for item in data]
        else:
            return data

    def get_customer_config(self, customer_id: int) -> Dict[str, Any]:
        """
        Get customer configuration from Git.

        Args:
            customer_id: Customer ID.

        Returns:
            Configuration dictionary.
        """
        branch_name = settings.get_customer_branch(customer_id)

        # Checkout customer branch
        self.repo.git.checkout(branch_name)

        # Read configuration
        customer_dir = self.repo_path / f"customer-{customer_id}"
        config_file = customer_dir / "openclaw.json"

        if not config_file.exists():
            # Load from template
            template_file = self.repo_path / "main" / "openclaw.json.template"
            config = json.loads(template_file.read_text())
        else:
            config = json.loads(config_file.read_text())

        return config

    def update_skill_config(
        self,
        customer_id: int,
        skill_name: str,
        skill_config: Dict[str, Any],
        user_id: int,
    ) -> str:
        """
        Update skill configuration for a customer.

        Args:
            customer_id: Customer ID.
            skill_name: Name of the skill.
            skill_config: Skill configuration.
            user_id: ID of user making the change.

        Returns:
            Git commit hash.
        """
        branch_name = settings.get_customer_branch(customer_id)
        self.repo.git.checkout(branch_name)

        customer_dir = self.repo_path / f"customer-{customer_id}"
        skill_file = customer_dir / "skills" / f"{skill_name}.json"

        skill_file.write_text(json.dumps(skill_config, indent=2))

        commit_message = f"Update skill '{skill_name}' for customer {customer_id} by user {user_id}"
        self.repo.index.commit(commit_message)

        return self.repo.head.commit.hexsha

    def get_config_history(
        self,
        customer_id: int,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get configuration change history for a customer.

        Args:
            customer_id: Customer ID.
            limit: Maximum number of commits to return.

        Returns:
            List of commit information.
        """
        branch_name = settings.get_customer_branch(customer_id)
        self.repo.git.checkout(branch_name)

        commits = list(self.repo.iter_commits(branch_name, max_count=limit))

        history = []
        for commit in commits:
            history.append({
                "hash": commit.hexsha,
                "message": commit.message.strip(),
                "author": str(commit.author),
                "timestamp": datetime.fromtimestamp(commit.committed_date).isoformat(),
            })

        return history

    def rollback_config(
        self,
        customer_id: int,
        commit_hash: str,
        user_id: int,
    ) -> str:
        """
        Rollback configuration to a previous commit.

        Args:
            customer_id: Customer ID.
            commit_hash: Target commit hash to rollback to.
            user_id: ID of user performing rollback.

        Returns:
            New commit hash after rollback.
        """
        branch_name = settings.get_customer_branch(customer_id)
        self.repo.git.checkout(branch_name)

        # Reset to target commit
        self.repo.git.reset("--hard", commit_hash)

        # Create new commit for rollback record
        commit_message = f"Rollback to {commit_hash[:7]} for customer {customer_id} by user {user_id}"
        self.repo.index.commit(commit_message)

        return self.repo.head.commit.hexsha

    def push_to_remote(self, branch_name: Optional[str] = None) -> None:
        """
        Push changes to remote repository.

        Args:
            branch_name: Branch name to push. If None, pushes current branch.
        """
        if settings.git_repo_url:
            if branch_name:
                self.repo.git.push("origin", branch_name)
            else:
                self.repo.git.push("origin", "HEAD")

    def pull_from_remote(self, branch_name: Optional[str] = None) -> None:
        """
        Pull changes from remote repository.

        Args:
            branch_name: Branch name to pull. If None, pulls current branch.
        """
        if settings.git_repo_url:
            if branch_name:
                self.repo.git.pull("origin", branch_name)
            else:
                self.repo.git.pull("origin", "HEAD")

    def track_deployment(
        self,
        customer_id: int,
        vps_id: int,
        commit_hash: str,
        status: str,
        user_id: int,
    ) -> None:
        """
        Track deployment in Git repository.

        Args:
            customer_id: Customer ID.
            vps_id: VPS server ID.
            commit_hash: Configuration commit hash.
            status: Deployment status.
            user_id: ID of user initiating deployment.
        """
        deployments_dir = self.repo_path / "deployments" / f"customer-{customer_id}"
        vps_dir = deployments_dir / f"vps-{vps_id}"
        vps_dir.mkdir(parents=True, exist_ok=True)

        deployments_file = vps_dir / "deployments.json"

        # Load existing deployments or create new
        if deployments_file.exists():
            deployments = json.loads(deployments_file.read_text())
        else:
            deployments = []

        # Add new deployment record
        deployments.append({
            "commit_hash": commit_hash,
            "status": status,
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
        })

        deployments_file.write_text(json.dumps(deployments, indent=2))

        # Commit changes
        self.repo.git.add(str(deployments_file.relative_to(self.repo_path)))
        commit_message = f"Track deployment for VPS {vps_id}, commit {commit_hash[:7]}"
        self.repo.index.commit(commit_message)


# Global Git manager instance
_git_manager: Optional[GitManager] = None


def get_git_manager() -> GitManager:
    """
    Get or create global Git manager instance.

    Returns:
        Git manager instance for the main repository.
    """
    global _git_manager
    if _git_manager is None:
        _git_manager = GitManager()
    return _git_manager
