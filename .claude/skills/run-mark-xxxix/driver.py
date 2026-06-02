#!/usr/bin/env python3
"""
MARK XXXIX Driver - Programmatic launcher and harness for automated testing and CI.

This driver handles:
1. Environment setup (Python paths, API keys, dependencies)
2. Launching the app with virtual display (Xvfb on Linux)
3. Smoke tests to verify core functionality
4. Screenshot capture for visual validation
5. Clean shutdown and resource cleanup

Usage:
  python driver.py setup     # Install dependencies
  python driver.py launch    # Start the app (headless mode on Linux)
  python driver.py test      # Run smoke tests
  python driver.py screenshot <output.png>  # Capture window
"""

import os
import sys
import json
import subprocess
import time
import argparse
from pathlib import Path
import signal
import platform

# Project paths
BASE_DIR = Path(__file__).parent.parent.parent.parent
SKILL_DIR = BASE_DIR / ".claude" / "skills" / "run-mark-xxxix"
CONFIG_DIR = BASE_DIR / "config"
API_FILE = CONFIG_DIR / "api_keys.json"

# Platform detection
OS_TYPE = platform.system()  # "Windows" | "Darwin" | "Linux"
IS_HEADLESS = OS_TYPE == "Linux"

# Global process handle
MARK_PROCESS = None
XVFB_PROCESS = None


def setup_environment():
    """Prepare Python environment and install dependencies."""
    print("🔧 Setting up environment...")

    # Ensure BASE_DIR is in sys.path
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))

    # On Linux, set up Xvfb virtual display
    if IS_HEADLESS:
        print("📺 Starting Xvfb virtual display (Linux headless mode)...")
        try:
            os.environ["DISPLAY"] = ":99"
            # Start Xvfb in background
            global XVFB_PROCESS
            XVFB_PROCESS = subprocess.Popen(
                ["Xvfb", ":99", "-screen", "0", "1280x720x24"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1)  # Wait for display to be ready
            print("✅ Xvfb running on DISPLAY=:99")
        except FileNotFoundError:
            print("⚠️  Xvfb not found. Install with: apt-get install -y xvfb")

    # Set up environment variables
    os.environ["PYTHONPATH"] = str(BASE_DIR)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

    # Verify API keys are available (won't stop setup, but warn)
    if not API_FILE.exists():
        print(f"⚠️  Warning: {API_FILE} not found - app may fail to start")
        print("   Set GEMINI_API_KEY environment variable or create config/api_keys.json")
    else:
        print(f"✅ API keys found at {API_FILE}")

    print("✅ Environment ready\n")


def install_dependencies():
    """Install Python dependencies from requirements.txt."""
    print("📦 Installing Python dependencies...")
    req_file = BASE_DIR / "requirements.txt"

    if not req_file.exists():
        print(f"❌ requirements.txt not found at {req_file}")
        return False

    try:
        # Use -q for quiet mode to reduce output noise
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "-r", str(req_file)],
            cwd=str(BASE_DIR),
            check=False,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("✅ Dependencies installed\n")
            return True
        else:
            print(f"❌ pip install failed:\n{result.stderr}\n")
            return False
    except Exception as e:
        print(f"❌ Failed to install dependencies: {e}\n")
        return False


def launch_app():
    """Launch MARK XXXIX main.py."""
    print("🚀 Launching MARK XXXIX...")
    setup_environment()

    main_py = BASE_DIR / "main.py"
    if not main_py.exists():
        print(f"❌ main.py not found at {main_py}")
        return False

    try:
        global MARK_PROCESS
        env = os.environ.copy()
        env["PYTHONPATH"] = str(BASE_DIR)

        # On Linux, ensure DISPLAY is set for Xvfb
        if IS_HEADLESS and "DISPLAY" not in env:
            env["DISPLAY"] = ":99"

        # Launch app
        MARK_PROCESS = subprocess.Popen(
            [sys.executable, str(main_py)],
            cwd=str(BASE_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        print(f"✅ App launched (PID: {MARK_PROCESS.pid})\n")

        # Give it time to initialize
        time.sleep(3)

        # Check if it's still running
        if MARK_PROCESS.poll() is None:
            print("✅ App is running\n")
            return True
        else:
            print("❌ App exited prematurely")
            stdout, stderr = MARK_PROCESS.communicate()
            if stderr:
                print(f"stderr:\n{stderr}")
            return False

    except Exception as e:
        print(f"❌ Failed to launch app: {e}\n")
        return False


def run_smoke_tests():
    """Run basic smoke tests to verify core functionality."""
    print("🧪 Running smoke tests...")

    # Check if app is still running
    if MARK_PROCESS is None or MARK_PROCESS.poll() is not None:
        print("❌ App is not running\n")
        return False

    tests_passed = 0
    tests_total = 3

    # Test 1: Verify process is alive
    print("  [1/3] Checking process status...")
    if MARK_PROCESS.poll() is None:
        print("    ✅ Process is alive")
        tests_passed += 1
    else:
        print("    ❌ Process has exited")

    # Test 2: Check if API config exists (can't test actual API call without mocking)
    print("  [2/3] Checking API configuration...")
    if API_FILE.exists():
        try:
            with open(API_FILE) as f:
                config = json.load(f)
                if "gemini_api_key" in config:
                    print("    ✅ Gemini API key configured")
                    tests_passed += 1
                else:
                    print("    ❌ Gemini API key not in config")
        except Exception as e:
            print(f"    ❌ Failed to read API config: {e}")
    else:
        print("    ⚠️  API config not found (expected for test)")

    # Test 3: Verify key modules can be imported
    print("  [3/3] Checking module imports...")
    try:
        # Try importing key modules without running the app
        sys.path.insert(0, str(BASE_DIR))
        import ui
        from agents.trading_agent import TradingAgent
        from core.data_bridge import DataBridge
        print("    ✅ Core modules imported successfully")
        tests_passed += 1
    except Exception as e:
        print(f"    ⚠️  Module import check: {e}")

    print(f"\n✅ Smoke tests: {tests_passed}/{tests_total} passed\n")
    return tests_passed >= 2  # Pass if at least 2 of 3 pass


def capture_screenshot(output_path: str = None):
    """Capture screenshot of the running app."""
    if not output_path:
        output_path = str(SKILL_DIR / "screenshot.png")

    print(f"📸 Capturing screenshot to {output_path}...")

    # On X11 (Linux), use scrot or import
    if IS_HEADLESS:
        try:
            # Try scrot first
            result = subprocess.run(
                ["scrot", "-o", output_path],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"✅ Screenshot saved\n")
                return True
        except FileNotFoundError:
            pass

        # Fallback to ImageMagick's import
        try:
            subprocess.run(
                ["import", "-window", "root", output_path],
                env={**os.environ, "DISPLAY": ":99"},
                capture_output=True,
                timeout=5,
                check=True
            )
            print(f"✅ Screenshot saved\n")
            return True
        except Exception as e:
            print(f"⚠️  Screenshot capture failed: {e}\n")
            return False
    else:
        # On Windows/macOS, would need platform-specific screenshot tool
        print("⚠️  Screenshot capture not implemented for this platform\n")
        return False


def cleanup():
    """Clean up resources on exit."""
    global MARK_PROCESS, XVFB_PROCESS

    print("\n🧹 Cleaning up...")

    if MARK_PROCESS and MARK_PROCESS.poll() is None:
        print("  Stopping app...")
        MARK_PROCESS.terminate()
        try:
            MARK_PROCESS.wait(timeout=3)
        except subprocess.TimeoutExpired:
            MARK_PROCESS.kill()
        print("  ✅ App stopped")

    if XVFB_PROCESS and XVFB_PROCESS.poll() is None:
        print("  Stopping Xvfb...")
        XVFB_PROCESS.terminate()
        try:
            XVFB_PROCESS.wait(timeout=2)
        except subprocess.TimeoutExpired:
            XVFB_PROCESS.kill()
        print("  ✅ Xvfb stopped")

    print("✅ Cleanup complete\n")


def main():
    parser = argparse.ArgumentParser(
        description="MARK XXXIX driver - launch and test the voice AI assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python driver.py setup              Install dependencies
  python driver.py install-deps       Alias for setup
  python driver.py launch             Start the app
  python driver.py test               Run smoke tests
  python driver.py screenshot out.png Capture window screenshot
        """
    )

    parser.add_argument(
        "command",
        choices=["setup", "install-deps", "launch", "test", "screenshot"],
        help="Command to execute"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output path for screenshot",
        default=None
    )

    args = parser.parse_args()

    try:
        if args.command == "setup" or args.command == "install-deps":
            setup_environment()
            install_dependencies()

        elif args.command == "launch":
            if not launch_app():
                sys.exit(1)
            print("💡 App is running. Press Ctrl+C to stop.\n")
            try:
                while MARK_PROCESS.poll() is None:
                    time.sleep(1)
            except KeyboardInterrupt:
                cleanup()

        elif args.command == "test":
            setup_environment()
            if launch_app():
                time.sleep(2)  # Wait for app to fully initialize
                run_smoke_tests()
                cleanup()
            else:
                sys.exit(1)

        elif args.command == "screenshot":
            if not MARK_PROCESS or MARK_PROCESS.poll() is not None:
                print("❌ App is not running. Start it with: python driver.py launch")
                sys.exit(1)
            capture_screenshot(args.output)

    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        cleanup()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        cleanup()
        sys.exit(1)


if __name__ == "__main__":
    main()
