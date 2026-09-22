"""Print a fresh Fernet key for TOKEN_ENCRYPTION_KEY.

Usage:
    python -m scripts.generate_encryption_key

In PowerShell, capture it without it ever appearing on screen:
    $env:TOKEN_ENCRYPTION_KEY = (python -m scripts.generate_encryption_key)
"""
from cryptography.fernet import Fernet

if __name__ == "__main__":
    print(Fernet.generate_key().decode())
