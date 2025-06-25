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
                
    def move_branch(self, old_name: str, new_name: str) -> bool:
        """Move/rename a branch."""
        try:
            subprocess.run(
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
        
        self.get_branches()
        
        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()
            
            # Header
            header = "Git Branch Manager - ↑/↓ navigate, Enter checkout, D delete, M rename, q quit"
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
                
                # Prepare display components
                prefix = "* " if branch_info.is_current else "  "
                relative_date = branch_info.format_relative_date()
                
                # Determine age-based color for branch
                days_old = (datetime.now() - branch_info.commit_date).days
                if days_old < 7:
                    date_color = 5  # Magenta for recent
                elif days_old > 30:
                    date_color = 7  # Red for old
                else:
                    date_color = 8  # White for normal
                
                # Truncate commit message if needed
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
            elif key == ord('M'):  # Shift+M for move/rename
                selected_branch = self.branches[self.selected_index].name
                
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
                        self.get_branches()  # Refresh branch list
                        # Update current branch name if it was renamed
                        if selected_branch == self.current_branch:
                            self.current_branch = new_name
                    else:
                        stdscr.addstr(1, 0, f"Failed to rename branch!")
                        stdscr.addstr(2, 0, "Press any key to continue...")
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