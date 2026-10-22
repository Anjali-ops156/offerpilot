"""Installs the repo's git hooks (currently: pre-commit secret scan).

Run once after cloning: python scripts/install_hooks.py
"""
import shutil
import stat
import subprocess
from pathlib import Path


def main() -> None:
    repo_root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
        ).stdout.strip()
    )
    src = repo_root / "githooks" / "pre-commit"
    dest = repo_root / ".git" / "hooks" / "pre-commit"
    shutil.copy(src, dest)
    dest.chmod(dest.stat().st_mode | stat.S_IEXEC)
    print(f"Installed pre-commit hook -> {dest}")


if __name__ == "__main__":
    main()
