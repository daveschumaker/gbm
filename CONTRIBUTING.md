# Contributing to Git Branch Manager

Thank you for your interest in contributing to Git Branch Manager! This document provides guidelines and instructions for contributing to the project.

## Code of Conduct

By participating in this project, you agree to abide by our code of conduct: be respectful, welcoming, and considerate to all contributors.

## How to Contribute

### Reporting Issues

1. **Check existing issues** first to avoid duplicates
2. **Use the issue template** if provided
3. **Include details**:
   - Git Branch Manager version (`gbm --version` or check `__version__` in the file)
   - Python version (`python3 --version`)
   - Operating system and terminal
   - Steps to reproduce the issue
   - Expected vs actual behavior

### Suggesting Features

1. **Open an issue** with the "enhancement" label
2. **Describe the feature** and its use case
3. **Consider the impact** on existing functionality
4. **Be open to discussion** about implementation

### Submitting Pull Requests

1. **Fork the repository** and create a feature branch:

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**:

   - Follow the existing code style
   - Add/update tests if applicable
   - Update documentation as needed
   - Test your changes thoroughly

3. **Commit your changes**:

   ```bash
   git commit -m "Add feature: brief description"
   ```

   - Use clear, descriptive commit messages
   - Reference issue numbers when applicable (#123)

4. **Push to your fork**:

   ```bash
   git push origin feature/your-feature-name
   ```

5. **Create a Pull Request**:
   - Fill out the PR template
   - Link related issues
   - Describe what changes you made and why

## Development Guidelines

### Code Style

1. **Python Style**:

   - Follow PEP 8 guidelines
   - Use meaningful variable and function names
   - Keep functions focused and small
   - Add type hints where beneficial

2. **No Comments Policy**:

   - Write self-documenting code
   - Use descriptive names instead of comments
   - Docstrings are encouraged for functions and classes

3. **Error Handling**:
   - Handle errors gracefully
   - Provide helpful error messages to users
   - Never crash the terminal session

### Project Structure

The project maintains a simple single-file structure:

- `git-branch-manager.py` - All application code
- Keep all functionality in one file for easy distribution
- Use classes and functions to organize code logically

### UI/UX Guidelines

1. **Consistency**:

   - Follow existing UI patterns
   - Maintain the professional, nano-style interface
   - Keep keyboard shortcuts intuitive

2. **Performance**:

   - Use batch Git operations where possible
   - Minimize subprocess calls
   - Keep the UI responsive

3. **Cross-platform**:
   - Test on different terminals (iTerm2, Terminal.app, gnome-terminal, etc.)
   - Ensure proper rendering on various terminal sizes
   - Handle both macOS and Linux environments

### Testing

While there's no formal test suite yet, please:

1. **Manual Testing**:

   - Test all affected functionality
   - Test edge cases (empty repos, no remotes, etc.)
   - Test with both regular repos and worktrees
   - Test with large repositories

2. **Terminal Testing**:
   - Test with narrow terminals (< 80 chars)
   - Test with various color schemes
   - Verify no text overflow or rendering issues

### Documentation

1. **Update README.md** if you:

   - Add new features
   - Change keyboard shortcuts
   - Modify installation steps

2. **Update CLAUDE.md** if you:
   - Add significant new functionality
   - Change core architecture
   - Modify development workflows

## Version Updates

When your PR is accepted:

- Maintainers will handle version bumps
- Your changes will be noted in CHANGELOG.md
- You'll be credited in the release notes

## Getting Help

- Open an issue for questions
- Check existing issues and discussions
- Review the codebase for examples

## Recognition

All contributors will be recognized in the project. We value:

- Code contributions
- Bug reports
- Feature suggestions
- Documentation improvements
- Testing and feedback

Thank you for helping make Git Branch Manager better!
