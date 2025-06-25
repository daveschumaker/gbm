#!/usr/bin/env python3

import subprocess
import sys
import os
from typing import List, Optional, NamedTuple
import curses
from datetime import datetime, timedelta
import time

class BranchInfo(NamedTuple):
    name: str
    is_current: bool
    commit_hash: str
    commit_date: datetime
    commit_message: str
    has_uncommitted_changes: bool
    
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
        self.current_branch: Optional[str] = None
        self.selected_index: int = 0
        
    def get_branch_info(self, branch: str) -> Optional[BranchInfo]:
        """Get commit info for a specific branch."""
        try:
            # Get commit hash, date, and message
            result = subprocess.run(
                ["git", "log", "-1", "--format=%H|%at|%s", branch],
                capture_output=True,
                text=True,
                check=True
            )
            
            if result.stdout.strip():
                parts = result.stdout.strip().split('|', 2)
                if len(parts) == 3:
                    commit_hash = parts[0][:12]  # Short hash
                    commit_timestamp = int(parts[1])
                    commit_date = datetime.fromtimestamp(commit_timestamp)
                    commit_message = parts[2]
                    
                    # Check for uncommitted changes only on current branch
                    has_uncommitted_changes = False
                    if branch == self.current_branch:
                        status_result = subprocess.run(
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
                        has_uncommitted_changes=has_uncommitted_changes
                    )
            return None
            
        except subprocess.CalledProcessError:
            return None
    
    def get_branches(self) -> None:
        """Get list of local git branches with commit info."""
        try:
            # First get the current branch
            current_result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                check=True
            )
            self.current_branch = current_result.stdout.strip()
            
            # Get all branches
            result = subprocess.run(
                ["git", "branch"],
                capture_output=True,
                text=True,
                check=True
            )
            
            lines = result.stdout.strip().split('\n')
            self.branches = []
            
            for line in lines:
                branch_name = line.strip()
                if branch_name.startswith('* '):
                    branch_name = branch_name[2:]
                
                branch_info = self.get_branch_info(branch_name)
                if branch_info:
                    self.branches.append(branch_info)
                    
        except subprocess.CalledProcessError as e:
            print(f"Error getting branches: {e}")
            sys.exit(1)
            
    def stash_changes(self) -> bool:
        """Stash current changes if any exist."""
        try:
            # Check if there are any changes to stash
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=True
            )
            
            if status_result.stdout.strip():
                # There are changes, stash them
                subprocess.run(
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
            
    def checkout_branch(self, branch: str) -> bool:
        """Checkout the specified branch."""
        try:
            subprocess.run(
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
            subprocess.run(
                ["git", "branch", "-d", branch],
                capture_output=True,
                text=True,
                check=True
            )
            return True
        except subprocess.CalledProcessError as e:
            # Try force delete if regular delete fails
            try:
                subprocess.run(
                    ["git", "branch", "-D", branch],
                    capture_output=True,
                    text=True,
                    check=True
                )
                return True
            except subprocess.CalledProcessError:
                return False
            
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
        
        self.get_branches()
        
        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()
            
            # Header
            header = "Git Branch Manager - ↑/↓ navigate, Enter checkout, Shift+D delete, q/ESC quit"
            stdscr.addstr(0, 0, header[:width-1])
            stdscr.addstr(1, 0, "-" * min(len(header), width-1))
            
            # Display branches
            start_y = 3
            visible_branches = min(height - start_y - 1, len(self.branches))
            
            # Calculate scroll position
            if self.selected_index >= visible_branches:
                scroll_offset = self.selected_index - visible_branches + 1
            else:
                scroll_offset = 0
                
            for i in range(visible_branches):
                branch_index = i + scroll_offset
                if branch_index >= len(self.branches):
                    break
                    
                branch_info = self.branches[branch_index]
                y = start_y + i
                
                # Prepare display string with branch info
                prefix = "* " if branch_info.is_current else "  "
                relative_date = branch_info.format_relative_date()
                
                # Add modified indicator
                modified_indicator = " [modified]" if branch_info.has_uncommitted_changes else ""
                
                # Truncate commit message if needed
                max_msg_len = width - len(branch_info.name) - len(relative_date) - len(branch_info.commit_hash) - len(modified_indicator) - 10
                commit_msg = branch_info.commit_message
                if len(commit_msg) > max_msg_len and max_msg_len > 3:
                    commit_msg = commit_msg[:max_msg_len-3] + "..."
                
                display_str = f"{prefix}{branch_info.name}{modified_indicator} • {relative_date} • {branch_info.commit_hash} • {commit_msg}"
                
                # Apply highlighting
                if branch_index == self.selected_index:
                    stdscr.attron(curses.color_pair(1))
                    stdscr.addstr(y, 0, display_str[:width-1].ljust(width-1))
                    stdscr.attroff(curses.color_pair(1))
                elif branch_info.is_current:
                    stdscr.attron(curses.color_pair(2))
                    stdscr.addstr(y, 0, display_str[:width-1])
                    stdscr.attroff(curses.color_pair(2))
                else:
                    stdscr.addstr(y, 0, display_str[:width-1])
                    
            stdscr.refresh()
            
            # Handle key press
            key = stdscr.getch()
            
            if key == ord('q') or key == ord('Q') or key == 27:  # 27 is ESC
                break
            elif key == curses.KEY_UP:
                self.selected_index = max(0, self.selected_index - 1)
            elif key == curses.KEY_DOWN:
                self.selected_index = min(len(self.branches) - 1, self.selected_index + 1)
            elif key == ord('D'):  # Shift+D for delete
                selected_branch = self.branches[self.selected_index].name
                
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
                        self.get_branches()  # Refresh branch list
                        # Adjust selected index if needed
                        if self.selected_index >= len(self.branches):
                            self.selected_index = len(self.branches) - 1
                    else:
                        stdscr.addstr(1, 0, f"Failed to delete branch '{selected_branch}'!")
                        stdscr.addstr(2, 0, "The branch may have unmerged changes.")
                        stdscr.addstr(3, 0, "Press any key to continue...")
                        stdscr.refresh()
                        stdscr.getch()
            elif key == ord('\n') or key == curses.KEY_ENTER:
                selected_branch = self.branches[self.selected_index].name
                if selected_branch != self.current_branch:
                    # Check if there are changes to stash
                    try:
                        status_result = subprocess.run(
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
                                f"You have uncommitted changes.\nStash them before switching to '{selected_branch}'?"
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
                        stdscr.addstr(0, 0, f"Switching to branch '{selected_branch}'...")
                        stdscr.refresh()
                        
                        if stashed:
                            stdscr.addstr(1, 0, "Stashed current changes.")
                            stdscr.refresh()
                        
                        # Checkout branch
                        if self.checkout_branch(selected_branch):
                            stdscr.addstr(2 if stashed else 1, 0, f"Successfully checked out '{selected_branch}'")
                            stdscr.addstr(3 if stashed else 2, 0, "Press any key to continue...")
                            stdscr.refresh()
                            stdscr.getch()
                            self.get_branches()  # Refresh branch list
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
            check=True
        )
    except subprocess.CalledProcessError:
        print("Error: Not in a git repository")
        sys.exit(1)
        
    manager = GitBranchManager()
    curses.wrapper(manager.run)

if __name__ == "__main__":
    main()