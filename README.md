# Git Branch Manager

A powerful terminal-based (TUI) Git branch management tool that provides an interactive interface for managing Git branches with rich visual feedback and advanced features.

![Git Branch Manager](https://img.shields.io/badge/git-branch--manager-blue)
![Python](https://img.shields.io/badge/python-3.6%2B-green)
![License](https://img.shields.io/badge/license-MIT-blue)

## Features

### Core Functionality
- **Interactive TUI**: Navigate branches with arrow keys in a clean, professional interface
- **Branch Operations**: Checkout, delete, rename, and create branches with ease
- **Visual Indicators**: 
  - `*` Current branch
  - `↓` Remote branches
  - `[modified]` Uncommitted changes
  - `[unpushed]` Local branches not on remote
  - `[merged]` Branches merged into main/master
  - `[worktree]` Branches in other worktrees
- **Smart Stash Management**: 
  - Automatic prompt to stash changes when switching branches
  - Track and recover stashes with 'S' key
  - Branch-specific stash detection
- **Remote Branch Support**: Toggle viewing and checkout remote branches
- **Branch Protection**: Extra confirmation for deleting main/master branches
- **Worktree Support**: Shows worktree indicators and prevents conflicts

### Advanced Features
- **Powerful Filtering**: 
  - Search by name (`/`)
  - Filter by author (`a`)
  - Hide old branches (`o`)
  - Hide merged branches (`m`)
  - Filter by prefix (`p`)
- **Smart Sorting**: Branches sorted by most recent commits
- **Color Coding**: Age-based coloring for quick visual scanning
- **Browser Integration**: Open branches in GitHub, GitLab, Bitbucket, etc.
- **Performance Optimized**: Uses batch operations for fast loading in large repos
- **Professional UI**: Nano-style footer with command shortcuts

## Installation

### Requirements
- Python 3.6+
- Git
- Terminal with color support

### Quick Install (curl)

```bash
# Download and install to /usr/local/bin (requires sudo)
sudo curl -L https://raw.githubusercontent.com/daveschumaker/git-bm/main/git-branch-manager.py -o /usr/local/bin/git-bm
sudo chmod +x /usr/local/bin/git-bm

# Or install to ~/.local/bin (no sudo required)
mkdir -p ~/.local/bin
curl -L https://raw.githubusercontent.com/daveschumaker/git-bm/main/git-branch-manager.py -o ~/.local/bin/git-bm
chmod +x ~/.local/bin/git-bm

# Now you can run from anywhere
git-bm
```

### Install from Source

```bash
# Clone the repository
git clone https://github.com/daveschumaker/git-bm.git
cd git-bm

# Make executable
chmod +x git-branch-manager.py

# Option 1: Run directly
./git-branch-manager.py

# Option 2: Create symlink (recommended)
ln -s $(pwd)/git-branch-manager.py ~/.local/bin/git-bm

# Now you can run from anywhere
git-bm
```

### Alternative: Install as Git Alias

```bash
# Add as git alias
git config --global alias.bm '!python3 /path/to/git-branch-manager.py'

# Now use as:
git bm
```

## Usage

### Basic Navigation
- `↑/↓` or `j/k`: Navigate through branches
- `Page Up/Page Down`: Navigate by page
- `Home/End`: Jump to first/last branch
- `Enter`: Checkout selected branch
- `q` or `ESC`: Quit (ESC also clears filters)

### Branch Operations
- `D`: Delete selected branch (with confirmation)
- `M`: Move/rename branch
- `N`: Create new branch from current
- `S`: Pop last stash (if available)

### Filtering & Search
- `/`: Search branches by name
- `a`: Toggle author filter (show only your branches)
- `o`: Toggle old branches filter (>3 months)
- `m`: Toggle merged branches filter
- `p`: Filter by prefix (feature/, bugfix/, etc.)
- `c`: Clear all filters

### Remote & Browser
- `t`: Toggle remote branches view
- `f`: Fetch from remote
- `b`: Open branch in browser
- `B`: Open branch comparison/PR page
- `r`: Reload branch list

### Help
- `?`: Show help screen

## Configuration

Git Branch Manager supports configuration via `~/.config/git-branch-manager/config.json`:

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

### Platform Detection

The tool automatically detects your Git hosting platform:
- GitHub
- GitLab
- Bitbucket (Cloud & Server)
- Azure DevOps
- Custom platforms (via configuration)

## Visual Indicators

### Branch Status
- `*` Current branch (highlighted in green)
- `↓` Remote branch
- `  ` Local branch

### Branch State
- `[modified]`: Has uncommitted changes
- `[unpushed]`: Exists locally but not on remote
- `[merged]`: Has been merged into main/master
- `[worktree]`: Checked out in another worktree

### Color Coding
- **Green**: Current branch
- **Cyan**: Branch names
- **Yellow**: Modified indicator
- **Magenta**: Recent branches (<1 week)
- **Blue**: Commit info
- **Red**: Old branches (>1 month)

## Keyboard Shortcuts

| Key | Action | Context |
|-----|--------|---------|
| `↑`/`↓` | Navigate branches | Always |
| `j`/`k` | Navigate branches (Vim-style) | Always |
| `PgUp`/`PgDn` | Navigate by page | Always |
| `Home`/`End` | Jump to first/last | Always |
| `Enter` | Checkout branch | Branch selected |
| `D` | Delete branch | Local branch selected |
| `M` | Move/rename branch | Branch selected |
| `N` | New branch | Always |
| `S` | Pop stash | Stash available |
| `/` | Search | Always |
| `a` | Author filter | Always |
| `o` | Old branches filter | Always |
| `m` | Merged filter | Always |
| `p` | Prefix filter | Always |
| `c` | Clear filters | Filters active |
| `t` | Toggle remotes | Always |
| `f` | Fetch | Always |
| `r` | Reload | Always |
| `b` | Open in browser | Branch selected |
| `B` | Compare/PR | Branch selected |
| `?` | Help | Always |
| `q` | Quit | Always |
| `ESC` | Clear filters/Quit | Always |

## Examples

### Daily Workflow

```bash
# Start branch manager
git-bm

# Press 't' to see remote branches
# Press '/' to search for a feature
# Press Enter to checkout
# Press 'N' to create new branch
# Press 'D' to delete old branches
```

### Cleanup Old Branches

```bash
git-bm
# Press 'o' to hide old branches
# Press 'm' to hide merged branches
# Review remaining branches
# Press 'D' on branches to delete
```

### Find Your Branches

```bash
git-bm
# Press 'a' to show only your branches
# Navigate and manage your work
```

## Tips & Tricks

1. **Quick Filter Clear**: Press `ESC` to clear all filters at once
2. **Safe Stashing**: The tool remembers stashes it creates and shows them in the header
3. **Worktree Safety**: Can't checkout branches that are active in other worktrees
4. **Protected Branches**: Main and master branches require extra confirmation to delete
5. **Remote Checkout**: Select a remote branch and press Enter to create a local tracking branch
6. **Quick Browser**: Press 'b' to instantly view a branch on GitHub/GitLab/etc.

## Troubleshooting

### Common Issues

1. **"No branches found"**
   - Ensure you're in a Git repository
   - Try pressing 'f' to fetch from remote

2. **Colors not showing**
   - Ensure your terminal supports colors
   - Try setting `TERM=xterm-256color`

3. **Can't delete remote branches**
   - This is by design - only local branches can be deleted
   - To remove remote branches, use standard git commands

4. **Spinner not animating during fetch**
   - Requires Python threading support
   - Check Python installation

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Development Setup

```bash
# Clone your fork
git clone https://github.com/yourusername/git-branch-manager.git
cd git-branch-manager

# Create a branch
git checkout -b feature/your-feature

# Make changes and test
python3 git-branch-manager.py

# Submit PR
```

## License

MIT License - see LICENSE file for details

## Acknowledgments

- Inspired by interactive Git tools like lazygit and gitui
- Built with Python's curses library
- UI design influenced by nano and micro editors

---

**Note**: This tool is designed for local branch management. For advanced Git operations, please use the standard Git CLI.