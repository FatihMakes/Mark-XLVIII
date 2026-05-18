# MARK XXXIX - Development Documentation

## Development Setup

### Prerequisites
- Git
- Python 3.11+
- Virtual environment tool
- Code editor (VS Code recommended)
- Docker (optional, for testing)

### Initial Setup
```bash
# Clone repository
git clone <repository-url>
cd MyJarvis

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install development dependencies
pip install -r requirements.txt
pip install pytest pytest-cov black flake8 mypy

# Setup pre-commit hooks (optional)
pip install pre-commit
pre-commit install

# Install Playwright browsers
playwright install
```

### Repository Structure Best Practices
- Keep `main.py` focused on orchestration
- Isolate action logic in `actions/` modules
- Centralize AI logic in `agent/` modules
- Use `memory/` for all persistent storage
- Store configs in `config/` only

## Code Standards

### Style Guide (PEP 8)

**Module Layout:**
```python
"""
Module description and purpose.
"""

# Standard library imports
import os
import sys
from pathlib import Path
from typing import Callable, Dict, Optional

# Third-party imports
import numpy as np

# Local imports
from memory.memory_manager import load_memory

# Constants
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30

# Functions
def function_name(param: str) -> bool:
    """
    Brief one-line description.
    
    Longer description if needed.
    
    Args:
        param: Parameter description
        
    Returns:
        Return value description
        
    Raises:
        ExceptionType: When it's raised
    """
    pass

# Classes
class ClassName:
    """Class description."""
    
    def __init__(self, name: str):
        self.name = name
    
    def method_name(self) -> str:
        """Method description."""
        return self.name
```

### Naming Conventions
```python
# Constants (UPPER_SNAKE_CASE)
MAX_RETRIES = 3

# Functions & variables (snake_case)
def process_data(input_data):
    processed_value = 0
    return processed_value

# Classes (PascalCase)
class DataProcessor:
    pass

# Private methods/attributes (leading underscore)
def _internal_method():
    _private_var = 0
```

### Type Hints
```python
from typing import Callable, Dict, List, Optional, Union

def process_items(
    items: List[Dict[str, any]],
    callback: Optional[Callable] = None
) -> Union[bool, str]:
    """Function with type hints."""
    pass
```

### Docstring Format
```python
def calculate_total(prices: List[float], tax_rate: float = 0.1) -> float:
    """
    Calculate total with tax.
    
    Args:
        prices: List of item prices
        tax_rate: Tax rate as decimal (default: 0.1 = 10%)
    
    Returns:
        Total price including tax
        
    Raises:
        ValueError: If prices contain negative values
        
    Example:
        >>> calculate_total([10.0, 20.0])
        33.0
    """
    if any(p < 0 for p in prices):
        raise ValueError("Prices must be non-negative")
    return sum(prices) * (1 + tax_rate)
```

## Testing

### Unit Testing
```python
# tests/test_memory_manager.py
import unittest
from memory.memory_manager import load_memory, update_memory

class TestMemoryManager(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures."""
        self.memory = load_memory()
    
    def test_update_memory(self):
        """Test memory update functionality."""
        update_memory("preferences", "timezone", "EST")
        updated = load_memory()
        self.assertEqual(updated["preferences"]["timezone"], "EST")
    
    def test_memory_size_limit(self):
        """Test memory size constraints."""
        # Test implementation
        pass

if __name__ == '__main__':
    unittest.main()
```

### Running Tests
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test
pytest tests/test_memory_manager.py::TestMemoryManager::test_update_memory

# Run with verbose output
pytest -v
```

### Integration Testing
```python
# tests/test_integration.py
def test_voice_to_action_flow():
    """Test complete voice command flow."""
    # Simulate voice input
    # Check Gemini API integration
    # Verify tool execution
    # Check response generation
    pass
```

## Debugging

### Debug Logging
```python
import logging

# In main.py or module
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

logger.debug("Debug information")
logger.info("General information")
logger.warning("Warning message")
logger.error("Error message", exc_info=True)
```

### Debugging Tools
```bash
# Python debugger
python -m pdb main.py

# VS Code debugger (add to .vscode/launch.json)
```

### launch.json Configuration
```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: Main",
            "type": "python",
            "request": "launch",
            "program": "${workspaceFolder}/main.py",
            "console": "integratedTerminal",
            "justMyCode": true,
            "env": {
                "PYTHONPATH": "${workspaceFolder}"
            }
        }
    ]
}
```

## Creating New Modules

### New Action Module Checklist
- [ ] Create `actions/new_action.py`
- [ ] Implement main function with standard signature
- [ ] Add comprehensive docstrings
- [ ] Include error handling
- [ ] Test independently
- [ ] Add tool definition to planner prompt
- [ ] Register in main.py executor
- [ ] Update API reference docs
- [ ] Add unit tests

### New Agent Module Checklist
- [ ] Create `agent/new_module.py`
- [ ] Follow project code style
- [ ] Add type hints
- [ ] Document public API
- [ ] Test with existing components
- [ ] Update architecture docs

### Example: New Action Module
```python
# actions/example_action.py
"""
Example Action Module
Purpose: Demonstrate action module structure
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)

def example_action(params: Dict) -> Dict:
    """
    Perform example action.
    
    Args:
        params: {
            "input": str - Input parameter
        }
    
    Returns:
        {
            "success": bool,
            "result": str,
            "error": str (if failed)
        }
    """
    try:
        input_value = params.get("input", "")
        
        logger.info(f"Processing: {input_value}")
        
        if not input_value:
            return {
                "success": False,
                "error": "Input parameter is required"
            }
        
        # Process input
        result = f"Processed: {input_value.upper()}"
        
        logger.info("Action completed successfully")
        
        return {
            "success": True,
            "result": result
        }
    
    except Exception as e:
        logger.error(f"Action failed: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


# Unit test
if __name__ == "__main__":
    test_result = example_action({"input": "test"})
    print(test_result)
```

## Performance Optimization

### Profiling
```python
import cProfile
import pstats
from io import StringIO

def profile_function():
    profiler = cProfile.Profile()
    profiler.enable()
    
    # Your code here
    
    profiler.disable()
    stream = StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats('cumulative')
    stats.print_stats(20)
    print(stream.getvalue())
```

### Memory Profiling
```bash
pip install memory-profiler

python -m memory_profiler main.py
```

### Optimization Techniques
```python
# Use generators for large datasets
def process_large_file(filepath):
    with open(filepath) as f:
        for line in f:
            yield line.strip()

# Cache results
from functools import lru_cache

@lru_cache(maxsize=128)
def expensive_operation(x):
    return x ** 2

# Use list comprehensions
result = [x * 2 for x in range(1000)]  # Faster than loop

# Minimize API calls
# Batch operations when possible
```

## Continuous Integration

### GitHub Actions Example
```yaml
# .github/workflows/tests.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.11', '3.12']
    
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-cov
    
    - name: Run tests
      run: pytest --cov
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

## Documentation

### Docstring Examples
```python
def complex_function(data: List[Dict], callback: Callable = None) -> Optional[str]:
    """
    Process data with optional callback.
    
    This function iterates through data dictionaries and applies
    optional processing via callback function.
    
    Args:
        data: List of dictionaries containing data items
        callback: Optional function to apply to each item.
                 Should accept dict and return str.
    
    Returns:
        Concatenated results or None if no callback
    
    Raises:
        TypeError: If data is not a list
        ValueError: If data items are not dicts
    
    Example:
        >>> data = [{"id": 1, "name": "test"}]
        >>> process = lambda x: x["name"]
        >>> result = complex_function(data, process)
        >>> print(result)
        "test"
    
    Note:
        This function modifies internal state.
        Not thread-safe.
    """
    pass
```

### README For Module
```python
# Module: actions/special_action.py
# Purpose: Execute special operations
# Dependencies: requests, beautifulsoup4
# Status: Stable
# Last Updated: 2024-01-15

# Usage:
# from actions.special_action import special_action
# result = special_action({"parameter": "value"})
```

## Release Management

### Version Bumping
```bash
# Update version in pyproject.toml
# Create git tag
git tag v0.2.0
git push origin v0.2.0

# Create release notes
```

### Changelog Format
```markdown
# Changelog

## [0.2.0] - 2024-01-15
### Added
- New feature X
- Improved performance of Y

### Fixed
- Bug in Z
- Crash when doing A

### Changed
- Updated dependency X to v1.0

## [0.1.0] - 2024-01-01
### Added
- Initial release
```

## Troubleshooting Development Issues

### Virtual Environment Issues
```bash
# Recreate venv
rm -rf venv
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Import Path Issues
```python
# Add to sys.path if needed
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
```

### Dependency Conflicts
```bash
# Check installed packages
pip list

# Clear cache and reinstall
pip cache purge
pip install --force-reinstall -r requirements.txt
```

### Git Issues
```bash
# Reset to remote
git fetch origin
git reset --hard origin/main

# Clean untracked files
git clean -fd
```

## Resources

- [PEP 8 Style Guide](https://www.python.org/dev/peps/pep-0008/)
- [Python Type Hints](https://docs.python.org/3/library/typing.html)
- [Google Gemini API Docs](https://ai.google.dev/docs)
- [PyQt6 Documentation](https://www.riverbankcomputing.com/software/pyqt/intro)
- [Python Logging](https://docs.python.org/3/library/logging.html)
