# Git Branch Manager - AI Assistant Guide

This document provides context and guidance for AI assistants working on the git-branch-manager project.

## Project Overview

Git Branch Manager is a terminal-based (TUI) Git branch management tool written in Python using the curses library. It provides an interactive interface for managing Git branches with rich visual feedback and advanced features.

## Key Features

### Core Functionality
- **Interactive TUI**: Navigate branches with arrow keys
- **Branch Operations**: Checkout, delete, rename branches
- **Visual Indicators**: Current branch (*), remote branches (↓), modified files
- **Stash Management**: Automatic prompt to stash changes when switching branches
- **Stash Recovery**: Track and recover last stash with 'S' key
- **Remote Branch Support**: Toggle viewing and checkout remote branches
- **Branch Creation**: Create new branches with 'N' key
- **Branch Protection**: Extra confirmation for deleting main/master branches
- **Performance Optimized**: Uses batch operations for fast loading in large repos
- **Browser Integration**: Open branches in web browser (GitHub, GitLab, Bitbucket, etc.)

### Advanced Features
- **Branch Filtering**: Search by name, author, age, or prefix
- **Smart Sorting**: Branches sorted by most recent commits first
- **Color Coding**: Age-based coloring for quick visual scanning
- **Help System**: Built-in help screen (?)
- **Reload/Refresh**: Update branch list
- **Safe Display**: Handles long branch names and narrow terminals

## Architecture

### Main Components

1. **BranchInfo (NamedTuple)**
   - Stores branch metadata: name, commit info, uncommitted changes flag, remote info
   - Has method for formatting relative dates
   - No longer includes merge/PR status (removed for performance)

2. **GitPlatformURLBuilder Class**
   - Detects Git hosting platform from remote URL
   - Builds platform-specific URLs for viewing branches and creating PRs
   - Supports GitHub, GitLab, Bitbucket (Cloud & Server), Azure DevOps
   - Extensible via configuration for custom platforms

3. **GitBranchManager Class**
   - Core application logic
   - Manages branch list, UI state, filtering, and operations
   - Handles git commands via subprocess with working directory support
   - Loads/saves configuration from ~/.config/git-branch-manager/

### Key Methods
- `get_branches()`: Fetches branches using optimized batch operations
- `_get_batch_branch_info()`: Uses git for-each-ref for performance
- `safe_addstr()`: Prevents terminal width overflow errors
- `has_active_filters()` / `clear_all_filters()`: Filter management
- `checkout_branch()`: Handles local and remote checkouts
- `delete_branch()`: Safe branch deletion with force fallback
- `move_branch()`: Rename/move branches
- `show_help()`: Display help screen
- `run()`: Main curses event loop

## Git Integration

### Commands Used
- `git for-each-ref`: Batch fetch branch info (performance optimization)
- `git branch`: List local branches
- `git branch -r`: List remote branches
- `git branch -d/-D`: Delete branches
- `git branch -m`: Move/rename branches
- `git checkout`: Switch branches
- `git checkout -b`: Create tracking branch from remote
- `git fetch --all`: Fetch all remotes
- `git status --porcelain`: Check for uncommitted changes
- `git stash`: Stash changes

### Platform Support
- Works in regular Git repositories and worktrees
- Works when run via symlink from any directory
- All Git platforms supported (GitHub, GitLab, Bitbucket, etc.)

## UI/UX Design

### Key Bindings
- `↑/↓`: Navigate branches
- `Enter`: Checkout selected branch
- `D`: Delete branch (with confirmation, protected branches need extra confirmation)
- `M`: Move/rename branch (with input dialog)
- `N`: Create new branch from current (with optional checkout)
- `S`: Pop last stash (if available)
- `t`: Toggle remote branches (fetches automatically)
- `f`: Fetch from remote
- `r`: Reload branch list
- `b`: Open branch in browser
- `B`: Open branch comparison/PR creation in browser
- `/`: Search branches by name
- `a`: Toggle author filter (show only your branches)
- `o`: Toggle old branches filter (hide >3 months)
- `p`: Filter by prefix (feature/, bugfix/, etc)
- `c`: Clear all filters
- `?`: Show help
- `q`: Quit
- `ESC`: Clear filters if active, otherwise quit

### Visual Elements
- **Prefixes**: `*` (current), `↓` (remote), `  ` (local)
- **Status Tags**: `[modified]` for uncommitted changes
- **Header Indicators**: `[Stash: stash@{0}]` when a stash is available to pop
- **Colors**: 
  - Green: Current branch
  - Cyan: Branch names
  - Yellow: Modified indicator
  - Magenta: Recent branches (<1 week)
  - Blue: Commit hashes
  - Red: Old branches (>1 month)
- **Sorting**: All branches sorted by most recent commit first

## Development Guidelines

### Code Style
- No comments unless specifically requested
- Use type hints (typing module)
- Handle errors gracefully
- Use subprocess for git commands
- Follow existing patterns in the codebase

### Testing Approach
- Manual testing via terminal
- Test with both regular repos and worktrees
- Verify GitHub and non-GitHub repo behavior
- Check edge cases (no branches, no remotes, etc.)

### Common Tasks

#### Adding a New Command
1. Add key handler in the main event loop
2. Implement the functionality method
3. Update help text
4. Update header if needed

#### Adding Status Indicators
1. Add field to BranchInfo
2. Update get_branch_info() to populate it
3. Add visual indicator in display logic
4. Update help text

## Performance Optimizations
- Uses `git for-each-ref` for batch operations instead of individual `git log` calls
- Removed expensive merge/PR checking for faster loading
- Efficient branch sorting by commit date
- Loading indicator for better UX during operations

## Known Limitations
- Remote branch operations require network access
- Very long branch names may be truncated in narrow terminals

## Recent Features Added
- **Stash Tracking**: The app now tracks the last stash it creates and shows it in the header
- **Stash Recovery**: Press 'S' to pop the last stash created by the app
- **Branch Protection**: Main and master branches require extra confirmation before deletion
- **Branch Creation**: Press 'N' to create a new branch with optional checkout
- **Browser Integration**: Press 'b' to open branch in browser, 'B' for compare/PR view
- **Auto-fetch on Remote Toggle**: Pressing 't' now automatically fetches before showing remotes
- **Multi-platform Browser Support**: Automatically detects GitHub, GitLab, Bitbucket, Azure DevOps, etc.

## Future Enhancement Ideas
- Multiple selection for bulk operations
- Branch graph visualization
- Config file for preferences (e.g., to re-enable merge/PR checks, customize protected branches)
- Undo functionality
- Export branch list

## Debugging Tips
- Check git command outputs with capture_output
- Verify curses coordinates don't exceed terminal bounds
- Test with various terminal sizes
- Ensure proper error handling for subprocess calls

## Configuration

The app supports configuration via `~/.config/git-branch-manager/config.json`:

```json
{
  "platform": "auto",              // auto-detect or: github, gitlab, bitbucket-cloud, bitbucket-server, custom
  "default_base_branch": "main",   // default branch for comparisons
  "browser_command": "open",       // command to open browser (open on macOS, xdg-open on Linux)
  "custom_patterns": {             // for custom Git hosting platforms
    "branch": "https://git.example.com/{repo}/tree/{branch}",
    "compare": "https://git.example.com/{repo}/compare/{base}...{branch}"
  }
}
```

## Dependencies
- Python 3.x
- curses (built-in)
- git (command-line)
- webbrowser (built-in)

## Files
- `git-branch-manager.py`: Main application file
- `CLAUDE.md`: This file

## Quick Command Reference

```bash
# Run the application
python3 git-branch-manager.py

# Install as command (example)
ln -s /path/to/git-branch-manager.py ~/my-scripts/git-bm
chmod +x ~/my-scripts/git-bm

# Key git commands the app uses
git for-each-ref --format="..."    # Batch fetch branch info
git branch                          # List local branches
git branch -r                       # List remote branches
git fetch --all                     # Fetch all remotes
git checkout <branch>               # Switch branch
git branch -d <branch>              # Delete branch
git branch -m <old> <new>           # Rename branch
git status --porcelain              # Check for uncommitted changes
git stash push -m "message"         # Stash changes
git stash list -1                   # Get last stash reference
git stash pop stash@{0}             # Pop specific stash
git branch <name>                   # Create new branch
git checkout -b <name>              # Create and checkout new branch
```