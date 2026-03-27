"""Tests for Git manager service."""
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from git import GitCommandError, InvalidGitRepositoryError

from services.git_manager import GitManager


class TestGitManager:
    """Test cases for GitManager class."""

    @pytest.fixture
    def temp_repo_path(self):
        """Create temporary directory for Git repository."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def git_manager(self, temp_repo_path):
        """Create GitManager instance for testing."""
        return GitManager(repo_path=temp_repo_path)

    def test_git_manager_init_new_repo(self, temp_repo_path):
        """Test GitManager initialization with new repository."""
        with patch("services.git_manager.get_encryption_service") as mock_enc:
            mock_enc.return_value = MagicMock()

            with patch("git.Repo.init") as mock_init:
                with patch.object(GitManager, "_create_base_structure"):
                    with patch.object(GitManager, "_initial_commit"):
                        manager = GitManager(repo_path=temp_repo_path)
                        mock_init.assert_called_once_with(temp_repo_path)

    def test_git_manager_init_existing_repo(self, temp_repo_path):
        """Test GitManager initialization with existing repository."""
        with patch("services.git_manager.get_encryption_service") as mock_enc:
            mock_enc.return_value = MagicMock()

            with patch("git.Repo") as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo_class.return_value = mock_repo

                manager = GitManager(repo_path=temp_repo_path)
                assert manager.repo == mock_repo
                assert manager.repo_path == temp_repo_path

    def test_create_base_structure(self, git_manager, temp_repo_path):
        """Test creation of base directory structure."""
        git_manager.repo = MagicMock()

        git_manager._create_base_structure()

        # Check that directories were created
        assert (temp_repo_path / "main").exists()
        assert (temp_repo_path / "main" / "skills").exists()
        assert (temp_repo_path / "deployments").exists()

        # Check gitignore was created
        assert (temp_repo_path / ".gitignore").exists()

    def test_create_gitignore(self, git_manager, temp_repo_path):
        """Test gitignore file creation."""
        git_manager._create_gitignore()

        gitignore_path = temp_repo_path / ".gitignore"
        assert gitignore_path.exists()

        content = gitignore_path.read_text()
        assert "openclaw.json" in content
        assert "*.log" in content
        assert ".DS_Store" in content

    def test_create_openclaw_template(self, git_manager, temp_repo_path):
        """Test OpenClaw configuration template creation."""
        git_manager._create_openclaw_template()

        template_path = temp_repo_path / "main" / "openclaw.json.template"
        assert template_path.exists()

        config = json.loads(template_path.read_text())
        assert "agent" in config
        assert "gateway" in config
        assert "skills" in config

    def test_create_agents_template(self, git_manager, temp_repo_path):
        """Test agents template creation."""
        git_manager._create_agents_template()

        template_path = temp_repo_path / "main" / "AGENTS.md.template"
        assert template_path.exists()

        content = template_path.read_text()
        assert "OpenClaw Agents Configuration" in content

    def test_initial_commit(self, git_manager):
        """Test initial commit creation."""
        git_manager.repo = MagicMock()
        git_manager.repo.git.add = MagicMock()
        git_manager.repo.index.commit = MagicMock()

        git_manager._initial_commit()

        git_manager.repo.git.add.assert_called_once_with(A=True)
        git_manager.repo.index.commit.assert_called_once()

    def test_create_customer_branch(self, git_manager):
        """Test creating customer branch."""
        git_manager.repo = MagicMock()
        git_manager.repo.git.checkout = MagicMock()
        git_manager.repo.git.add = MagicMock()
        git_manager.repo.index.commit = MagicMock()

        result = git_manager.create_customer_branch(1, "Test Customer")

        assert result == "customer-1"
        git_manager.repo.git.checkout.assert_called()

    def test_update_customer_config(self, git_manager, temp_repo_path):
        """Test updating customer configuration."""
        git_manager.repo = MagicMock()
        git_manager.encryption = MagicMock()
        git_manager.encryption.encrypt_dict.return_value = "encrypted_config"

        git_manager.repo.git.checkout = MagicMock()
        git_manager.repo.git.add = MagicMock()
        git_manager.repo.index.commit = MagicMock()
        git_manager.repo.head.commit.hexsha = "abc123"

        test_config = {"agent": {"model": "test"}}
        commit_hash = git_manager.update_customer_config(1, test_config, 1)

        assert commit_hash == "abc123"
        git_manager.encryption.encrypt_dict.assert_called_once()

    def test_get_customer_config(self, git_manager, temp_repo_path):
        """Test getting customer configuration."""
        git_manager.repo = MagicMock()
        git_manager.repo.git.checkout = MagicMock()

        customer_dir = temp_repo_path / "customer-1"
        customer_dir.mkdir(parents=True, exist_ok=True)
        config_file = customer_dir / "openclaw.json"
        config_file.write_text(json.dumps({"test": "config"}))

        config = git_manager.get_customer_config(1)

        assert config == {"test": "config"}

    def test_get_customer_config_from_template(self, git_manager, temp_repo_path):
        """Test getting customer configuration from template."""
        git_manager.repo = MagicMock()
        git_manager.repo.git.checkout = MagicMock()

        main_dir = temp_repo_path / "main"
        main_dir.mkdir(parents=True, exist_ok=True)
        template_file = main_dir / "openclaw.json.template"
        template_file.write_text(json.dumps({"from_template": True}))

        customer_dir = temp_repo_path / "customer-1"
        customer_dir.mkdir(parents=True, exist_ok=True)

        config = git_manager.get_customer_config(1)

        assert config == {"from_template": True}

    def test_update_skill_config(self, git_manager, temp_repo_path):
        """Test updating skill configuration."""
        git_manager.repo = MagicMock()
        git_manager.repo.git.checkout = MagicMock()
        git_manager.repo.index.commit = MagicMock()
        git_manager.repo.head.commit.hexsha = "def456"

        customer_dir = temp_repo_path / "customer-1" / "skills"
        customer_dir.mkdir(parents=True, exist_ok=True)

        commit_hash = git_manager.update_skill_config(
            1, "test_skill", {"enabled": True}, 1
        )

        assert commit_hash == "def456"

        skill_file = customer_dir / "test_skill.json"
        assert skill_file.exists()

    def test_get_config_history(self, git_manager):
        """Test getting configuration history."""
        git_manager.repo = MagicMock()
        git_manager.repo.git.checkout = MagicMock()

        mock_commit1 = MagicMock()
        mock_commit1.hexsha = "abc123"
        mock_commit1.message = "Commit 1"
        mock_commit1.author = "Test Author"
        mock_commit1.committed_date = 1234567890

        mock_commit2 = MagicMock()
        mock_commit2.hexsha = "def456"
        mock_commit2.message = "Commit 2"
        mock_commit2.author = "Test Author"
        mock_commit2.committed_date = 1234567891

        git_manager.repo.iter_commits.return_value = [mock_commit1, mock_commit2]

        history = git_manager.get_config_history(1, limit=10)

        assert len(history) == 2
        assert history[0]["hash"] == "abc123"
        assert history[0]["message"] == "Commit 1"

    def test_rollback_config(self, git_manager):
        """Test configuration rollback."""
        git_manager.repo = MagicMock()
        git_manager.repo.git.checkout = MagicMock()
        git_manager.repo.git.reset = MagicMock()
        git_manager.repo.index.commit = MagicMock()
        git_manager.repo.head.commit.hexsha = "new_commit"

        commit_hash = git_manager.rollback_config(1, "abc123", 1)

        assert commit_hash == "new_commit"
        git_manager.repo.git.reset.assert_called_once_with("--hard", "abc123")

    def test_push_to_remote(self, git_manager):
        """Test pushing to remote repository."""
        git_manager.repo = MagicMock()
        git_manager.repo.git.push = MagicMock()

        with patch("services.git_manager.settings") as mock_settings:
            mock_settings.git_repo_url = "https://github.com/test/repo.git"

            git_manager.push_to_remote("test-branch")

            git_manager.repo.git.push.assert_called_once_with("origin", "test-branch")

    def test_push_to_remote_no_url(self, git_manager):
        """Test push when no remote URL is configured."""
        git_manager.repo = MagicMock()
        git_manager.repo.git.push = MagicMock()

        with patch("services.git_manager.settings") as mock_settings:
            mock_settings.git_repo_url = None

            git_manager.push_to_remote("test-branch")

            git_manager.repo.git.push.assert_not_called()

    def test_pull_from_remote(self, git_manager):
        """Test pulling from remote repository."""
        git_manager.repo = MagicMock()
        git_manager.repo.git.pull = MagicMock()

        with patch("services.git_manager.settings") as mock_settings:
            mock_settings.git_repo_url = "https://github.com/test/repo.git"

            git_manager.pull_from_remote("test-branch")

            git_manager.repo.git.pull.assert_called_once_with("origin", "test-branch")

    def test_track_deployment(self, git_manager, temp_repo_path):
        """Test tracking deployment."""
        git_manager.repo = MagicMock()
        git_manager.repo.git.add = MagicMock()
        git_manager.repo.index.commit = MagicMock()

        deployments_dir = temp_repo_path / "deployments" / "customer-1" / "vps-1"
        deployments_dir.mkdir(parents=True, exist_ok=True)

        git_manager.track_deployment(1, 1, "abc123", "success", 1)

        deployments_file = deployments_dir / "deployments.json"
        assert deployments_file.exists()

        deployments = json.loads(deployments_file.read_text())
        assert len(deployments) == 1
        assert deployments[0]["commit_hash"] == "abc123"
        assert deployments[0]["status"] == "success"


class TestGitManagerErrors:
    """Test cases for GitManager error handling."""

    @pytest.fixture
    def git_manager(self):
        """Create GitManager instance for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            return GitManager(repo_path=Path(tmpdir))

    def test_git_command_error_handling(self, git_manager):
        """Test GitCommandError handling."""
        git_manager.repo = MagicMock()
        git_manager.repo.git.checkout.side_effect = GitCommandError("checkout failed")

        with pytest.raises(GitCommandError):
            git_manager.get_customer_config(1)

    def test_invalid_repo_error_handling(self):
        """Test InvalidGitRepositoryError handling."""
        with patch("git.Repo") as mock_repo_class:
            mock_repo_class.side_effect = InvalidGitRepositoryError()

            with patch("services.git_manager.get_encryption_service"):
                with patch.object(GitManager, "_create_base_structure"):
                    with patch.object(GitManager, "_initial_commit"):
                        # This should handle the error and create a new repo
                        manager = GitManager()
                        assert manager.repo is not None
