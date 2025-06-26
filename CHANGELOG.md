# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Command-line argument parsing:
  - `--version`/`-v` flag to show version from VERSION file
  - `--help`/`-h` flag to display usage and key bindings
  - `--directory`/`-d` flag to specify git repository directory
- Improved configuration validation with graceful fallback
  - Clear warnings for invalid configuration values
  - Always falls back to safe defaults
  - Config errors no longer crash the application
- New configuration option `prevent_browser_for_merged`
  - Prevents opening browser for merged branches
  - Useful for workflows where merged branches are deleted from remote
  - Shows informative message explaining why browser was blocked
  - Configurable via `~/.config/git-branch-manager/config.json`

### Fixed
- Author filter email format mismatch bug
  - Git for-each-ref returns emails in `<email@example.com>` format
  - Git config returns emails without angle brackets
  - Fixed by stripping angle brackets for consistent comparison
  - Author filter now correctly shows user's branches

### Changed
- Version management now uses VERSION file as single source of truth
  - Removed hardcoded version in code
  - Loads version dynamically with fallback to 'unknown'

## [1.0.0] - 2025-06-25

### Added

- Initial release of Git Branch Manager
- Interactive TUI for managing Git branches with curses
- Branch navigation with arrow keys, j/k, Page Up/Down, Home/End
- Branch operations: checkout, delete, rename, create new branches
- Visual indicators for branch status:
  - Current branch (\*) with green highlighting
  - Remote branches (↓)
  - Modified files indicator [modified]
  - Unpushed branches indicator [unpushed]
  - Merged branches indicator [merged]
  - Worktree branches indicator [worktree]
- Smart stash management:
  - Automatic stash prompt when switching branches with uncommitted changes
  - Track and recover stashes with 'S' key
  - Branch-specific stash detection
- Remote branch support with toggle viewing ('t')
- Branch filtering capabilities:
  - Search by name (/)
  - Filter by author (a)
  - Hide old branches >3 months (o)
  - Hide merged branches (m)
  - Filter by prefix (p)
  - Clear all filters (c or ESC)
- Browser integration:
  - Open branch in web browser (b)
  - Open branch comparison/PR page (B)
  - Support for GitHub, GitLab, Bitbucket, Azure DevOps
  - Configurable custom platforms
- Professional UI with nano-style footer
- Color-coded branch age visualization
- Fetch from remote (f) with animated loading spinner
- Reload branch list (r)
- Built-in help system (?)
- Configuration support via ~/.config/git-branch-manager/config.json
- Performance optimized using git for-each-ref batch operations
- Support for Git worktrees
- Branch protection for main/master branches
