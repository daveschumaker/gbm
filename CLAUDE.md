# Git Branch Manager - AI Assistant Guide

This document provides context and guidance for AI assistants working on the git-branch-manager project.

## Project Overview

Git Branch Manager is a terminal-based (TUI) Git branch management tool written in Python using the curses library. It provides an interactive interface for managing Git branches with rich visual feedback and advanced features.

## Key Features

### Core Functionality
- **Interactive TUI**: Navigate branches with arrow keys
- **Branch Operations**: Checkout, delete, rename branches
- **Visual Indicators**: Current branch (*), remote branches (↓), modified files, PR status, merge status
- **Stash Management**: Automatic prompt to stash changes when switching branches
- **Remote Branch Support**: Toggle viewing and checkout remote branches

### Advanced Features
- **PR Detection**: Shows open pull requests (GitHub only via `gh` CLI)
- **Merge Status**: Indicates if branches are merged into main/master
- **Color Coding**: Age-based coloring, status indicators
- **Help System**: Built-in help screen (?)
- **Reload/Refresh**: Update branch list and status

## Architecture

### Main Components

1. **BranchInfo (NamedTuple)**
   - Stores all branch metadata
   - Includes: name, commit info, status flags, remote info
   - Has method for formatting relative dates

2. **GitBranchManager Class**
   - Core application logic
   - Manages branch list, UI state, and operations
   - Handles git commands via subprocess

### Key Methods
- `get_branches()`: Fetches local and remote branches
- `get_branch_info()`: Gets detailed info for a single branch
- `checkout_branch()`: Handles local and remote checkouts
- `delete_branch()`: Safe branch deletion with force fallback
- `move_branch()`: Rename/move branches
- `show_help()`: Display help screen
- `run()`: Main curses event loop

## Git Integration

### Commands Used
- `git branch`: List local branches
- `git branch -r`: List remote branches
- `git branch -d/-D`: Delete branches
- `git branch -m`: Move/rename branches
- `git checkout`: Switch branches
- `git checkout -b`: Create tracking branch from remote
- `git fetch --all`: Fetch all remotes
- `git cherry`: Check if branch is merged
- `git log`: Get commit info
- `git status --porcelain`: Check for uncommitted changes
- `git stash`: Stash changes
- `gh pr list`: Get PR info (GitHub only)

### Platform Support
- Works in regular Git repositories and worktrees
- GitHub: Full support including PR detection
- Bitbucket/GitLab: All features except PR detection

## UI/UX Design

### Key Bindings
- `↑/↓`: Navigate branches
- `Enter`: Checkout selected branch
- `D`: Delete branch (with confirmation)
- `M`: Move/rename branch (with input dialog)
- `t`: Toggle remote branches
- `f`: Fetch from remote
- `r`: Reload branch list
- `?`: Show help
- `q/ESC`: Quit

### Visual Elements
- **Prefixes**: `*` (current), `↓` (remote), `  ` (local)
- **Status Tags**: `[modified]`, `[PR#123]`, `[merged]`
- **Colors**: 
  - Green: Current branch
  - Cyan: Branch names, PR status
  - Yellow: Modified indicator
  - Magenta: Recent branches (<1 week), merged status
  - Blue: Commit hashes
  - Red: Old branches (>1 month)

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

## Known Limitations
- PR detection only works with GitHub (requires `gh` CLI)
- Remote branch operations require network access
- Some git operations may be slow on large repos
- Terminal size affects display quality

## Future Enhancement Ideas
- Search/filter branches
- Multiple selection for bulk operations
- Branch graph visualization
- Integration with more Git platforms
- Config file for preferences
- Undo functionality

## Debugging Tips
- Check git command outputs with capture_output
- Verify curses coordinates don't exceed terminal bounds
- Test with various terminal sizes
- Ensure proper error handling for subprocess calls

## Dependencies
- Python 3.x
- curses (built-in)
- git (command-line)
- gh CLI (optional, for GitHub PR detection)

## Files
- `git-branch-manager.py`: Main application file
- `CLAUDE.md`: This file

## Quick Command Reference

```bash
# Run the application
python3 git-branch-manager.py

# Common git commands the app uses
git branch                  # List local branches
git branch -r              # List remote branches
git fetch --all            # Fetch all remotes
git checkout <branch>      # Switch branch
git branch -d <branch>     # Delete branch
git branch -m <old> <new>  # Rename branch
```