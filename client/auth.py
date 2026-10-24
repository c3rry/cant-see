"""
Authentication handler for Kalshi API v2.
Implements RSA-SHA256 with PSS padding matching Kalshi's security specifications.
"""

import time
import base64
from pathlib import Path
from typing import Dict
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key


class KalshiAuth:
    """Manages RSA key loading and request signature generation."""

    def __init__(self, key_id: str, private_key_path: str):
        self.key_id = key_id
        self.private_key_path = Path(private_key_path)
        self._private_key = None
        self._load_key()

    def _load_key(self):
        if not self.private_key_path.exists():
            raise FileNotFoundError(f"Kalshi private key file not found: {self.private_key_path}")
        
        with open(self.private_key_path, "rb") as key_file:
            self._private_key = load_pem_private_key(key_file.read(), password=None)

    def sign_request(self, method: str, path: str) -> Dict[str, str]:
        """
        Signs an HTTP request for Kalshi API v2.
        Message format: <timestamp_ms><METHOD><path_without_query>
        Returns headers dictionary with key, timestamp, and signature.
        """
        timestamp = str(int(time.time() * 1000))
        
        # Path for signature should strip query parameters
        clean_path = path.split("?")[0]
        message_str = f"{timestamp}{method.upper()}{clean_path}"
        message_bytes = message_str.encode("utf-8")

        # Kalshi requires RSA-PSS with SHA256 and PSS.DIGEST_LENGTH salt
        signature = self._private_key.sign(
            message_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH
            ),
            hashes.SHA256()
        )
        
        signature_b64 = base64.b64encode(signature).decode("utf-8")

        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "KALSHI-ACCESS-SIGNATURE": signature_b64,
            "Content-Type": "application/json"
        }
