"""
    init module for the constants
"""

from dotenv import load_dotenv

load_dotenv(".env")

__all__ = [name for name in globals() if name.isupper() and not name.startswith("_")]
if __name__ != "__main__":
    missing = [name for name in __all__ if name not in globals()]
    if missing:
        raise AssertionError(f"__all__ contains undefined names: {missing}")
