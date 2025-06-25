#!/usr/bin/env python3

import subprocess
import sys
import os
from typing import List, Optional, NamedTuple, Dict, Tuple
import curses
from datetime import datetime, timedelta
import time
import json

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
                self._run_command(
                    ["git", "stash", "push", "-m", "Stashed by git-branch-manager"],
                    capture_output=True,
                    text=True,
                    check=True
                )
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
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        
        help_text = [
            ("Git Branch Manager - Help", curses.A_BOLD),
            ("=" * 30, 0),
            ("", 0),
            ("Navigation:", curses.A_BOLD),
            ("  ↑/↓        Navigate through branches", 0),
            ("  q/ESC      Quit", 0),
            ("  ?          Show this help", 0),
            ("", 0),
            ("Branch Operations:", curses.A_BOLD),
            ("  Enter      Checkout selected branch", 0),
            ("  D          Delete selected branch", 0),
            ("  M          Rename/move selected branch", 0),
            ("", 0),
            ("View Options:", curses.A_BOLD),
            ("  r          Reload branch list", 0),
            ("  t          Toggle remote branches", 0),
            ("  f          Fetch latest from remote", 0),
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
            ("Press any key to return...", curses.A_BOLD),
        ]
        
        # Display help text
        start_y = max(0, (height - len(help_text)) // 2)
        start_x = max(5, (width - 60) // 2)  # Left margin of 5, or centered if narrow screen
        
        for i, (text, attr) in enumerate(help_text):
            if start_y + i < height - 1:
                try:
                    if attr:
                        stdscr.attron(attr)
                    stdscr.addstr(start_y + i, start_x, text[:width - start_x - 1])
                    if attr:
                        stdscr.attroff(attr)
                except curses.error:
                    pass
        
        stdscr.refresh()
        stdscr.getch()
    
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
            
            # Header
            header = "Git Branch Manager - Press ? for help"
            if self.show_remotes:
                header += " [REMOTES ON]"
            
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
            
            stdscr.addstr(0, 0, header[:width-1])
            stdscr.addstr(1, 0, "-" * min(len(header), width-1))
            
            # Display branches
            start_y = 3
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
                    stdscr.addstr(y, 0, " " * (width - 1))  # Fill background
                    stdscr.addstr(y, x_pos, prefix)
                    x_pos += len(prefix)
                    stdscr.addstr(y, x_pos, branch_info.name)
                    x_pos += len(branch_info.name)
                    if modified_indicator:
                        stdscr.addstr(y, x_pos, modified_indicator)
                        x_pos += len(modified_indicator)
                    stdscr.addstr(y, x_pos, separator)
                    x_pos += len(separator)
                    stdscr.addstr(y, x_pos, relative_date)
                    x_pos += len(relative_date)
                    stdscr.addstr(y, x_pos, separator)
                    x_pos += len(separator)
                    stdscr.addstr(y, x_pos, branch_info.commit_hash)
                    x_pos += len(branch_info.commit_hash)
                    stdscr.addstr(y, x_pos, separator)
                    x_pos += len(separator)
                    stdscr.addstr(y, x_pos, commit_msg)
                    stdscr.attroff(curses.color_pair(1))
                else:
                    # Non-selected rows with colors
                    stdscr.addstr(y, x_pos, prefix)
                    x_pos += len(prefix)
                    
                    # Branch name color
                    if branch_info.is_current:
                        stdscr.attron(curses.color_pair(2))
                        stdscr.addstr(y, x_pos, branch_info.name)
                        stdscr.attroff(curses.color_pair(2))
                    else:
                        stdscr.attron(curses.color_pair(4))
                        stdscr.addstr(y, x_pos, branch_info.name)
                        stdscr.attroff(curses.color_pair(4))
                    x_pos += len(branch_info.name)
                    
                    # Modified indicator
                    if modified_indicator:
                        stdscr.attron(curses.color_pair(3))
                        stdscr.addstr(y, x_pos, modified_indicator)
                        stdscr.attroff(curses.color_pair(3))
                        x_pos += len(modified_indicator)
                    
                    stdscr.addstr(y, x_pos, separator)
                    x_pos += len(separator)
                    
                    # Date with age-based color
                    stdscr.attron(curses.color_pair(date_color))
                    stdscr.addstr(y, x_pos, relative_date)
                    stdscr.attroff(curses.color_pair(date_color))
                    x_pos += len(relative_date)
                    
                    stdscr.addstr(y, x_pos, separator)
                    x_pos += len(separator)
                    
                    # Commit hash
                    stdscr.attron(curses.color_pair(6))
                    stdscr.addstr(y, x_pos, branch_info.commit_hash)
                    stdscr.attroff(curses.color_pair(6))
                    x_pos += len(branch_info.commit_hash)
                    
                    stdscr.addstr(y, x_pos, separator)
                    x_pos += len(separator)
                    
                    # Commit message
                    stdscr.addstr(y, x_pos, commit_msg)
                    
            stdscr.refresh()
            
            # Handle key press
            key = stdscr.getch()
            
            if key == ord('q') or key == ord('Q') or key == 27:  # 27 is ESC
                break
            elif key == ord('?'):  # Show help
                self.show_help(stdscr)
            elif key == ord('t') or key == ord('T'):  # Toggle remote branches
                self.show_remotes = not self.show_remotes
                stdscr.clear()
                stdscr.addstr(0, 0, f"Remote branches: {'ON' if self.show_remotes else 'OFF'}")
                stdscr.addstr(1, 0, "Loading branches...")
                stdscr.refresh()
                
                # Reload branches
                self.get_branches(stdscr)
                
                # Adjust selected index if needed
                if self.selected_index >= len(self.filtered_branches):
                    self.selected_index = max(0, len(self.filtered_branches) - 1)
                    
                stdscr.addstr(2, 0, "Press any key to continue...")
                stdscr.refresh()
                stdscr.getch()
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
                    stdscr.addstr(1, 0, "Fetch complete!")
                    stdscr.addstr(2, 0, "Reloading branches...")
                    stdscr.refresh()
                    
                    # Reload branches
                    self.get_branches(stdscr)
                    
                    stdscr.addstr(3, 0, "Press any key to continue...")
                except subprocess.CalledProcessError as e:
                    stdscr.addstr(1, 0, f"Fetch failed: {e}")
                    stdscr.addstr(2, 0, "Press any key to continue...")
                
                stdscr.refresh()
                stdscr.getch()
            elif key == ord('r') or key == ord('R'):  # Reload
                # Show loading message
                stdscr.clear()
                stdscr.addstr(0, 0, "Reloading branches...")
                stdscr.refresh()
                
                # Reload branches
                self.get_branches(stdscr)
                
                # Adjust selected index if needed
                if self.selected_index >= len(self.filtered_branches):
                    self.selected_index = max(0, len(self.filtered_branches) - 1)
                
                stdscr.addstr(1, 0, "Reload complete!")
                stdscr.addstr(2, 0, "Press any key to continue...")
                stdscr.refresh()
                stdscr.getch()
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
                self.search_filter = ""
                self.author_filter = False
                self.age_filter = False
                self.prefix_filter = ""
                self._apply_filters()
                self.selected_index = 0
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
                
                # Show confirmation dialog
                response = self.show_confirmation_dialog(
                    stdscr,
                    f"Delete branch '{selected_branch}'?\nThis action cannot be undone."
                )
                
                if response == 'yes':
                    stdscr.clear()
                    stdscr.addstr(0, 0, f"Deleting branch '{selected_branch}'...")
                    stdscr.refresh()
                    
                    if self.delete_branch(selected_branch):
                        stdscr.addstr(1, 0, f"Successfully deleted branch '{selected_branch}'")
                        stdscr.addstr(2, 0, "Press any key to continue...")
                        stdscr.refresh()
                        stdscr.getch()
                        self.get_branches(stdscr)  # Refresh branch list
                        # Adjust selected index if needed
                        if self.selected_index >= len(self.filtered_branches):
                            self.selected_index = max(0, len(self.filtered_branches) - 1)
                    else:
                        stdscr.addstr(1, 0, f"Failed to delete branch '{selected_branch}'!")
                        stdscr.addstr(2, 0, "The branch may have unpushed commits or is not fully merged.")
                        stdscr.addstr(3, 0, "Press any key to continue...")
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
                    
                    stdscr.clear()
                    stdscr.addstr(0, 0, f"Renaming branch '{selected_branch}' to '{new_name}'...")
                    stdscr.refresh()
                    
                    if self.move_branch(selected_branch, new_name):
                        stdscr.addstr(1, 0, f"Successfully renamed branch to '{new_name}'")
                        stdscr.addstr(2, 0, "Press any key to continue...")
                        stdscr.refresh()
                        stdscr.getch()
                        self.get_branches(stdscr)  # Refresh branch list
                        # Update current branch name if it was renamed
                        if selected_branch == self.current_branch:
                            self.current_branch = new_name
                    else:
                        stdscr.addstr(1, 0, f"Failed to rename branch!")
                        stdscr.addstr(2, 0, "Press any key to continue...")
                        stdscr.refresh()
                        stdscr.getch()
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
                        
                        stdscr.clear()
                        if selected_branch_info.is_remote:
                            stdscr.addstr(0, 0, f"Creating local branch '{display_name}' from '{selected_branch}'...")
                        else:
                            stdscr.addstr(0, 0, f"Switching to branch '{selected_branch}'...")
                        stdscr.refresh()
                        
                        if stashed:
                            stdscr.addstr(1, 0, "Stashed current changes.")
                            stdscr.refresh()
                        
                        # Checkout branch
                        if self.checkout_branch(selected_branch, selected_branch_info.is_remote):
                            stdscr.addstr(2 if stashed else 1, 0, f"Successfully checked out '{display_name}'")
                            stdscr.addstr(3 if stashed else 2, 0, "Press any key to continue...")
                            stdscr.refresh()
                            stdscr.getch()
                            self.get_branches(stdscr)  # Refresh branch list
                        else:
                            stdscr.addstr(2 if stashed else 1, 0, "Failed to checkout branch!")
                            stdscr.addstr(3 if stashed else 2, 0, "Press any key to continue...")
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