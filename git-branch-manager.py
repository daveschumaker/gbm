#!/usr/bin/env python3

import subprocess
import sys
import os
from typing import List, Optional, NamedTuple, Dict, Tuple, Any
import curses
from datetime import datetime, timedelta
import time
import json
import webbrowser
import urllib.parse
import re
import threading
import argparse
from pathlib import Path

# Load version from VERSION file
_version_file = Path(__file__).parent / 'VERSION'
if _version_file.exists():
    __version__ = _version_file.read_text().strip()
else:
    __version__ = 'unknown'

class BranchInfo(NamedTuple):
    name: str
    is_current: bool
    commit_hash: str
    commit_date: datetime
    commit_message: str
    commit_author: str
    has_uncommitted_changes: bool
    is_remote: bool
    remote_name: Optional[str]
    has_upstream: bool  # True if branch exists on remote
    is_merged: bool  # True if branch has been merged into main/master
    in_worktree: bool  # True if branch is checked out in a worktree
    commits_ahead: int  # Number of commits ahead of main/master
    commits_behind: int  # Number of commits behind main/master
    
    def format_relative_date(self) -> str:
        """Format the commit date as a relative time string."""
        now = datetime.now()
        diff = now - self.commit_date
        
        if diff.days == 0:
            if diff.seconds < 3600:
                minutes = diff.seconds // 60
                return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
            else:
                hours = diff.seconds // 3600
                return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif diff.days == 1:
            return "yesterday"
        elif diff.days < 7:
            return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
        elif diff.days < 30:
            weeks = diff.days // 7
            return f"{weeks} week{'s' if weeks != 1 else ''} ago"
        elif diff.days < 365:
            months = diff.days // 30
            return f"{months} month{'s' if months != 1 else ''} ago"
        else:
            years = diff.days // 365
            return f"{years} year{'s' if years != 1 else ''} ago"

class GitPlatformURLBuilder:
    """Builds URLs for different Git hosting platforms.
    
    Supports GitHub, GitLab, Bitbucket (Cloud & Server), Azure DevOps,
    and custom platforms via configuration.
    
    Attributes:
        config: Configuration dictionary containing platform settings
        remote_url: The Git remote URL to parse
        platform: Detected or configured platform name
        repo_info: Parsed repository information (owner, repo, etc.)
    """
    
    def __init__(self, config: Dict[str, Any], remote_url: str):
        """Initialize the URL builder with config and remote URL.
        
        Args:
            config: Configuration dict with optional 'platform', 'custom_patterns' keys
            remote_url: Git remote URL (SSH or HTTPS format)
        """
        self.config = config
        self.remote_url = remote_url
        self.platform = self._detect_platform()
        self.repo_info = self._parse_remote_url()
    
    def _detect_platform(self) -> str:
        """Detect the Git hosting platform from the remote URL.
        
        Checks config for manual platform setting first, then auto-detects
        based on URL patterns.
        
        Returns:
            Platform identifier: 'github', 'gitlab', 'bitbucket-cloud',
            'bitbucket-server', 'azure-devops', 'custom', or 'unknown'
        """
        if self.config.get('platform') != 'auto':
            return self.config.get('platform', 'unknown')
        
        url = self.remote_url.lower()
        
        if 'github.com' in url:
            return 'github'
        elif 'gitlab.com' in url:
            return 'gitlab'
        elif 'bitbucket.org' in url:
            return 'bitbucket-cloud'
        elif 'dev.azure.com' in url or 'visualstudio.com' in url:
            return 'azure-devops'
        elif '/projects/' in url and '/repos/' in url:
            # Bitbucket Server pattern
            return 'bitbucket-server'
        elif self.config.get('custom_patterns'):
            return 'custom'
        else:
            return 'unknown'
    
    def _parse_remote_url(self) -> Dict[str, str]:
        """Parse the remote URL to extract repository information.
        
        Handles both SSH (git@) and HTTPS URL formats. Extracts domain,
        owner/organization, repository name, and other platform-specific info.
        
        Returns:
            Dictionary containing parsed URL components:
            - domain: The host domain
            - owner: Repository owner or organization
            - repo: Repository name
            - project: Project key (Bitbucket Server)
            - org: Organization (Azure DevOps)
        """
        info = {}
        
        # Remove git@ prefix and .git suffix
        url = self.remote_url
        if url.startswith('git@'):
            url = url.replace('git@', 'https://').replace(':', '/', 1)
        if url.endswith('.git'):
            url = url[:-4]
        
        # Extract domain
        if '://' in url:
            protocol, rest = url.split('://', 1)
            info['protocol'] = protocol
            parts = rest.split('/', 1)
            info['domain'] = parts[0]
            path = parts[1] if len(parts) > 1 else ''
        else:
            info['domain'] = ''
            path = url
        
        # Platform-specific parsing
        if self.platform == 'github':
            # github.com/owner/repo
            parts = path.split('/')
            if len(parts) >= 2:
                info['owner'] = parts[0]
                info['repo'] = parts[1]
        
        elif self.platform == 'gitlab':
            # gitlab.com/owner/repo or gitlab.com/group/subgroup/repo
            parts = path.split('/')
            if len(parts) >= 2:
                info['owner'] = '/'.join(parts[:-1])
                info['repo'] = parts[-1]
        
        elif self.platform == 'bitbucket-cloud':
            # bitbucket.org/workspace/repo
            parts = path.split('/')
            if len(parts) >= 2:
                info['workspace'] = parts[0]
                info['repo'] = parts[1]
        
        elif self.platform == 'bitbucket-server':
            # domain/projects/PROJECT/repos/repo
            match = re.search(r'projects/([^/]+)/repos/([^/]+)', path)
            if match:
                info['project'] = match.group(1)
                info['repo'] = match.group(2)
        
        elif self.platform == 'azure-devops':
            # dev.azure.com/org/project/_git/repo
            parts = path.split('/')
            if len(parts) >= 4 and parts[2] == '_git':
                info['org'] = parts[0]
                info['project'] = parts[1]
                info['repo'] = parts[3]
        
        return info
    
    def build_branch_url(self, branch_name: str) -> Optional[str]:
        """Build URL to view a specific branch on the Git platform.
        
        Generates platform-specific URLs for viewing branch content.
        Handles URL encoding for branch names with special characters.
        
        Args:
            branch_name: Name of the branch to view
            
        Returns:
            URL string for viewing the branch, or None if platform not supported
            or repository info not available
        """
        if not self.repo_info:
            return None
        
        if self.platform == 'github':
            return f"https://github.com/{self.repo_info['owner']}/{self.repo_info['repo']}/tree/{urllib.parse.quote(branch_name)}"
        
        elif self.platform == 'gitlab':
            return f"https://gitlab.com/{self.repo_info['owner']}/{self.repo_info['repo']}/-/tree/{urllib.parse.quote(branch_name)}"
        
        elif self.platform == 'bitbucket-cloud':
            return f"https://bitbucket.org/{self.repo_info['workspace']}/{self.repo_info['repo']}/branch/{urllib.parse.quote(branch_name)}"
        
        elif self.platform == 'bitbucket-server':
            return f"https://{self.repo_info['domain']}/projects/{self.repo_info['project']}/repos/{self.repo_info['repo']}/browse?at=refs/heads/{urllib.parse.quote(branch_name)}"
        
        elif self.platform == 'azure-devops':
            return f"https://dev.azure.com/{self.repo_info['org']}/{self.repo_info['project']}/_git/{self.repo_info['repo']}?version=GB{urllib.parse.quote(branch_name)}"
        
        elif self.platform == 'custom' and self.config.get('custom_patterns', {}).get('branch'):
            template = self.config['custom_patterns']['branch']
            return template.format(branch=urllib.parse.quote(branch_name), **self.repo_info)
        
        return None
    
    def build_compare_url(self, branch_name: str, base_branch: Optional[str] = None) -> Optional[str]:
        """Build URL to compare branch with base branch or create PR.
        
        Generates platform-specific URLs for comparing branches or creating
        pull/merge requests. Uses configured default base branch if none specified.
        
        Args:
            branch_name: Source branch to compare
            base_branch: Target branch to compare against (defaults to config setting)
            
        Returns:
            URL string for comparing branches, or None if platform not supported
            or repository info not available
        """
        if not self.repo_info:
            return None
        
        if not base_branch:
            base_branch = self.config.get('default_base_branch', 'main')
        
        if self.platform == 'github':
            return f"https://github.com/{self.repo_info['owner']}/{self.repo_info['repo']}/compare/{urllib.parse.quote(base_branch)}...{urllib.parse.quote(branch_name)}"
        
        elif self.platform == 'gitlab':
            return f"https://gitlab.com/{self.repo_info['owner']}/{self.repo_info['repo']}/-/compare/{urllib.parse.quote(base_branch)}...{urllib.parse.quote(branch_name)}"
        
        elif self.platform == 'bitbucket-cloud':
            return f"https://bitbucket.org/{self.repo_info['workspace']}/{self.repo_info['repo']}/pull-requests/new?source={urllib.parse.quote(branch_name)}&dest={urllib.parse.quote(base_branch)}"
        
        elif self.platform == 'bitbucket-server':
            return f"https://{self.repo_info['domain']}/projects/{self.repo_info['project']}/repos/{self.repo_info['repo']}/compare/commits?sourceBranch=refs/heads/{urllib.parse.quote(branch_name)}&targetBranch=refs/heads/{urllib.parse.quote(base_branch)}"
        
        elif self.platform == 'azure-devops':
            return f"https://dev.azure.com/{self.repo_info['org']}/{self.repo_info['project']}/_git/{self.repo_info['repo']}/pullrequestcreate?sourceRef={urllib.parse.quote(branch_name)}&targetRef={urllib.parse.quote(base_branch)}"
        
        elif self.platform == 'custom' and self.config.get('custom_patterns', {}).get('compare'):
            template = self.config['custom_patterns']['compare']
            return template.format(branch=urllib.parse.quote(branch_name), base=urllib.parse.quote(base_branch), **self.repo_info)
        
        return None

class GitBranchManager:
    """Main application class for managing Git branches through a TUI.
    
    Provides an interactive terminal interface for viewing, filtering,
    and managing Git branches with support for stashing, worktrees,
    and multiple Git hosting platforms.
    
    Attributes:
        branches: Complete list of all branches
        filtered_branches: Currently visible branches after filtering
        current_branch: Name of the currently checked out branch
        selected_index: Current cursor position in the branch list
        show_remotes: Whether to display remote branches
        search_filter: Current search string
        author_filter: Whether to show only current user's branches
        age_filter: Whether to hide old branches
        prefix_filter: Branch prefix to filter by
        merged_filter: Whether to hide merged branches
    """
    
    def __init__(self):
        """Initialize the Git Branch Manager with default settings.
        
        Sets up branch lists, filters, configuration, and attempts to
        detect the Git hosting platform from the remote URL.
        """
        self.branches: List[BranchInfo] = []
        self.filtered_branches: List[BranchInfo] = []  # Filtered view of branches
        self.current_branch: Optional[str] = None
        self.selected_index: int = 0
        self.working_dir: str = os.getcwd()  # Store current working directory
        self.show_remotes: bool = False  # Toggle for showing remote branches
        
        # Filters
        self.search_filter: str = ""  # Search by name substring
        self.author_filter: bool = False  # Show only current user's branches
        self.age_filter: bool = False  # Hide old branches (>3 months)
        self.prefix_filter: str = ""  # Filter by prefix
        self.merged_filter: bool = False  # Hide merged branches
        self.current_user: Optional[str] = self._get_current_user()
        self.last_stash_ref: Optional[str] = None  # Track last stash created
        self.protected_branches: List[str] = ["main", "master"]  # Protected branches
        
        # Configuration
        self.config: Dict[str, Any] = self._load_config()
        self.url_builder: Optional[GitPlatformURLBuilder] = None
        self._init_url_builder()
        
    def _get_config_path(self) -> str:
        """Get the path to the configuration file.
        
        Uses XDG Base Directory specification for config location.
        
        Returns:
            Full path to config.json file
        """
        xdg_config_home = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
        return os.path.join(xdg_config_home, 'git-branch-manager', 'config.json')
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or return defaults.
        
        Attempts to read config.json from the config directory.
        Returns default configuration if file doesn't exist.
        Validates configuration and falls back to defaults for invalid values.
        
        Returns:
            Configuration dictionary with platform settings
        """
        config_path = self._get_config_path()
        default_config = {
            'platform': 'auto',
            'default_base_branch': 'main',
            'browser_command': 'open' if sys.platform == 'darwin' else 'xdg-open' if sys.platform.startswith('linux') else 'start',
            'custom_patterns': {},
            'prevent_browser_for_merged': False  # Prevent opening browser for merged branches
        }
        
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    user_config = json.load(f)
                    # Validate and merge with defaults
                    validated_config = self._validate_config(user_config, default_config)
                    return validated_config
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load config from {config_path}: {e}")
                print("Using default configuration.")
        
        return default_config
    
    def _validate_config(self, user_config: Dict[str, Any], default_config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate user configuration and merge with defaults.
        
        Ensures all configuration values are valid types and within expected ranges.
        Falls back to default values for any invalid entries.
        
        Args:
            user_config: Configuration loaded from file
            default_config: Default configuration values
            
        Returns:
            Validated configuration dictionary
        """
        validated = default_config.copy()
        warnings = []
        
        # Validate platform
        if 'platform' in user_config:
            valid_platforms = ['auto', 'github', 'gitlab', 'bitbucket-cloud', 'bitbucket-server', 'azure-devops', 'custom']
            if isinstance(user_config['platform'], str) and user_config['platform'] in valid_platforms:
                validated['platform'] = user_config['platform']
            else:
                warnings.append(f"Invalid platform '{user_config['platform']}', using 'auto'")
        
        # Validate default_base_branch
        if 'default_base_branch' in user_config:
            if isinstance(user_config['default_base_branch'], str) and user_config['default_base_branch'].strip():
                validated['default_base_branch'] = user_config['default_base_branch']
            else:
                warnings.append(f"Invalid default_base_branch, using 'main'")
        
        # Validate browser_command
        if 'browser_command' in user_config:
            if isinstance(user_config['browser_command'], str) and user_config['browser_command'].strip():
                validated['browser_command'] = user_config['browser_command']
            else:
                warnings.append(f"Invalid browser_command, using system default")
        
        # Validate custom_patterns
        if 'custom_patterns' in user_config:
            if isinstance(user_config['custom_patterns'], dict):
                valid_patterns = {}
                for key, value in user_config['custom_patterns'].items():
                    if isinstance(key, str) and isinstance(value, str):
                        valid_patterns[key] = value
                    else:
                        warnings.append(f"Invalid custom pattern: {key}")
                validated['custom_patterns'] = valid_patterns
            else:
                warnings.append("Invalid custom_patterns format, using empty dict")
        
        # Validate prevent_browser_for_merged
        if 'prevent_browser_for_merged' in user_config:
            if isinstance(user_config['prevent_browser_for_merged'], bool):
                validated['prevent_browser_for_merged'] = user_config['prevent_browser_for_merged']
            else:
                warnings.append(f"Invalid prevent_browser_for_merged value, using False")
        
        # Print warnings if any
        if warnings:
            print("\nConfiguration warnings:")
            for warning in warnings:
                print(f"  - {warning}")
            print("")
        
        return validated
    
    def _save_config(self) -> None:
        """Save current configuration to file.
        
        Creates config directory if needed and writes current
        configuration to config.json.
        """
        config_path = self._get_config_path()
        config_dir = os.path.dirname(config_path)
        
        # Create directory if it doesn't exist
        if not os.path.exists(config_dir):
            os.makedirs(config_dir, mode=0o755)
        
        try:
            with open(config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save config to {config_path}: {e}")
    
    def _init_url_builder(self) -> None:
        """Initialize the URL builder with the current remote URL.
        
        Attempts to get the origin remote URL and create a
        GitPlatformURLBuilder instance. Sets url_builder to None
        if no remote is configured.
        """
        try:
            result = self._run_command(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                check=True
            )
            remote_url = result.stdout.strip()
            if remote_url:
                self.url_builder = GitPlatformURLBuilder(self.config, remote_url)
        except subprocess.CalledProcessError:
            # No remote URL available
            self.url_builder = None
        
    def has_active_filters(self) -> bool:
        """Check if any filters are currently active.
        
        Returns:
            True if any filter (search, author, age, prefix, or merged) is active
        """
        return bool(self.search_filter or self.author_filter or self.age_filter or self.prefix_filter or self.merged_filter)
    
    def clear_all_filters(self) -> None:
        """Clear all active filters and reset the branch view.
        
        Resets search, author, age, prefix, and merged filters,
        then reapplies filtering to show all branches.
        """
        self.search_filter = ""
        self.author_filter = False
        self.age_filter = False
        self.prefix_filter = ""
        self.merged_filter = False
        self._apply_filters()
        self.selected_index = 0
        
    def _run_command(self, cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
        """Run a command in the current working directory.
        
        Wrapper around subprocess.run that ensures commands are executed
        in the correct working directory.
        
        Args:
            cmd: Command and arguments as a list
            **kwargs: Additional arguments passed to subprocess.run
            
        Returns:
            CompletedProcess instance with command results
        """
        if 'cwd' not in kwargs:
            kwargs['cwd'] = self.working_dir
        return subprocess.run(cmd, **kwargs)
        
    def _get_current_user(self) -> Optional[str]:
        """Get the current git user email.
        
        Used for the author filter to show only branches created by
        the current user.
        
        Returns:
            User email address from git config, or None if not configured
        """
        try:
            result = self._run_command(
                ["git", "config", "user.email"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None
        
    def get_branch_info(self, branch: str, is_remote: bool = False, remote_name: Optional[str] = None) -> Optional[BranchInfo]:
        """Get commit info for a specific branch."""
        try:
            # Get commit hash, date, message, and author email
            result = self._run_command(
                ["git", "log", "-1", "--format=%H|%at|%s|%ae", branch],
                capture_output=True,
                text=True,
                check=True
            )
            
            if result.stdout.strip():
                parts = result.stdout.strip().split('|', 3)
                if len(parts) == 4:
                    commit_hash = parts[0][:12]  # Short hash
                    commit_timestamp = int(parts[1])
                    commit_date = datetime.fromtimestamp(commit_timestamp)
                    commit_message = parts[2]
                    commit_author = parts[3]
                    
                    # Check for uncommitted changes only on current branch
                    has_uncommitted_changes = False
                    if branch == self.current_branch:
                        status_result = self._run_command(
                            ["git", "status", "--porcelain"],
                            capture_output=True,
                            text=True,
                            check=True
                        )
                        has_uncommitted_changes = bool(status_result.stdout.strip())
                    
                    return BranchInfo(
                        name=branch,
                        is_current=(branch == self.current_branch),
                        commit_hash=commit_hash,
                        commit_date=commit_date,
                        commit_message=commit_message,
                        commit_author=commit_author,
                        has_uncommitted_changes=has_uncommitted_changes,
                        is_remote=is_remote,
                        remote_name=remote_name
                    )
            return None
            
        except subprocess.CalledProcessError:
            return None
    
    def _get_batch_branch_info(self, branches: List[Tuple[str, bool, Optional[str]]], worktree_branches: set = None) -> Dict[str, Dict]:
        """Get branch info for multiple branches in a single git command."""
        if not branches:
            return {}
        
        # Build format string for git for-each-ref
        format_str = "%(refname:short)|%(objectname:short)|%(committerdate:unix)|%(subject)|%(authoremail)"
        
        # Get info for all branches at once
        branch_names = [b[0] for b in branches]
        
        # Use git for-each-ref which is much faster than individual git log commands
        cmd = ["git", "for-each-ref", f"--format={format_str}"]
        
        # Add ref patterns for the branches we want
        ref_patterns = []
        for branch_name, is_remote, _ in branches:
            if is_remote:
                ref_patterns.append(f"refs/remotes/{branch_name}")
            else:
                ref_patterns.append(f"refs/heads/{branch_name}")
        
        cmd.extend(ref_patterns)
        
        try:
            result = self._run_command(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            branch_data = {}
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split('|', 4)
                    if len(parts) == 5:
                        ref_name = parts[0]
                        # Extract branch name from ref
                        if ref_name.startswith('refs/heads/'):
                            branch_name = ref_name[11:]  # Remove 'refs/heads/'
                        elif ref_name.startswith('refs/remotes/'):
                            branch_name = ref_name[13:]  # Remove 'refs/remotes/'
                        else:
                            branch_name = ref_name
                        
                        # Strip angle brackets from email if present
                        author_email = parts[4]
                        if author_email.startswith('<') and author_email.endswith('>'):
                            author_email = author_email[1:-1]
                        
                        branch_data[branch_name] = {
                            'hash': parts[1],
                            'timestamp': int(parts[2]),
                            'message': parts[3],
                            'author': author_email
                        }
            
            return branch_data
            
        except subprocess.CalledProcessError:
            return {}
    
    def _check_uncommitted_changes_batch(self) -> bool:
        """Check if current branch has uncommitted changes.
        
        Uses git status --porcelain for a machine-readable output format.
        
        Returns:
            True if there are uncommitted changes, False otherwise
        """
        try:
            status_result = self._run_command(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=True
            )
            return bool(status_result.stdout.strip())
        except subprocess.CalledProcessError:
            return False
    
    def _get_remote_branches_set(self) -> set:
        """Get a set of all branch names that exist on any remote.
        
        Used to determine which local branches have been pushed (have upstream).
        Strips remote prefixes to get just branch names.
        
        Returns:
            Set of branch names (without remote prefix) that exist on remotes
        """
        remote_branches = set()
        try:
            result = self._run_command(
                ["git", "branch", "-r"],
                capture_output=True,
                text=True,
                check=True
            )
            
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    branch = line.strip()
                    # Skip HEAD pointer
                    if '->' in branch:
                        continue
                    # Extract just the branch name (remove remote prefix)
                    if '/' in branch:
                        branch_name = branch.split('/', 1)[1]
                        remote_branches.add(branch_name)
            
        except subprocess.CalledProcessError:
            pass
        
        return remote_branches
    
    def _get_branch_stashes(self, branch_name: str) -> List[Tuple[str, str]]:
        """Get stashes that were created by git-branch-manager from the specified branch.
        
        Only returns stashes with the message "Stashed by git-branch-manager"
        to avoid interfering with user-created stashes.
        
        Args:
            branch_name: Name of the branch to find stashes for
            
        Returns:
            List of tuples containing (stash_ref, stash_message) for matching stashes
        """
        stashes = []
        try:
            # Get all stashes with their branch info
            result = self._run_command(
                ["git", "stash", "list", "--format=%gd|%s"],
                capture_output=True,
                text=True,
                check=True
            )
            
            if result.stdout.strip():
                for line in result.stdout.strip().split('\n'):
                    if '|' in line:
                        stash_ref, message = line.split('|', 1)
                        # Only match stashes created by git-branch-manager
                        # Format: "On branch_name: Stashed by git-branch-manager"
                        if f"On {branch_name}: Stashed by git-branch-manager" in message:
                            stashes.append((stash_ref, message))
            
        except subprocess.CalledProcessError:
            pass
        
        return stashes
    
    def _get_merged_branches_set(self, base_branch: str) -> set:
        """Get a set of all branch names that have been merged into the base branch.
        
        Uses git branch --merged to find branches whose tips are reachable
        from the specified base branch.
        
        Args:
            base_branch: Branch to check merge status against (typically main/master)
            
        Returns:
            Set of branch names that have been merged into base_branch
        """
        merged_branches = set()
        try:
            # Get branches merged into the base branch
            result = self._run_command(
                ["git", "branch", "--merged", base_branch],
                capture_output=True,
                text=True,
                check=True
            )
            
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    branch = line.strip()
                    # Remove the * prefix for current branch
                    if branch.startswith('* '):
                        branch = branch[2:]
                    merged_branches.add(branch)
            
        except subprocess.CalledProcessError:
            pass
        
        return merged_branches
    
    def _get_branch_commit_counts(self, branch_name: str, base_branch: str) -> Tuple[int, int]:
        """Get the number of commits a branch is ahead/behind relative to base branch.
        
        Uses git rev-list to efficiently count commits without fetching full content.
        
        Args:
            branch_name: The branch to compare
            base_branch: The base branch to compare against (typically main/master)
            
        Returns:
            Tuple of (commits_ahead, commits_behind)
        """
        if branch_name == base_branch:
            return (0, 0)
        
        try:
            result = self._run_command(
                ["git", "rev-list", "--left-right", "--count", f"{base_branch}...{branch_name}"],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Output format is "behind\tahead"
            parts = result.stdout.strip().split('\t')
            if len(parts) == 2:
                behind = int(parts[0])
                ahead = int(parts[1])
                return (ahead, behind)
        except (subprocess.CalledProcessError, ValueError):
            pass
        
        return (0, 0)
    
    def safe_addstr(self, stdscr, y: int, x: int, text: str, attr: int = 0) -> int:
        """Safely add string to screen, truncating if necessary.
        
        Prevents curses errors when trying to write beyond screen boundaries.
        Truncates text to fit within available space.
        
        Args:
            stdscr: Curses screen object
            y: Y coordinate (row)
            x: X coordinate (column)
            text: Text to display
            attr: Optional curses attribute (color pair, bold, etc.)
            
        Returns:
            New x position after adding the text
        """
        height, width = stdscr.getmaxyx()
        if y >= height or x >= width:
            return x
        
        # Calculate available space
        available = width - x - 1  # Leave 1 char margin
        if available <= 0:
            return x
        
        # Truncate text if needed
        if len(text) > available:
            text = text[:available]
        
        try:
            if attr:
                stdscr.attron(attr)
            stdscr.addstr(y, x, text)
            if attr:
                stdscr.attroff(attr)
        except curses.error:
            pass
        
        return x + len(text)
    
    def draw_header(self, stdscr, width: int) -> int:
        """Draw the header with title, directory, and status information.
        
        Creates a clean, organized header with:
        - Title bar with app name
        - Directory and repository info
        - Active filters and status indicators
        
        Args:
            stdscr: Curses screen object
            width: Terminal width
            
        Returns:
            Y position after header (where content should start)
        """
        # Get shortened working directory for display
        cwd = self.working_dir
        home = os.path.expanduser('~')
        if cwd.startswith(home):
            cwd = '~' + cwd[len(home):]
        
        # Check if we're in a worktree
        worktree_info = ""
        try:
            # Check if this is a worktree
            result = self._run_command(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0 and result.stdout:
                git_dir = result.stdout.strip()
                # Check if it's a worktree by looking for .git file (not directory)
                git_path = os.path.join(git_dir, '.git')
                if os.path.isfile(git_path):
                    worktree_info = " [worktree]"
        except:
            pass
        
        # Line 0: Title bar with directory
        title = "Git Branch Manager"
        title_with_dir = f" {title} • {cwd}{worktree_info}"
        
        # Truncate if too long, keeping the title visible
        max_left_side = width - 25  # Reserve space for version and help
        if len(title_with_dir) > max_left_side:
            # Keep title, truncate directory
            title_part = f" {title} • "
            available_for_dir = max_left_side - len(title_part) - 3
            if available_for_dir > 0:
                truncated_dir = "..." + cwd[-(available_for_dir):]
                title_with_dir = f"{title_part}{truncated_dir}{worktree_info}"
            else:
                title_with_dir = f" {title}"[:max_left_side]
        
        # Right-align version and help hint
        version = "v1.0"
        right_text = f"{version} • Press ? for help "
        padding = width - len(title_with_dir) - len(right_text)
        if padding > 0:
            title_bar = title_with_dir + " " * padding + right_text
        else:
            # If no room, just show the left side
            title_bar = title_with_dir[:width-1]
        
        # Draw title bar with inverted colors
        try:
            stdscr.attron(curses.color_pair(9))
            stdscr.addstr(0, 0, " " * (width - 1))  # Clear line
            stdscr.addstr(0, 0, title_bar[:width-1])
            stdscr.attroff(curses.color_pair(9))
        except curses.error:
            pass
        
        # Line 1: Status indicators (only show if there are any)
        current_y = 1
        status_items = []
        if self.show_remotes:
            status_items.append("Remotes: ON")
        if self.last_stash_ref:
            status_items.append(f"Stash: {self.last_stash_ref}")
        
        if status_items:
            status_line = " • ".join(status_items)
            if len(status_line) > width - 1:
                status_line = status_line[:width-4] + "..."
            
            try:
                stdscr.addstr(current_y, 0, status_line[:width-1], curses.color_pair(8))
            except curses.error:
                pass
            current_y += 1
        
        # Active filters (if any)
        filters = []
        if self.search_filter:
            filters.append(f"Search: {self.search_filter}")
        if self.author_filter:
            filters.append("Author: me")
        if self.age_filter:
            filters.append("Age: <3 months")
        if self.prefix_filter:
            filters.append(f"Prefix: {self.prefix_filter}")
        if self.merged_filter:
            filters.append("Hiding: merged")
        
        if filters:
            filter_line = f"Filters: {' • '.join(filters)}"
            if len(filter_line) > width - 1:
                filter_line = filter_line[:width-4] + "..."
            try:
                stdscr.addstr(current_y, 0, filter_line[:width-1], curses.color_pair(3))
            except curses.error:
                pass
            current_y += 1
        
        # Separator line with branch count
        separator = "─" * (width - 1)
        
        # Add branch count to separator if there's room
        branch_count_text = f" {len(self.filtered_branches)} branches "
        if len(self.branches) != len(self.filtered_branches):
            branch_count_text = f" {len(self.filtered_branches)}/{len(self.branches)} branches "
        
        if len(branch_count_text) + 10 < width:
            # Insert branch count in the middle of separator
            mid_point = (width - len(branch_count_text)) // 2
            separator = separator[:mid_point] + branch_count_text + separator[mid_point + len(branch_count_text):]
        
        try:
            stdscr.addstr(current_y, 0, separator[:width-1], curses.color_pair(8))
        except curses.error:
            pass
        
        # Return the Y position where content should start
        return current_y + 2  # +1 for separator, +1 for spacing
    
    def draw_footer(self, stdscr, height: int, width: int) -> None:
        """Draw the fixed footer with command shortcuts.
        
        Creates a nano/micro-style footer with commonly used commands.
        Adapts to terminal width by showing more or fewer commands.
        
        Args:
            stdscr: Curses screen object
            height: Terminal height
            width: Terminal width
        """
        # Footer position (bottom two lines)
        separator_y = height - 2
        footer_y = height - 1
        
        # Draw separator line with proper box drawing characters
        try:
            # Use box drawing characters for a more professional look
            separator_line = "─" * (width - 1)
            stdscr.addstr(separator_y, 0, separator_line, curses.color_pair(8))
        except curses.error:
            pass
        
        # Define footer commands
        # Format: (key display, command name, condition for showing)
        all_commands = [
            ("?", "Help", True),
            ("q", "Exit", True),
            ("↵", "Checkout", len(self.filtered_branches) > 0),
            ("t", "Remote", True),
            ("r", "Refresh", True),
            ("N", "New", True),
            ("D", "Delete", len(self.filtered_branches) > 0 and not self.show_remotes),
            ("b", "Browser", self.url_builder is not None),
            ("/", "Search", True),
            ("S", "Pop Stash", self.last_stash_ref is not None),
            ("f", "Fetch", True),
            ("a", "Author", True),
        ]
        
        # Filter commands based on conditions
        commands = [(k, c) for k, c, show in all_commands if show]
        
        # Build footer text
        footer_parts = []
        for key, cmd in commands:
            footer_parts.append(f"{key} {cmd}")
        
        # Join with spacing
        footer_text = "  ".join(footer_parts)
        
        # Truncate if too long
        if len(footer_text) > width - 2:
            # Show only the most important commands
            essential_commands = commands[:6]  # First 6 commands
            footer_parts = [f"{k} {c}" for k, c in essential_commands]
            footer_text = "  ".join(footer_parts)
            if len(footer_text) > width - 2:
                footer_text = footer_text[:width - 5] + "..."
        
        # Draw footer with color
        try:
            stdscr.attron(curses.color_pair(9))
            # Clear the line first
            stdscr.addstr(footer_y, 0, " " * (width - 1))
            # Center the text
            x_start = (width - len(footer_text)) // 2
            if x_start < 0:
                x_start = 1
            stdscr.addstr(footer_y, x_start, footer_text)
            stdscr.attroff(curses.color_pair(9))
        except curses.error:
            pass
    
    def _run_command_with_spinner(self, stdscr, command: List[str], message: str, **kwargs) -> subprocess.CompletedProcess:
        """Run a command while showing an animated spinner.
        
        Executes a subprocess command in a separate thread while animating
        a spinner in the main thread. Provides visual feedback during
        long-running operations.
        
        Args:
            stdscr: Curses screen object
            command: Command and arguments to execute
            message: Loading message to display with spinner
            **kwargs: Additional arguments passed to subprocess.run
            
        Returns:
            CompletedProcess instance with command results
        """
        # Shared state between threads
        result = [None]  # Use list to allow modification in thread
        exception = [None]
        stop_spinner = threading.Event()
        
        def run_command():
            """Run the command in a separate thread."""
            try:
                result[0] = self._run_command(command, **kwargs)
            except Exception as e:
                exception[0] = e
            finally:
                stop_spinner.set()
        
        # Start command in background thread
        cmd_thread = threading.Thread(target=run_command)
        cmd_thread.start()
        
        # Animate spinner in main thread
        spinner_frame = 0
        stdscr.nodelay(True)  # Make getch non-blocking during animation
        
        try:
            while not stop_spinner.is_set():
                self.show_loading_message(stdscr, message, spinner_frame)
                spinner_frame += 1
                
                # Check for ESC key to cancel
                key = stdscr.getch()
                if key == 27:  # ESC key
                    # Note: We can't easily cancel the git operation
                    # but we can stop showing the spinner
                    break
                
                time.sleep(0.1)  # Update spinner every 100ms
                
                # Check if thread is still alive
                if not cmd_thread.is_alive():
                    break
        finally:
            stdscr.nodelay(False)  # Restore blocking mode
        
        # Ensure thread completes
        cmd_thread.join(timeout=1.0)
        
        # Handle any exceptions from the thread
        if exception[0]:
            raise exception[0]
        
        return result[0]
    
    def show_loading_message(self, stdscr, message: str, spinner_frame: int = 0) -> None:
        """Show a loading message in the center of the screen with spinner.
        
        Clears the screen and displays a centered message with an animated
        spinner, typically used during long-running operations.
        
        Args:
            stdscr: Curses screen object
            message: Loading message to display
            spinner_frame: Frame number for spinner animation (0-7)
        """
        if stdscr:
            stdscr.clear()
            height, width = stdscr.getmaxyx()
            
            # Spinner frames for a smooth animation
            spinners = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧"]
            spinner = spinners[spinner_frame % len(spinners)]
            
            # Combine spinner with message
            display_text = f"{spinner} {message}"
            
            # Center the message
            y = height // 2
            x = (width - len(display_text)) // 2
            
            if x >= 0 and y >= 0:
                try:
                    # Draw the spinner in cyan color
                    stdscr.attron(curses.color_pair(4))
                    stdscr.addstr(y, x, spinner)
                    stdscr.attroff(curses.color_pair(4))
                    
                    # Draw the message
                    stdscr.addstr(y, x + 2, message)
                    
                    # Add a subtle hint below
                    hint = "This may take a moment..."
                    hint_x = (width - len(hint)) // 2
                    if hint_x >= 0 and y + 2 < height:
                        stdscr.addstr(y + 2, hint_x, hint, curses.color_pair(8))
                    
                    stdscr.refresh()
                except curses.error:
                    pass
    
    def get_branches(self, stdscr=None) -> None:
        """Get list of git branches with commit info - optimized version.
        
        Main method for populating the branch list. Collects local and
        optionally remote branches, fetches metadata in batch for performance,
        detects uncommitted changes, upstream status, merge status, and
        worktree status.
        
        Args:
            stdscr: Optional curses screen object for displaying loading message
        """
        try:
            if stdscr:
                self.show_loading_message(stdscr, "Loading branches...")
            # First get the current branch
            current_result = self._run_command(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                check=True
            )
            self.current_branch = current_result.stdout.strip()
            
            self.branches = []
            
            # Collect all branch names first
            all_branches = []
            worktree_branches = set()
            
            # Get local branches
            result = self._run_command(
                ["git", "branch"],
                capture_output=True,
                text=True,
                check=True
            )
            
            lines = result.stdout.strip().split('\n') if result.stdout.strip() else []
            
            for line in lines:
                branch_name = line.strip()
                if branch_name.startswith('* '):
                    branch_name = branch_name[2:]
                elif branch_name.startswith('+ '):
                    # Branch checked out in a worktree
                    branch_name = branch_name[2:]
                    worktree_branches.add(branch_name)
                all_branches.append((branch_name, False, None))  # (name, is_remote, remote_name)
            
            # Get remote branches if enabled
            if self.show_remotes:
                remote_result = self._run_command(
                    ["git", "branch", "-r"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                remote_lines = remote_result.stdout.strip().split('\n') if remote_result.stdout.strip() else []
                
                # First pass: collect local branch names for duplicate checking
                local_branch_names = {b[0] for b in all_branches if not b[1]}
                
                for line in remote_lines:
                    branch_name = line.strip()
                    # Skip HEAD pointer
                    if '->' in branch_name:
                        continue
                    
                    # Parse remote/branch format
                    if '/' in branch_name:
                        parts = branch_name.split('/', 1)
                        remote_name = parts[0]
                        branch_short_name = parts[1]
                        
                        # Skip if this branch exists locally
                        if branch_short_name in local_branch_names:
                            continue
                        
                        all_branches.append((branch_name, True, remote_name))
            
            # Get batch info for all branches
            batch_info = self._get_batch_branch_info(all_branches, worktree_branches)
            
            # Check uncommitted changes once for current branch
            has_uncommitted = False
            if self.current_branch:
                has_uncommitted = self._check_uncommitted_changes_batch()
            
            # Get set of branches that exist on remote
            remote_branch_names = self._get_remote_branches_set()
            
            # Get set of branches that have been merged into main/master
            # Use the configured default base branch, falling back to main or master
            base_branch = self.config.get('default_base_branch', 'main')
            # If configured base doesn't exist, try to find main or master
            all_local_branches = {b[0] for b in all_branches if not b[1]}
            if base_branch not in all_local_branches:
                if 'main' in all_local_branches:
                    base_branch = 'main'
                elif 'master' in all_local_branches:
                    base_branch = 'master'
            
            merged_branch_names = self._get_merged_branches_set(base_branch)
            
            # Build BranchInfo objects
            for branch_name, is_remote, remote_name in all_branches:
                if branch_name in batch_info:
                    info = batch_info[branch_name]
                    
                    # For local branches, check if they exist on remote
                    # For remote branches, they obviously have upstream
                    if is_remote:
                        has_upstream = True
                    else:
                        # Check if this local branch exists on any remote
                        has_upstream = branch_name in remote_branch_names
                    
                    # Check if branch has been merged
                    is_merged = branch_name in merged_branch_names
                    
                    # Get commit counts for local branches only (skip remote branches for performance)
                    commits_ahead = 0
                    commits_behind = 0
                    if not is_remote and base_branch:
                        commits_ahead, commits_behind = self._get_branch_commit_counts(branch_name, base_branch)
                    
                    branch_info = BranchInfo(
                        name=branch_name,
                        is_current=(branch_name == self.current_branch),
                        commit_hash=info['hash'],
                        commit_date=datetime.fromtimestamp(info['timestamp']),
                        commit_message=info['message'],
                        commit_author=info['author'],
                        has_uncommitted_changes=(has_uncommitted if branch_name == self.current_branch else False),
                        is_remote=is_remote,
                        remote_name=remote_name,
                        has_upstream=has_upstream,
                        is_merged=is_merged,
                        in_worktree=(branch_name in worktree_branches) if worktree_branches else False,
                        commits_ahead=commits_ahead,
                        commits_behind=commits_behind
                    )
                    self.branches.append(branch_info)
            
            # Sort branches by commit date (most recent first)
            self.branches.sort(key=lambda b: b.commit_date, reverse=True)
            
            # Apply filters
            self._apply_filters()
                    
        except subprocess.CalledProcessError as e:
            print(f"Error getting branches: {e}")
            sys.exit(1)
            
    def _apply_filters(self) -> None:
        """Apply all active filters to the branch list.
        
        Filters are applied in sequence:
        1. Search filter (name substring match)
        2. Author filter (current user's branches only)
        3. Age filter (hide branches older than 3 months)
        4. Prefix filter (branches starting with specified prefix)
        5. Merged filter (hide branches merged into main/master)
        
        Updates self.filtered_branches with the filtered results.
        """
        self.filtered_branches = self.branches[:]
        
        # Search filter (name substring)
        if self.search_filter:
            self.filtered_branches = [
                b for b in self.filtered_branches 
                if self.search_filter.lower() in b.name.lower()
            ]
        
        # Author filter
        if self.author_filter and self.current_user:
            self.filtered_branches = [
                b for b in self.filtered_branches 
                if b.commit_author == self.current_user
            ]
        
        # Age filter (hide old branches > 3 months)
        if self.age_filter:
            three_months_ago = datetime.now() - timedelta(days=90)
            self.filtered_branches = [
                b for b in self.filtered_branches 
                if b.commit_date >= three_months_ago
            ]
        
        # Prefix filter
        if self.prefix_filter:
            self.filtered_branches = [
                b for b in self.filtered_branches 
                if b.name.startswith(self.prefix_filter)
            ]
        
        # Merged filter (hide merged branches)
        if self.merged_filter:
            self.filtered_branches = [
                b for b in self.filtered_branches 
                if not b.is_merged or b.is_current
            ]
        
        # Adjust selected index if it's out of bounds
        if self.selected_index >= len(self.filtered_branches):
            self.selected_index = max(0, len(self.filtered_branches) - 1)
            
    def stash_changes(self) -> bool:
        """Stash current changes if any exist.
        
        Creates a stash with the message "Stashed by git-branch-manager"
        and tracks the stash reference for later recovery.
        
        Returns:
            True if changes were stashed successfully, False if no changes
            to stash or if stashing failed
        """
        try:
            # Check if there are any changes to stash
            status_result = self._run_command(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=True
            )
            
            if status_result.stdout.strip():
                # There are changes, stash them
                stash_result = self._run_command(
                    ["git", "stash", "push", "-m", "Stashed by git-branch-manager"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                # Extract stash reference from output
                if "Saved working directory" in stash_result.stdout:
                    # Get the stash reference (usually stash@{0})
                    stash_list = self._run_command(
                        ["git", "stash", "list", "-1"],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    if stash_list.stdout:
                        self.last_stash_ref = stash_list.stdout.split(':')[0]
                return True
            return False
            
        except subprocess.CalledProcessError as e:
            print(f"Error stashing changes: {e}")
            return False
            
    def checkout_branch(self, branch: str, is_remote: bool = False) -> bool:
        """Checkout the specified branch.
        
        For remote branches, creates a local tracking branch if it doesn't
        already exist. For local branches, performs a standard checkout.
        
        Args:
            branch: Name of the branch to checkout
            is_remote: Whether this is a remote branch (e.g., origin/feature)
            
        Returns:
            True if checkout succeeded, False on error
        """
        try:
            if is_remote and '/' in branch:
                # For remote branches, create a local tracking branch
                parts = branch.split('/', 1)
                local_branch_name = parts[1]
                
                # Check if local branch already exists
                check_result = self._run_command(
                    ["git", "rev-parse", "--verify", local_branch_name],
                    capture_output=True,
                    check=False
                )
                
                if check_result.returncode == 0:
                    # Local branch exists, just check it out
                    self._run_command(
                        ["git", "checkout", local_branch_name],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                else:
                    # Create new tracking branch
                    self._run_command(
                        ["git", "checkout", "-b", local_branch_name, branch],
                        capture_output=True,
                        text=True,
                        check=True
                    )
            else:
                self._run_command(
                    ["git", "checkout", branch],
                    capture_output=True,
                    text=True,
                    check=True
                )
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error checking out branch {branch}: {e}")
            return False
            
    def delete_branch(self, branch: str) -> bool:
        """Delete the specified branch.
        
        Attempts a safe delete first (git branch -d), then falls back
        to force delete (git branch -D) if the branch has unmerged changes.
        
        Args:
            branch: Name of the branch to delete
            
        Returns:
            True if deletion succeeded, False if both attempts failed
        """
        try:
            self._run_command(
                ["git", "branch", "-d", branch],
                capture_output=True,
                text=True,
                check=True
            )
            return True
        except subprocess.CalledProcessError as e:
            # Try force delete if regular delete fails
            try:
                self._run_command(
                    ["git", "branch", "-D", branch],
                    capture_output=True,
                    text=True,
                    check=True
                )
                return True
            except subprocess.CalledProcessError:
                return False
                
    def move_branch(self, old_name: str, new_name: str) -> bool:
        """Move/rename a branch.
        
        Uses git branch -m to rename a branch. Works for both local
        and the current branch.
        
        Args:
            old_name: Current name of the branch
            new_name: New name for the branch
            
        Returns:
            True if rename succeeded, False on error
        """
        try:
            self._run_command(
                ["git", "branch", "-m", old_name, new_name],
                capture_output=True,
                text=True,
                check=True
            )
            return True
        except subprocess.CalledProcessError:
            return False
            
    def show_input_dialog(self, stdscr, prompt: str, initial_value: str = "") -> Optional[str]:
        """Show an input dialog to get text from user."""
        height, width = stdscr.getmaxyx()
        
        # Calculate dialog dimensions
        dialog_width = min(60, width - 4)
        dialog_height = 6
        start_y = (height - dialog_height) // 2
        start_x = (width - dialog_width) // 2
        
        # Create dialog window
        dialog = curses.newwin(dialog_height, dialog_width, start_y, start_x)
        dialog.box()
        
        # Add prompt
        dialog.addstr(2, 2, prompt[:dialog_width - 4])
        
        # Create input field
        input_y = 3
        input_x = 2
        input_width = dialog_width - 4
        
        # Initialize with initial value
        user_input = initial_value
        cursor_pos = len(user_input)
        
        # Enable cursor
        curses.curs_set(1)
        
        while True:
            # Display current input
            dialog.move(input_y, input_x)
            dialog.clrtoeol()
            dialog.addstr(input_y, input_x, user_input[:input_width - 1])
            
            # Position cursor
            if cursor_pos < input_width - 1:
                dialog.move(input_y, input_x + cursor_pos)
            
            # Draw border again (clrtoeol might have erased it)
            dialog.box()
            dialog.addstr(2, 2, prompt[:dialog_width - 4])
            
            dialog.refresh()
            
            # Get key
            key = dialog.getch()
            
            if key == ord('\n') or key == curses.KEY_ENTER:
                curses.curs_set(0)  # Hide cursor
                return user_input if user_input else None
            elif key == 27:  # ESC
                curses.curs_set(0)  # Hide cursor
                return None
            elif key == curses.KEY_BACKSPACE or key == 127:
                if cursor_pos > 0:
                    user_input = user_input[:cursor_pos-1] + user_input[cursor_pos:]
                    cursor_pos -= 1
            elif key == curses.KEY_LEFT:
                if cursor_pos > 0:
                    cursor_pos -= 1
            elif key == curses.KEY_RIGHT:
                if cursor_pos < len(user_input):
                    cursor_pos += 1
            elif key == curses.KEY_HOME:
                cursor_pos = 0
            elif key == curses.KEY_END:
                cursor_pos = len(user_input)
            elif 32 <= key <= 126:  # Printable characters
                user_input = user_input[:cursor_pos] + chr(key) + user_input[cursor_pos:]
                cursor_pos += 1
    
    def show_help(self, stdscr) -> None:
        """Show help screen with all commands.
        
        Displays a scrollable help screen listing all keyboard shortcuts,
        visual indicators, and features. Supports scrolling with arrow keys.
        
        Args:
            stdscr: Curses screen object
        """
        height, width = stdscr.getmaxyx()
        
        help_text = [
            ("Git Branch Manager - Help", curses.A_BOLD),
            ("=" * 30, 0),
            ("", 0),
            ("Navigation:", curses.A_BOLD),
            ("  ↑/↓        Navigate through branches", 0),
            ("  PgUp/PgDn  Navigate by page", 0),
            ("  Home/End   Jump to first/last branch", 0),
            ("  q          Quit", 0),
            ("  ESC        Clear filters (or quit if no filters)", 0),
            ("  ?          Show this help", 0),
            ("", 0),
            ("Branch Operations:", curses.A_BOLD),
            ("  Enter      Checkout selected branch", 0),
            ("  D          Delete selected branch", 0),
            ("  M          Rename/move selected branch", 0),
            ("  N          Create new branch from current", 0),
            ("", 0),
            ("Stash Management:", curses.A_BOLD),
            ("  S          Pop last stash (if available)", 0),
            ("  Auto-detect Branch stashes detected when switching branches", 0),
            ("", 0),
            ("View Options:", curses.A_BOLD),
            ("  r          Reload branch list", 0),
            ("  t          Toggle remote branches (auto-fetches)", 0),
            ("  f          Fetch latest from remote", 0),
            ("  b          Open branch in browser", 0),
            ("  B          Open branch comparison/PR in browser", 0),
            ("", 0),
            ("Filtering:", curses.A_BOLD),
            ("  /          Search branches by name", 0),
            ("  a          Toggle author filter (show only your branches)", 0),
            ("  o          Toggle old branches filter (hide >3 months)", 0),
            ("  m          Toggle merged filter (hide merged branches)", 0),
            ("  p          Filter by prefix (feature/, bugfix/, etc)", 0),
            ("  c          Clear all filters", 0),
            ("", 0),
            ("Status Indicators:", curses.A_BOLD),
            ("  *          Current branch", 0),
            ("  ↓          Remote branch", 0),
            ("  [modified] Uncommitted changes", 0),
            ("  [unpushed] Local branch not on remote", 0),
            ("  [merged]   Branch merged into main/master", 0),
            ("  [worktree] Branch checked out in worktree", 0),
            ("  [+N]       N commits ahead of main/master", 0),
            ("  [-N]       N commits behind main/master", 0),
            ("  [+N/-M]    N ahead and M behind main/master", 0),
            ("", 0),
            ("Color Coding:", curses.A_BOLD),
            ("  Green      Current branch, [+N] ahead only", 0),
            ("  Cyan       Branch names", 0),
            ("  Yellow     Modified indicator, [-N] behind only", 0),
            ("  Magenta    Recent commits (<1 week), [+N/-M] mixed", 0),
            ("  Blue       Commit hashes", 0),
            ("  Red        Old branches (>1 month)", 0),
            ("", 0),
            ("↑/↓ to scroll, any other key to return...", curses.A_BOLD),
        ]
        
        # Scrolling support
        scroll_offset = 0
        max_scroll = max(0, len(help_text) - (height - 2))
        
        while True:
            stdscr.clear()
            
            # Display help text with scrolling
            visible_lines = height - 2  # Leave room for borders
            start_x = max(5, (width - 60) // 2)  # Left margin of 5, or centered if narrow screen
            
            for i in range(visible_lines):
                line_idx = i + scroll_offset
                if line_idx < len(help_text):
                    text, attr = help_text[line_idx]
                    y_pos = i + 1
                    
                    if y_pos < height - 1:
                        try:
                            if attr:
                                stdscr.attron(attr)
                            stdscr.addstr(y_pos, start_x, text[:width - start_x - 1])
                            if attr:
                                stdscr.attroff(attr)
                        except curses.error:
                            pass
            
            # Show scroll indicator if needed
            if max_scroll > 0:
                scroll_pct = int((scroll_offset / max_scroll) * 100) if max_scroll > 0 else 0
                scroll_msg = f"[{scroll_pct}%]"
                try:
                    stdscr.addstr(0, width - len(scroll_msg) - 2, scroll_msg)
                except curses.error:
                    pass
            
            stdscr.refresh()
            
            # Handle key input
            key = stdscr.getch()
            if key == curses.KEY_UP:
                scroll_offset = max(0, scroll_offset - 1)
            elif key == curses.KEY_DOWN:
                scroll_offset = min(max_scroll, scroll_offset + 1)
            elif key == curses.KEY_PPAGE:  # Page Up
                scroll_offset = max(0, scroll_offset - visible_lines)
            elif key == curses.KEY_NPAGE:  # Page Down
                scroll_offset = min(max_scroll, scroll_offset + visible_lines)
            elif key == curses.KEY_HOME:  # Home
                scroll_offset = 0
            elif key == curses.KEY_END:  # End
                scroll_offset = max_scroll
            else:
                break
    
    def show_platform_config_help(self, stdscr) -> None:
        """Show help for configuring Git platform integration.
        
        Displays detailed instructions for setting up browser integration
        with various Git hosting platforms. Includes example configurations
        and URL patterns. Supports scrolling.
        
        Args:
            stdscr: Curses screen object
        """
        height, width = stdscr.getmaxyx()
        
        config_path = self._get_config_path()
        remote_url = "Not found"
        try:
            result = self._run_command(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                remote_url = result.stdout.strip()
        except:
            pass
        
        help_lines = [
            "Git Platform Configuration Help",
            "=" * 40,
            "",
            f"Current remote URL: {remote_url}",
            f"Detected platform: {self.url_builder.platform if self.url_builder else 'None'}",
            "",
            f"You can configure your settings at:",
            f"{config_path}",
            "",
            "Example configuration file:",
            "{",
            '  "platform": "bitbucket-server",  // or auto, github, gitlab, etc.',
            '  "default_base_branch": "main",',
            '  "browser_command": "open",',
            '  "custom_patterns": {',
            '    "branch": "https://git.example.com/{repo}/tree/{branch}",',
            '    "compare": "https://git.example.com/{repo}/compare/{base}...{branch}"',
            '  }',
            "}",
            "",
            "Supported platforms and URL patterns:",
            "",
            "GitHub:",
            "  branch:  https://github.com/{owner}/{repo}/tree/{branch}",
            "  compare: https://github.com/{owner}/{repo}/compare/{base}...{branch}",
            "",
            "GitLab:",
            "  branch:  https://gitlab.com/{owner}/{repo}/-/tree/{branch}",
            "  compare: https://gitlab.com/{owner}/{repo}/-/compare/{base}...{branch}",
            "",
            "Bitbucket Cloud:",
            "  branch:  https://bitbucket.org/{workspace}/{repo}/branch/{branch}",
            "  compare: https://bitbucket.org/{workspace}/{repo}/pull-requests/new",
            "           ?source={branch}&dest={base}",
            "",
            "Bitbucket Server:",
            "  branch:  https://{domain}/projects/{project}/repos/{repo}/browse",
            "           ?at=refs/heads/{branch}",
            "  compare: https://{domain}/projects/{project}/repos/{repo}/compare/commits",
            "           ?sourceBranch=refs/heads/{branch}&targetBranch=refs/heads/{base}",
            "",
            "↑/↓ to scroll, any other key to return..."
        ]
        
        # Scrolling support
        scroll_offset = 0
        max_scroll = max(0, len(help_lines) - (height - 2))
        
        while True:
            stdscr.clear()
            
            # Display help with scrolling
            footer_height = 2  # Account for footer
            visible_lines = height - footer_height - 2  # Leave room for borders and footer
            for i in range(visible_lines):
                line_idx = i + scroll_offset
                if line_idx < len(help_lines):
                    line = help_lines[line_idx]
                    y_pos = i + 1
                    
                    if y_pos < height - 1:
                        try:
                            if line_idx == 0:  # Title
                                stdscr.attron(curses.A_BOLD)
                                stdscr.addstr(y_pos, 2, line[:width - 4])
                                stdscr.attroff(curses.A_BOLD)
                            elif line.startswith("Supported platforms") or (line.endswith(":") and not line.startswith(" ")):
                                stdscr.attron(curses.A_BOLD)
                                stdscr.addstr(y_pos, 2, line[:width - 4])
                                stdscr.attroff(curses.A_BOLD)
                            else:
                                stdscr.addstr(y_pos, 2, line[:width - 4])
                        except curses.error:
                            pass
            
            # Show scroll indicator if needed
            if max_scroll > 0:
                scroll_pct = int((scroll_offset / max_scroll) * 100) if max_scroll > 0 else 0
                scroll_msg = f"[{scroll_pct}%]"
                try:
                    stdscr.addstr(0, width - len(scroll_msg) - 2, scroll_msg)
                except curses.error:
                    pass
            
            stdscr.refresh()
            
            # Handle key input
            key = stdscr.getch()
            if key == curses.KEY_UP:
                scroll_offset = max(0, scroll_offset - 1)
            elif key == curses.KEY_DOWN:
                scroll_offset = min(max_scroll, scroll_offset + 1)
            elif key == curses.KEY_PPAGE:  # Page Up
                scroll_offset = max(0, scroll_offset - visible_lines)
            elif key == curses.KEY_NPAGE:  # Page Down
                scroll_offset = min(max_scroll, scroll_offset + visible_lines)
            elif key == curses.KEY_HOME:  # Home
                scroll_offset = 0
            elif key == curses.KEY_END:  # End
                scroll_offset = max_scroll
            else:
                break
    
    def show_confirmation_dialog(self, stdscr, message: str) -> Optional[str]:
        """Show a confirmation dialog with yes/no/cancel options.
        
        Creates a centered dialog box with the provided message and
        waits for user input (y/n/ESC).
        
        Args:
            stdscr: Curses screen object
            message: Confirmation message to display (supports newlines)
            
        Returns:
            'yes' if Y pressed, 'no' if N pressed, 'cancel' if ESC pressed
        """
        height, width = stdscr.getmaxyx()
        
        # Calculate dialog dimensions
        dialog_width = min(60, width - 4)
        dialog_height = 7
        start_y = (height - dialog_height) // 2
        start_x = (width - dialog_width) // 2
        
        # Create dialog window
        dialog = curses.newwin(dialog_height, dialog_width, start_y, start_x)
        dialog.box()
        
        # Add message
        lines = message.split('\n')
        for i, line in enumerate(lines[:2]):  # Show max 2 lines
            dialog.addstr(2 + i, 2, line[:dialog_width - 4])
        
        # Options
        options = ["[Y]es", "[N]o", "[C]ancel"]
        option_y = dialog_height - 2
        total_width = sum(len(opt) for opt in options) + 6
        start_opt_x = (dialog_width - total_width) // 2
        
        x = start_opt_x
        for opt in options:
            dialog.addstr(option_y, x, opt)
            x += len(opt) + 3
        
        dialog.refresh()
        
        # Wait for user input
        while True:
            key = dialog.getch()
            if key in [ord('y'), ord('Y')]:
                return 'yes'
            elif key in [ord('n'), ord('N')]:
                return 'no'
            elif key in [ord('c'), ord('C'), 27]:  # 27 is ESC
                return 'cancel'
    
    def run(self, stdscr) -> None:
        """Main curses UI loop.
        
        Initializes the terminal UI, sets up colors, fetches branches,
        and handles all keyboard input. Runs until user quits.
        
        Args:
            stdscr: Curses screen object (provided by curses.wrapper)
        """
        # Initialize curses
        curses.curs_set(0)  # Hide cursor
        stdscr.nodelay(False)  # Wait for key press
        
        # Set up colors
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Selected
        curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)  # Current branch
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Modified indicator
        curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)  # Branch name
        curses.init_pair(5, curses.COLOR_MAGENTA, curses.COLOR_BLACK)  # Recent branches (< 1 week)
        curses.init_pair(6, curses.COLOR_BLUE, curses.COLOR_BLACK)  # Hash
        curses.init_pair(7, curses.COLOR_RED, curses.COLOR_BLACK)  # Old branches (> 1 month)
        curses.init_pair(8, curses.COLOR_WHITE, curses.COLOR_BLACK)  # Normal text
        curses.init_pair(9, curses.COLOR_BLACK, curses.COLOR_CYAN)  # Footer
        
        self.get_branches(stdscr)
        
        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()
            
            # Draw header and get content start position
            start_y = self.draw_header(stdscr, width)
            
            # Display branches
            footer_height = 2  # Footer takes 2 lines (separator + commands)
            visible_branches = min(height - start_y - footer_height - 1, len(self.filtered_branches))
            
            # Calculate scroll position
            if self.selected_index >= visible_branches:
                scroll_offset = self.selected_index - visible_branches + 1
            else:
                scroll_offset = 0
                
            for i in range(visible_branches):
                branch_index = i + scroll_offset
                if branch_index >= len(self.filtered_branches):
                    break
                    
                branch_info = self.filtered_branches[branch_index]
                y = start_y + i
                
                # Prepare display components
                if branch_info.is_current:
                    prefix = "* "
                elif branch_info.is_remote:
                    prefix = "↓ "  # Down arrow for remote branches
                else:
                    prefix = "  "
                relative_date = branch_info.format_relative_date()
                
                # Determine age-based color for branch
                days_old = (datetime.now() - branch_info.commit_date).days
                if days_old < 7:
                    date_color = 5  # Magenta for recent
                elif days_old > 30:
                    date_color = 7  # Red for old
                else:
                    date_color = 8  # White for normal
                
                # Prepare status indicators
                separator = " • "
                modified_indicator = " [modified]" if branch_info.has_uncommitted_changes else ""
                # Add unpushed indicator for local branches
                unpushed_indicator = ""
                if not branch_info.is_remote and not branch_info.has_upstream:
                    unpushed_indicator = " [unpushed]"
                # Add merged indicator
                merged_indicator = ""
                if branch_info.is_merged and not branch_info.is_current and not branch_info.is_remote:
                    merged_indicator = " [merged]"
                # Add worktree indicator
                worktree_indicator = ""
                if branch_info.in_worktree and not branch_info.is_current:
                    worktree_indicator = " [worktree]"
                # Add commit count indicators
                commit_count_indicator = ""
                if not branch_info.is_remote:
                    if branch_info.commits_ahead > 0 and branch_info.commits_behind > 0:
                        commit_count_indicator = f" [+{branch_info.commits_ahead}/-{branch_info.commits_behind}]"
                    elif branch_info.commits_ahead > 0:
                        commit_count_indicator = f" [+{branch_info.commits_ahead}]"
                    elif branch_info.commits_behind > 0:
                        commit_count_indicator = f" [-{branch_info.commits_behind}]"
                
                # Calculate available space for commit message
                fixed_len = len(prefix) + len(branch_info.name) + len(modified_indicator) + len(unpushed_indicator) + len(merged_indicator) + len(worktree_indicator) + len(commit_count_indicator) + len(separator) * 3 + len(relative_date) + len(branch_info.commit_hash)
                max_msg_len = width - fixed_len - 1
                commit_msg = branch_info.commit_message
                if len(commit_msg) > max_msg_len and max_msg_len > 3:
                    commit_msg = commit_msg[:max_msg_len-3] + "..."
                
                # Display with colors
                x_pos = 0
                
                if branch_index == self.selected_index:
                    # Selected row - inverse video
                    stdscr.attron(curses.color_pair(1))
                    try:
                        stdscr.addstr(y, 0, " " * (width - 1))  # Fill background
                    except curses.error:
                        pass
                    x_pos = self.safe_addstr(stdscr, y, x_pos, prefix)
                    x_pos = self.safe_addstr(stdscr, y, x_pos, branch_info.name)
                    if modified_indicator:
                        x_pos = self.safe_addstr(stdscr, y, x_pos, modified_indicator)
                    if unpushed_indicator:
                        x_pos = self.safe_addstr(stdscr, y, x_pos, unpushed_indicator)
                    if merged_indicator:
                        x_pos = self.safe_addstr(stdscr, y, x_pos, merged_indicator)
                    if worktree_indicator:
                        x_pos = self.safe_addstr(stdscr, y, x_pos, worktree_indicator)
                    if commit_count_indicator:
                        x_pos = self.safe_addstr(stdscr, y, x_pos, commit_count_indicator)
                    x_pos = self.safe_addstr(stdscr, y, x_pos, separator)
                    x_pos = self.safe_addstr(stdscr, y, x_pos, relative_date)
                    x_pos = self.safe_addstr(stdscr, y, x_pos, separator)
                    x_pos = self.safe_addstr(stdscr, y, x_pos, branch_info.commit_hash)
                    x_pos = self.safe_addstr(stdscr, y, x_pos, separator)
                    x_pos = self.safe_addstr(stdscr, y, x_pos, commit_msg)
                    stdscr.attroff(curses.color_pair(1))
                else:
                    # Non-selected rows with colors
                    x_pos = self.safe_addstr(stdscr, y, x_pos, prefix)
                    
                    # Branch name color
                    if branch_info.is_current:
                        x_pos = self.safe_addstr(stdscr, y, x_pos, branch_info.name, curses.color_pair(2))
                    else:
                        x_pos = self.safe_addstr(stdscr, y, x_pos, branch_info.name, curses.color_pair(4))
                    
                    # Modified indicator
                    if modified_indicator:
                        x_pos = self.safe_addstr(stdscr, y, x_pos, modified_indicator, curses.color_pair(3))
                    
                    # Unpushed indicator
                    if unpushed_indicator:
                        x_pos = self.safe_addstr(stdscr, y, x_pos, unpushed_indicator, curses.color_pair(3))
                    
                    # Merged indicator - use green color
                    if merged_indicator:
                        x_pos = self.safe_addstr(stdscr, y, x_pos, merged_indicator, curses.color_pair(2))
                    
                    # Worktree indicator - use cyan color
                    if worktree_indicator:
                        x_pos = self.safe_addstr(stdscr, y, x_pos, worktree_indicator, curses.color_pair(4))
                    
                    # Commit count indicator - use different colors for ahead/behind
                    if commit_count_indicator:
                        if branch_info.commits_ahead > 0 and branch_info.commits_behind == 0:
                            # Only ahead - green
                            x_pos = self.safe_addstr(stdscr, y, x_pos, commit_count_indicator, curses.color_pair(2))
                        elif branch_info.commits_behind > 0 and branch_info.commits_ahead == 0:
                            # Only behind - yellow
                            x_pos = self.safe_addstr(stdscr, y, x_pos, commit_count_indicator, curses.color_pair(3))
                        else:
                            # Both ahead and behind - magenta
                            x_pos = self.safe_addstr(stdscr, y, x_pos, commit_count_indicator, curses.color_pair(5))
                    
                    x_pos = self.safe_addstr(stdscr, y, x_pos, separator)
                    
                    # Date with age-based color
                    x_pos = self.safe_addstr(stdscr, y, x_pos, relative_date, curses.color_pair(date_color))
                    
                    x_pos = self.safe_addstr(stdscr, y, x_pos, separator)
                    
                    # Commit hash
                    x_pos = self.safe_addstr(stdscr, y, x_pos, branch_info.commit_hash, curses.color_pair(6))
                    
                    x_pos = self.safe_addstr(stdscr, y, x_pos, separator)
                    
                    # Commit message
                    x_pos = self.safe_addstr(stdscr, y, x_pos, commit_msg)
            
            # Add scroll indicator if needed
            if len(self.filtered_branches) > visible_branches:
                scroll_pos = self.selected_index / max(1, len(self.filtered_branches) - 1)
                scroll_pct = int(scroll_pos * 100)
                scroll_msg = f"[{self.selected_index + 1}/{len(self.filtered_branches)}]"
                try:
                    # Show in top right corner
                    stdscr.addstr(0, width - len(scroll_msg) - 1, scroll_msg, curses.color_pair(9))
                except curses.error:
                    pass
            
            # Draw footer
            self.draw_footer(stdscr, height, width)
            
            stdscr.refresh()
            
            # Handle key press
            key = stdscr.getch()
            
            if key == ord('q') or key == ord('Q'):
                break
            elif key == 27:  # ESC key
                # If filters are active, clear them instead of quitting
                if self.has_active_filters():
                    self.clear_all_filters()
                else:
                    break
            elif key == ord('?'):  # Show help
                self.show_help(stdscr)
            elif key == ord('t') or key == ord('T'):  # Toggle remote branches
                # Fetch from remote before toggling
                if not self.show_remotes:  # Only fetch when turning remotes ON
                    try:
                        # Use animated spinner for fetch
                        self._run_command_with_spinner(
                            stdscr,
                            ["git", "fetch", "--all"],
                            "Fetching from remote...",
                            capture_output=True,
                            text=True,
                            check=True
                        )
                    except subprocess.CalledProcessError as e:
                        stdscr.clear()
                        stdscr.addstr(0, 0, f"Fetch failed: {e}")
                        stdscr.addstr(1, 0, "Press any key to continue...")
                        stdscr.refresh()
                        stdscr.getch()
                        continue
                
                self.show_remotes = not self.show_remotes
                # Reload branches with loading message
                self.get_branches(stdscr)
                
                # Adjust selected index if needed
                if self.selected_index >= len(self.filtered_branches):
                    self.selected_index = max(0, len(self.filtered_branches) - 1)
            elif key == ord('f') or key == ord('F'):  # Fetch from remote
                try:
                    # Use animated spinner for fetch
                    result = self._run_command_with_spinner(
                        stdscr,
                        ["git", "fetch", "--all"],
                        "Fetching from remote...",
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    # Reload branches immediately after fetch
                    self.get_branches(stdscr)
                except subprocess.CalledProcessError as e:
                    stdscr.clear()
                    stdscr.addstr(0, 0, f"Fetch failed: {e}")
                    stdscr.addstr(1, 0, "Press any key to continue...")
                    stdscr.refresh()
                    stdscr.getch()
            elif key == ord('r') or key == ord('R'):  # Reload
                # Just reload branches - the loading message is shown by get_branches
                self.get_branches(stdscr)
                
                # Adjust selected index if needed
                if self.selected_index >= len(self.filtered_branches):
                    self.selected_index = max(0, len(self.filtered_branches) - 1)
            elif key == ord('/'):  # Search filter
                search_term = self.show_input_dialog(
                    stdscr,
                    "Search branches by name:",
                    self.search_filter
                )
                if search_term is not None:  # User didn't cancel
                    self.search_filter = search_term
                    self._apply_filters()
                    self.selected_index = 0  # Reset to first result
            elif key == ord('a') or key == ord('A'):  # Author filter
                self.author_filter = not self.author_filter
                self._apply_filters()
                if self.selected_index >= len(self.filtered_branches):
                    self.selected_index = max(0, len(self.filtered_branches) - 1)
            elif key == ord('o') or key == ord('O'):  # Old branches filter
                self.age_filter = not self.age_filter
                self._apply_filters()
                if self.selected_index >= len(self.filtered_branches):
                    self.selected_index = max(0, len(self.filtered_branches) - 1)
            elif key == ord('m'):  # lowercase m for merged filter (uppercase M is for rename)
                self.merged_filter = not self.merged_filter
                self._apply_filters()
                if self.selected_index >= len(self.filtered_branches):
                    self.selected_index = max(0, len(self.filtered_branches) - 1)
            elif key == ord('p') or key == ord('P'):  # Prefix filter
                prefix = self.show_input_dialog(
                    stdscr,
                    "Filter by prefix (e.g. feature/, bugfix/):",
                    self.prefix_filter
                )
                if prefix is not None:  # User didn't cancel
                    self.prefix_filter = prefix
                    self._apply_filters()
                    self.selected_index = 0  # Reset to first result
            elif key == ord('c') or key == ord('C'):  # Clear filters
                self.clear_all_filters()
            elif key == ord('S'):  # Pop stash
                if self.last_stash_ref:
                    stdscr.clear()
                    stdscr.addstr(0, 0, f"Popping stash {self.last_stash_ref}...")
                    stdscr.refresh()
                    
                    try:
                        self._run_command(
                            ["git", "stash", "pop", self.last_stash_ref],
                            capture_output=True,
                            text=True,
                            check=True
                        )
                        self.last_stash_ref = None  # Clear the reference
                        # Reload branches to update modified status
                        self.get_branches(stdscr)
                    except subprocess.CalledProcessError as e:
                        stdscr.clear()
                        stdscr.addstr(0, 0, f"Failed to pop stash: {e}")
                        stdscr.addstr(1, 0, "Press any key to continue...")
                        stdscr.refresh()
                        stdscr.getch()
                else:
                    stdscr.clear()
                    stdscr.addstr(0, 0, "No stash to pop.")
                    stdscr.addstr(1, 0, "Press any key to continue...")
                    stdscr.refresh()
                    stdscr.getch()
            elif key == ord('N'):  # Create new branch
                # Get new branch name from user
                new_branch_name = self.show_input_dialog(
                    stdscr,
                    "Enter new branch name:"
                )
                
                if new_branch_name:
                    # Check if branch already exists
                    existing_names = [b.name for b in self.branches]
                    if new_branch_name in existing_names:
                        stdscr.clear()
                        stdscr.addstr(0, 0, f"Branch '{new_branch_name}' already exists!")
                        stdscr.addstr(1, 0, "Press any key to continue...")
                        stdscr.refresh()
                        stdscr.getch()
                        continue
                    
                    # Ask if user wants to checkout the new branch
                    response = self.show_confirmation_dialog(
                        stdscr,
                        f"Create branch '{new_branch_name}'?\nAlso checkout the new branch?"
                    )
                    
                    if response == 'yes':
                        # Create and checkout
                        try:
                            self._run_command(
                                ["git", "checkout", "-b", new_branch_name],
                                capture_output=True,
                                text=True,
                                check=True
                            )
                            self.get_branches(stdscr)  # Refresh branch list
                        except subprocess.CalledProcessError as e:
                            stdscr.clear()
                            stdscr.addstr(0, 0, f"Failed to create branch: {e}")
                            stdscr.addstr(1, 0, "Press any key to continue...")
                            stdscr.refresh()
                            stdscr.getch()
                    elif response == 'no':
                        # Create without checkout
                        try:
                            self._run_command(
                                ["git", "branch", new_branch_name],
                                capture_output=True,
                                text=True,
                                check=True
                            )
                            self.get_branches(stdscr)  # Refresh branch list
                        except subprocess.CalledProcessError as e:
                            stdscr.clear()
                            stdscr.addstr(0, 0, f"Failed to create branch: {e}")
                            stdscr.addstr(1, 0, "Press any key to continue...")
                            stdscr.refresh()
                            stdscr.getch()
            elif key == curses.KEY_UP:
                self.selected_index = max(0, self.selected_index - 1)
            elif key == curses.KEY_DOWN:
                self.selected_index = min(len(self.filtered_branches) - 1, self.selected_index + 1)
            elif key == curses.KEY_PPAGE:  # Page Up
                # Move up by the number of visible branches
                page_size = visible_branches
                self.selected_index = max(0, self.selected_index - page_size)
            elif key == curses.KEY_NPAGE:  # Page Down
                # Move down by the number of visible branches
                page_size = visible_branches
                self.selected_index = min(len(self.filtered_branches) - 1, self.selected_index + page_size)
            elif key == curses.KEY_HOME:  # Home - go to first branch
                self.selected_index = 0
            elif key == curses.KEY_END:  # End - go to last branch
                if self.filtered_branches:
                    self.selected_index = len(self.filtered_branches) - 1
            elif key == ord('D'):  # Shift+D for delete
                if not self.filtered_branches:
                    continue
                selected_branch_info = self.filtered_branches[self.selected_index]
                selected_branch = selected_branch_info.name
                
                # Check if trying to delete a remote branch
                if selected_branch_info.is_remote:
                    stdscr.clear()
                    stdscr.addstr(0, 0, "Cannot delete remote branches!")
                    stdscr.addstr(1, 0, "Remote branches must be deleted from the remote repository.")
                    stdscr.addstr(2, 0, "To delete a local copy of a remote branch, switch off remote view (press 't').")
                    stdscr.addstr(3, 0, "Press any key to continue...")
                    stdscr.refresh()
                    stdscr.getch()
                    continue
                
                # Check if trying to delete current branch
                if selected_branch == self.current_branch:
                    stdscr.clear()
                    stdscr.addstr(0, 0, "Cannot delete the current branch!")
                    stdscr.addstr(1, 0, "Please switch to another branch first.")
                    stdscr.addstr(2, 0, "Press any key to continue...")
                    stdscr.refresh()
                    stdscr.getch()
                    continue
                
                # Check if trying to delete protected branch
                if selected_branch in self.protected_branches:
                    response = self.show_confirmation_dialog(
                        stdscr,
                        f"WARNING: '{selected_branch}' is a protected branch!\nAre you REALLY sure you want to delete it?"
                    )
                    if response != 'yes':
                        continue
                
                # Show confirmation dialog
                response = self.show_confirmation_dialog(
                    stdscr,
                    f"Delete branch '{selected_branch}'?\nThis action cannot be undone."
                )
                
                if response == 'yes':
                    if self.delete_branch(selected_branch):
                        self.get_branches(stdscr)  # Refresh branch list
                        # Adjust selected index if needed
                        if self.selected_index >= len(self.filtered_branches):
                            self.selected_index = max(0, len(self.filtered_branches) - 1)
                    else:
                        stdscr.clear()
                        stdscr.addstr(0, 0, f"Failed to delete branch '{selected_branch}'!")
                        stdscr.addstr(1, 0, "The branch may have unpushed commits or is not fully merged.")
                        stdscr.addstr(2, 0, "Press any key to continue...")
                        stdscr.refresh()
                        stdscr.getch()
            elif key == ord('M'):  # Shift+M for move/rename
                if not self.filtered_branches:
                    continue
                selected_branch = self.filtered_branches[self.selected_index].name
                
                # Get new name from user
                new_name = self.show_input_dialog(
                    stdscr,
                    f"Rename branch '{selected_branch}' to:",
                    selected_branch
                )
                
                if new_name and new_name != selected_branch:
                    # Check if new name already exists
                    existing_names = [b.name for b in self.branches]
                    if new_name in existing_names:
                        stdscr.clear()
                        stdscr.addstr(0, 0, f"Branch '{new_name}' already exists!")
                        stdscr.addstr(1, 0, "Press any key to continue...")
                        stdscr.refresh()
                        stdscr.getch()
                        continue
                    
                    if self.move_branch(selected_branch, new_name):
                        # Update current branch name if it was renamed
                        if selected_branch == self.current_branch:
                            self.current_branch = new_name
                        self.get_branches(stdscr)  # Refresh branch list
                    else:
                        stdscr.addstr(1, 0, f"Failed to rename branch!")
                        stdscr.addstr(2, 0, "Press any key to continue...")
                        stdscr.refresh()
                        stdscr.getch()
            elif key == ord('B'):  # Shift+B for opening branch in browser (compare/PR)
                if not self.filtered_branches or not self.url_builder:
                    if not self.url_builder:
                        stdscr.clear()
                        stdscr.addstr(0, 0, "No remote repository URL found!")
                        stdscr.addstr(1, 0, "Make sure you have a remote named 'origin' configured.")
                        stdscr.addstr(2, 0, "")
                        stdscr.addstr(3, 0, "Press 'h' for configuration help, any other key to continue...")
                        stdscr.refresh()
                        key = stdscr.getch()
                        if key == ord('h') or key == ord('H'):
                            self.show_platform_config_help(stdscr)
                    continue
                
                selected_branch_info = self.filtered_branches[self.selected_index]
                selected_branch = selected_branch_info.name
                
                # Check if branch has been pushed
                if not selected_branch_info.is_remote and not selected_branch_info.has_upstream:
                    stdscr.clear()
                    stdscr.addstr(0, 0, f"Branch '{selected_branch}' has not been pushed to remote!")
                    stdscr.addstr(1, 0, "Push the branch first before opening in browser.")
                    stdscr.addstr(2, 0, "")
                    stdscr.addstr(3, 0, "Press any key to continue...")
                    stdscr.refresh()
                    stdscr.getch()
                    continue
                
                # Check if branch is merged and config prevents opening
                if selected_branch_info.is_merged and self.config.get('prevent_browser_for_merged', False):
                    stdscr.clear()
                    stdscr.addstr(0, 0, f"Branch '{selected_branch}' has been merged!")
                    stdscr.addstr(1, 0, "")
                    stdscr.addstr(2, 0, "This branch has likely been deleted from the remote repository")
                    stdscr.addstr(3, 0, "after being merged (based on your configuration).")
                    stdscr.addstr(4, 0, "")
                    stdscr.addstr(5, 0, "Press 'o' to open anyway, or any other key to cancel...")
                    stdscr.addstr(6, 0, "")
                    stdscr.addstr(7, 0, "To disable this warning, set 'prevent_browser_for_merged' to false")
                    stdscr.addstr(8, 0, "in your ~/.config/git-branch-manager/config.json file.")
                    stdscr.refresh()
                    
                    key = stdscr.getch()
                    if key != ord('o') and key != ord('O'):
                        continue
                    # If 'o' pressed, fall through to open the browser
                
                # For remote branches, strip the remote prefix (e.g., origin/)
                if selected_branch_info.is_remote and '/' in selected_branch:
                    branch_name = selected_branch.split('/', 1)[1]
                else:
                    branch_name = selected_branch
                
                # Build compare URL
                url = self.url_builder.build_compare_url(branch_name)
                if url:
                    try:
                        # Use the configured browser command
                        browser_cmd = self.config.get('browser_command', 'open')
                        self._run_command([browser_cmd, url], check=True)
                    except subprocess.CalledProcessError:
                        stdscr.clear()
                        stdscr.addstr(0, 0, f"Failed to open browser!")
                        stdscr.addstr(1, 0, f"URL: {url}")
                        stdscr.addstr(2, 0, "Press any key to continue...")
                        stdscr.refresh()
                        stdscr.getch()
                else:
                    stdscr.clear()
                    stdscr.addstr(0, 0, f"Platform '{self.url_builder.platform}' not supported for compare URLs")
                    stdscr.addstr(1, 0, "")
                    stdscr.addstr(2, 0, "Press 'h' for configuration help, any other key to continue...")
                    stdscr.refresh()
                    key = stdscr.getch()
                    if key == ord('h') or key == ord('H'):
                        self.show_platform_config_help(stdscr)
            elif key == ord('b'):  # lowercase b for opening branch view
                if not self.filtered_branches or not self.url_builder:
                    if not self.url_builder:
                        stdscr.clear()
                        stdscr.addstr(0, 0, "No remote repository URL found!")
                        stdscr.addstr(1, 0, "Make sure you have a remote named 'origin' configured.")
                        stdscr.addstr(2, 0, "")
                        stdscr.addstr(3, 0, "Press 'h' for configuration help, any other key to continue...")
                        stdscr.refresh()
                        key = stdscr.getch()
                        if key == ord('h') or key == ord('H'):
                            self.show_platform_config_help(stdscr)
                    continue
                
                selected_branch_info = self.filtered_branches[self.selected_index]
                selected_branch = selected_branch_info.name
                
                # Check if branch has been pushed
                if not selected_branch_info.is_remote and not selected_branch_info.has_upstream:
                    stdscr.clear()
                    stdscr.addstr(0, 0, f"Branch '{selected_branch}' has not been pushed to remote!")
                    stdscr.addstr(1, 0, "Push the branch first before opening in browser.")
                    stdscr.addstr(2, 0, "")
                    stdscr.addstr(3, 0, "Press any key to continue...")
                    stdscr.refresh()
                    stdscr.getch()
                    continue
                
                # Check if branch is merged and config prevents opening
                if selected_branch_info.is_merged and self.config.get('prevent_browser_for_merged', False):
                    stdscr.clear()
                    stdscr.addstr(0, 0, f"Branch '{selected_branch}' has been merged!")
                    stdscr.addstr(1, 0, "")
                    stdscr.addstr(2, 0, "This branch has likely been deleted from the remote repository")
                    stdscr.addstr(3, 0, "after being merged (based on your configuration).")
                    stdscr.addstr(4, 0, "")
                    stdscr.addstr(5, 0, "Press 'o' to open anyway, or any other key to cancel...")
                    stdscr.addstr(6, 0, "")
                    stdscr.addstr(7, 0, "To disable this warning, set 'prevent_browser_for_merged' to false")
                    stdscr.addstr(8, 0, "in your ~/.config/git-branch-manager/config.json file.")
                    stdscr.refresh()
                    
                    key = stdscr.getch()
                    if key != ord('o') and key != ord('O'):
                        continue
                    # If 'o' pressed, fall through to open the browser
                
                # For remote branches, strip the remote prefix (e.g., origin/)
                if selected_branch_info.is_remote and '/' in selected_branch:
                    branch_name = selected_branch.split('/', 1)[1]
                else:
                    branch_name = selected_branch
                
                # Build branch URL
                url = self.url_builder.build_branch_url(branch_name)
                if url:
                    try:
                        # Use the configured browser command
                        browser_cmd = self.config.get('browser_command', 'open')
                        self._run_command([browser_cmd, url], check=True)
                    except subprocess.CalledProcessError:
                        stdscr.clear()
                        stdscr.addstr(0, 0, f"Failed to open browser!")
                        stdscr.addstr(1, 0, f"URL: {url}")
                        stdscr.addstr(2, 0, "Press any key to continue...")
                        stdscr.refresh()
                        stdscr.getch()
                else:
                    stdscr.clear()
                    stdscr.addstr(0, 0, f"Platform '{self.url_builder.platform}' not supported for branch URLs")
                    stdscr.addstr(1, 0, "")
                    stdscr.addstr(2, 0, "Press 'h' for configuration help, any other key to continue...")
                    stdscr.refresh()
                    key = stdscr.getch()
                    if key == ord('h') or key == ord('H'):
                        self.show_platform_config_help(stdscr)
            elif key == ord('\n') or key == curses.KEY_ENTER:
                if not self.filtered_branches:
                    continue
                selected_branch_info = self.filtered_branches[self.selected_index]
                selected_branch = selected_branch_info.name
                
                # For remote branches, show the local name that will be created
                display_name = selected_branch
                if selected_branch_info.is_remote and '/' in selected_branch:
                    display_name = selected_branch.split('/', 1)[1]
                
                if selected_branch != self.current_branch:
                    # Check if branch is checked out in a worktree
                    if selected_branch_info.in_worktree:
                        stdscr.clear()
                        stdscr.addstr(0, 0, f"Cannot checkout branch '{selected_branch}'!")
                        stdscr.addstr(1, 0, "This branch is already checked out in another worktree.")
                        stdscr.addstr(2, 0, "")
                        stdscr.addstr(3, 0, "Press any key to continue...")
                        stdscr.refresh()
                        stdscr.getch()
                        continue
                    
                    # Check if there are changes to stash
                    try:
                        status_result = self._run_command(
                            ["git", "status", "--porcelain"],
                            capture_output=True,
                            text=True,
                            check=True
                        )
                        
                        has_changes = bool(status_result.stdout.strip())
                        stashed = False
                        
                        if has_changes:
                            # Show confirmation dialog
                            response = self.show_confirmation_dialog(
                                stdscr,
                                f"You have uncommitted changes.\nStash them before switching to '{display_name}'?"
                            )
                            
                            if response == 'cancel':
                                continue  # Go back to branch list
                            elif response == 'yes':
                                stashed = self.stash_changes()
                                if not stashed:
                                    stdscr.clear()
                                    stdscr.addstr(0, 0, "Failed to stash changes!")
                                    stdscr.addstr(1, 0, "Press any key to continue...")
                                    stdscr.refresh()
                                    stdscr.getch()
                                    continue
                            # If 'no', proceed without stashing
                        
                        # Checkout branch
                        if self.checkout_branch(selected_branch, selected_branch_info.is_remote):
                            self.get_branches(stdscr)  # Refresh branch list
                            
                            # Check if the newly checked out branch has any stashes
                            branch_stashes = self._get_branch_stashes(self.current_branch)
                            if branch_stashes:
                                # Show the most recent stash for this branch
                                most_recent_stash = branch_stashes[0]
                                stash_ref, stash_message = most_recent_stash
                                
                                stdscr.clear()
                                stdscr.addstr(0, 0, f"Found {len(branch_stashes)} git-branch-manager stash{'es' if len(branch_stashes) > 1 else ''} for branch '{self.current_branch}':")
                                stdscr.addstr(1, 0, "")
                                stdscr.addstr(2, 0, f"Most recent: {stash_message}")
                                stdscr.addstr(3, 0, "")
                                stdscr.addstr(4, 0, "Apply this stash? (y/n)")
                                stdscr.refresh()
                                
                                key = stdscr.getch()
                                if key in [ord('y'), ord('Y')]:
                                    try:
                                        self._run_command(
                                            ["git", "stash", "pop", stash_ref],
                                            capture_output=True,
                                            text=True,
                                            check=True
                                        )
                                        stdscr.clear()
                                        stdscr.addstr(0, 0, "Stash applied successfully!")
                                        stdscr.addstr(1, 0, "Press any key to continue...")
                                        stdscr.refresh()
                                        stdscr.getch()
                                        # Refresh to show modified status
                                        self.get_branches(stdscr)
                                    except subprocess.CalledProcessError as e:
                                        stdscr.clear()
                                        stdscr.addstr(0, 0, "Failed to apply stash!")
                                        stdscr.addstr(1, 0, f"Error: {e}")
                                        stdscr.addstr(2, 0, "Press any key to continue...")
                                        stdscr.refresh()
                                        stdscr.getch()
                        else:
                            stdscr.clear()
                            stdscr.addstr(0, 0, "Failed to checkout branch!")
                            stdscr.addstr(1, 0, "Press any key to continue...")
                            stdscr.refresh()
                            stdscr.getch()
                            
                    except subprocess.CalledProcessError as e:
                        stdscr.clear()
                        stdscr.addstr(0, 0, f"Error checking git status: {e}")
                        stdscr.addstr(1, 0, "Press any key to continue...")
                        stdscr.refresh()
                        stdscr.getch()

def main():
    """Entry point for the Git Branch Manager application.
    
    Parses command line arguments, verifies git repository,
    and launches the TUI using curses.
    
    Exits with status 1 if not in a git repository.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        prog='git-branch-manager',
        description='Terminal-based Git branch manager with rich features',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Key bindings:
  ↑/↓       Navigate branches
  Enter     Checkout selected branch
  D         Delete branch
  M         Move/rename branch
  N         Create new branch
  S         Pop last stash
  t         Toggle remote branches
  f         Fetch from remote
  r         Reload branch list
  b         Open branch in browser
  B         Open branch comparison/PR in browser
  /         Search branches
  a         Toggle author filter
  o         Toggle old branches filter
  m         Toggle merged filter
  p         Filter by prefix
  c         Clear all filters
  ?         Show help
  q         Quit
  ESC       Clear filters or quit

For more information, visit: https://github.com/daves/git-branch-manager"""
    )
    
    parser.add_argument(
        '--version', '-v',
        action='version',
        version=f'%(prog)s {__version__}'
    )
    
    parser.add_argument(
        '--directory', '-d',
        type=str,
        help='Git repository directory (default: current directory)',
        default=os.getcwd()
    )
    
    args = parser.parse_args()
    
    # Change to specified directory if provided
    if args.directory != os.getcwd():
        try:
            os.chdir(args.directory)
        except OSError as e:
            print(f"Error: Cannot change to directory '{args.directory}': {e}")
            sys.exit(1)
    
    # Check if we're in a git repository
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            check=True,
            cwd=os.getcwd()
        )
    except subprocess.CalledProcessError:
        print("Error: Not in a git repository")
        sys.exit(1)
        
    manager = GitBranchManager()
    curses.wrapper(manager.run)

if __name__ == "__main__":
    main()