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
    """Builds URLs for different Git hosting platforms."""
    
    def __init__(self, config: Dict[str, Any], remote_url: str):
        self.config = config
        self.remote_url = remote_url
        self.platform = self._detect_platform()
        self.repo_info = self._parse_remote_url()
    
    def _detect_platform(self) -> str:
        """Detect the Git hosting platform from the remote URL."""
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
        """Parse the remote URL to extract repository information."""
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
        """Build URL to view a specific branch."""
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
        """Build URL to compare branch with base branch or create PR."""
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
    def __init__(self):
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
        self.current_user: Optional[str] = self._get_current_user()
        self.last_stash_ref: Optional[str] = None  # Track last stash created
        self.protected_branches: List[str] = ["main", "master"]  # Protected branches
        
        # Configuration
        self.config: Dict[str, Any] = self._load_config()
        self.url_builder: Optional[GitPlatformURLBuilder] = None
        self._init_url_builder()
        
    def _get_config_path(self) -> str:
        """Get the path to the configuration file."""
        xdg_config_home = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
        return os.path.join(xdg_config_home, 'git-branch-manager', 'config.json')
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or return defaults."""
        config_path = self._get_config_path()
        default_config = {
            'platform': 'auto',
            'default_base_branch': 'main',
            'browser_command': 'open' if sys.platform == 'darwin' else 'xdg-open' if sys.platform.startswith('linux') else 'start',
            'custom_patterns': {}
        }
        
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    user_config = json.load(f)
                    # Merge with defaults
                    default_config.update(user_config)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load config from {config_path}: {e}")
        
        return default_config
    
    def _save_config(self) -> None:
        """Save current configuration to file."""
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
        """Initialize the URL builder with the current remote URL."""
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
        """Check if any filters are currently active."""
        return bool(self.search_filter or self.author_filter or self.age_filter or self.prefix_filter)
    
    def clear_all_filters(self) -> None:
        """Clear all active filters."""
        self.search_filter = ""
        self.author_filter = False
        self.age_filter = False
        self.prefix_filter = ""
        self._apply_filters()
        self.selected_index = 0
        
    def _run_command(self, cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
        """Run a command in the current working directory."""
        if 'cwd' not in kwargs:
            kwargs['cwd'] = self.working_dir
        return subprocess.run(cmd, **kwargs)
        
    def _get_current_user(self) -> Optional[str]:
        """Get the current git user."""
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
    
    def _get_batch_branch_info(self, branches: List[Tuple[str, bool, Optional[str]]]) -> Dict[str, Dict]:
        """Get branch info for multiple branches in a single git command."""
        if not branches:
            return {}
        
        # Build format string for git for-each-ref
        format_str = "%(refname:short)|%(objectname:short)|%(committerdate:unix)|%(subject)|%(committeremail)"
        
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
                        
                        branch_data[branch_name] = {
                            'hash': parts[1],
                            'timestamp': int(parts[2]),
                            'message': parts[3],
                            'author': parts[4]
                        }
            
            return branch_data
            
        except subprocess.CalledProcessError:
            return {}
    
    def _check_uncommitted_changes_batch(self) -> bool:
        """Check if current branch has uncommitted changes."""
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
    
    def safe_addstr(self, stdscr, y: int, x: int, text: str, attr: int = 0) -> int:
        """Safely add string to screen, truncating if necessary. Returns new x position."""
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
    
    def show_loading_message(self, stdscr, message: str) -> None:
        """Show a loading message in the center of the screen."""
        if stdscr:
            stdscr.clear()
            height, width = stdscr.getmaxyx()
            y = height // 2
            x = (width - len(message)) // 2
            if x >= 0 and y >= 0:
                try:
                    stdscr.addstr(y, x, message)
                    stdscr.refresh()
                except curses.error:
                    pass
    
    def get_branches(self, stdscr=None) -> None:
        """Get list of git branches with commit info - optimized version."""
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
            batch_info = self._get_batch_branch_info(all_branches)
            
            # Check uncommitted changes once for current branch
            has_uncommitted = False
            if self.current_branch:
                has_uncommitted = self._check_uncommitted_changes_batch()
            
            # Build BranchInfo objects
            for branch_name, is_remote, remote_name in all_branches:
                if branch_name in batch_info:
                    info = batch_info[branch_name]
                    
                    branch_info = BranchInfo(
                        name=branch_name,
                        is_current=(branch_name == self.current_branch),
                        commit_hash=info['hash'],
                        commit_date=datetime.fromtimestamp(info['timestamp']),
                        commit_message=info['message'],
                        commit_author=info['author'],
                        has_uncommitted_changes=(has_uncommitted if branch_name == self.current_branch else False),
                        is_remote=is_remote,
                        remote_name=remote_name
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
        """Apply all active filters to the branch list."""
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
        
        # Adjust selected index if it's out of bounds
        if self.selected_index >= len(self.filtered_branches):
            self.selected_index = max(0, len(self.filtered_branches) - 1)
            
    def stash_changes(self) -> bool:
        """Stash current changes if any exist."""
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
        """Checkout the specified branch."""
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
        """Delete the specified branch."""
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
        """Move/rename a branch."""
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
        """Show help screen with all commands."""
        height, width = stdscr.getmaxyx()
        
        help_text = [
            ("Git Branch Manager - Help", curses.A_BOLD),
            ("=" * 30, 0),
            ("", 0),
            ("Navigation:", curses.A_BOLD),
            ("  ↑/↓        Navigate through branches", 0),
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
            ("  p          Filter by prefix (feature/, bugfix/, etc)", 0),
            ("  c          Clear all filters", 0),
            ("", 0),
            ("Status Indicators:", curses.A_BOLD),
            ("  *          Current branch", 0),
            ("  ↓          Remote branch", 0),
            ("  [modified] Uncommitted changes", 0),
            ("", 0),
            ("Color Coding:", curses.A_BOLD),
            ("  Green      Current branch", 0),
            ("  Cyan       Branch names", 0),
            ("  Yellow     Modified indicator", 0),
            ("  Magenta    Recent commits (<1 week)", 0),
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
            else:
                break
    
    def show_platform_config_help(self, stdscr) -> None:
        """Show help for configuring Git platform integration."""
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
            visible_lines = height - 2  # Leave room for borders
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
            else:
                break
    
    def show_confirmation_dialog(self, stdscr, message: str) -> Optional[str]:
        """Show a confirmation dialog with yes/no/cancel options."""
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
        """Main curses UI loop."""
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
        
        self.get_branches(stdscr)
        
        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()
            
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
                if result.returncode == 0:
                    git_dir = result.stdout.strip()
                    # Check if it's a worktree by looking for .git file (not directory)
                    git_path = os.path.join(git_dir, '.git')
                    if os.path.isfile(git_path):
                        worktree_info = " [worktree]"
            except:
                pass
            
            # Header
            header = "Git Branch Manager - Press ? for help"
            if self.show_remotes:
                header += " [REMOTES ON]"
            if self.last_stash_ref:
                header += f" [Stash: {self.last_stash_ref}]"
            
            # Add active filter indicators
            filters = []
            if self.search_filter:
                filters.append(f"search:{self.search_filter}")
            if self.author_filter:
                filters.append("author:me")
            if self.age_filter:
                filters.append("age:<3m")
            if self.prefix_filter:
                filters.append(f"prefix:{self.prefix_filter}")
            
            if filters:
                header += f" [Filters: {', '.join(filters)}]"
            
            # First line: main header
            stdscr.addstr(0, 0, header[:width-1])
            
            # Second line: working directory
            dir_line = f"Directory: {cwd}{worktree_info}"
            if len(dir_line) > width - 1:
                # Truncate from the left if too long, keeping the end visible
                dir_line = "..." + dir_line[-(width - 4):]
            stdscr.addstr(1, 0, dir_line[:width-1], curses.color_pair(8))
            
            stdscr.addstr(2, 0, "-" * min(max(len(header), len(dir_line)), width-1))
            
            # Display branches
            start_y = 4  # Increased from 3 to account for directory line
            visible_branches = min(height - start_y - 1, len(self.filtered_branches))
            
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
                
                # Calculate available space for commit message
                fixed_len = len(prefix) + len(branch_info.name) + len(modified_indicator) + len(separator) * 3 + len(relative_date) + len(branch_info.commit_hash)
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
                    
                    x_pos = self.safe_addstr(stdscr, y, x_pos, separator)
                    
                    # Date with age-based color
                    x_pos = self.safe_addstr(stdscr, y, x_pos, relative_date, curses.color_pair(date_color))
                    
                    x_pos = self.safe_addstr(stdscr, y, x_pos, separator)
                    
                    # Commit hash
                    x_pos = self.safe_addstr(stdscr, y, x_pos, branch_info.commit_hash, curses.color_pair(6))
                    
                    x_pos = self.safe_addstr(stdscr, y, x_pos, separator)
                    
                    # Commit message
                    x_pos = self.safe_addstr(stdscr, y, x_pos, commit_msg)
                    
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
                    stdscr.clear()
                    stdscr.addstr(0, 0, "Fetching from remote...")
                    stdscr.refresh()
                    
                    try:
                        self._run_command(
                            ["git", "fetch", "--all"],
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
                stdscr.clear()
                stdscr.addstr(0, 0, "Fetching from remote...")
                stdscr.refresh()
                
                try:
                    result = self._run_command(
                        ["git", "fetch", "--all"],
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
            elif key == ord('D'):  # Shift+D for delete
                if not self.filtered_branches:
                    continue
                selected_branch = self.filtered_branches[self.selected_index].name
                
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