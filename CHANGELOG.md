# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
