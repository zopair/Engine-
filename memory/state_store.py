from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sqlite3
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class StateStoreError(RuntimeError):
    pass


class EncryptedStateCodec:
    """Encrypt SQLite snapshots with AES-256-CBC plus encrypt-then-MAC authentication."""

    MAGIC = b"ENGINESTATE\x01"

    def __init__(self, key: bytes | str | None = None) -> None:
        supplied = key if key is not None else os.getenv("ENGINE_STATE_ENCRYPTION_KEY")
        if supplied is None:
            raise StateStoreError("ENGINE_STATE_ENCRYPTION_KEY is required; refusing plaintext persistence")
        self.secret = supplied.encode("utf-8") if isinstance(supplied, str) else bytes(supplied)
        if len(self.secret) < 32:
            raise StateStoreError("state encryption key must contain at least 32 bytes")

    def _derive(self, salt: bytes) -> bytes:
        return hashlib.scrypt(self.secret, salt=salt, n=2**14, r=8, p=1, dklen=64)

    @staticmethod
    def _openssl(data: bytes, key: bytes, iv: bytes, decrypt: bool = False) -> bytes:
        command = ["openssl", "enc", "-aes-256-cbc", "-nosalt", "-K", key.hex(), "-iv", iv.hex()]
        if decrypt:
            command.insert(2, "-d")
        try:
            result = subprocess.run(
                command, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=True, timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise StateStoreError("OpenSSL AES-256-CBC operation failed") from exc
        return result.stdout

    def encrypt(self, plaintext: bytes) -> bytes:
        salt, iv = os.urandom(16), os.urandom(16)
        derived = self._derive(salt)
        ciphertext = self._openssl(plaintext, derived[:32], iv)
        payload = self.MAGIC + salt + iv + ciphertext
        tag = hmac.new(derived[32:], payload, hashlib.sha256).digest()
        return payload + tag

    def decrypt(self, encrypted: bytes) -> bytes:
        header = len(self.MAGIC) + 16 + 16
        if len(encrypted) < header + 16 + 32 or not encrypted.startswith(self.MAGIC):
            raise StateStoreError("invalid encrypted state format")
        salt = encrypted[len(self.MAGIC):len(self.MAGIC) + 16]
        iv_start = len(self.MAGIC) + 16
        iv = encrypted[iv_start:iv_start + 16]
        payload, tag = encrypted[:-32], encrypted[-32:]
        derived = self._derive(salt)
        expected = hmac.new(derived[32:], payload, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise StateStoreError("state authentication failed")
        return self._openssl(encrypted[header:-32], derived[:32], iv, decrypt=True)


class GitHubBranchStateStore:
    """Persist an encrypted SQLite snapshot in a dedicated GitHub data branch."""

    def __init__(
        self,
        repository: str | None = None,
        token: str | None = None,
        branch: str = "engine-state",
        path: str = "state/engine.sqlite.enc",
        codec: EncryptedStateCodec | None = None,
        api_url: str | None = None,
        opener=None,
    ) -> None:
        self.repository = repository or os.getenv("GITHUB_REPOSITORY", "")
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        if not self.repository or not self.token:
            raise StateStoreError("GITHUB_REPOSITORY and GITHUB_TOKEN are required")
        self.branch, self.path = branch, path
        self.codec = codec or EncryptedStateCodec()
        self.api_url = (api_url or os.getenv("GITHUB_API_URL", "https://api.github.com")).rstrip("/")
        self.opener = opener or urllib.request.urlopen

    def _request(self, method: str, endpoint: str, payload=None, missing_ok: bool = False):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.api_url + endpoint,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "ENGINE-state-store",
            },
        )
        try:
            with self.opener(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if missing_ok and exc.code == 404:
                return None
            raise StateStoreError(f"GitHub state API request failed with HTTP {exc.code}") from exc
        except (OSError, ValueError) as exc:
            raise StateStoreError("GitHub state API request failed") from exc

    def _ref_endpoint(self) -> str:
        return f"/repos/{self.repository}/git/ref/heads/{urllib.parse.quote(self.branch, safe='')}"

    def _branch_ref(self, create: bool = False):
        ref = self._request("GET", self._ref_endpoint(), missing_ok=True)
        if ref or not create:
            return ref
        main = self._request("GET", f"/repos/{self.repository}/git/ref/heads/main")
        self._request("POST", f"/repos/{self.repository}/git/refs", {
            "ref": f"refs/heads/{self.branch}", "sha": main["object"]["sha"]
        })
        return self._request("GET", self._ref_endpoint())

    def _tree(self, commit_sha: str):
        commit = self._request("GET", f"/repos/{self.repository}/git/commits/{commit_sha}")
        return self._request(
            "GET", f"/repos/{self.repository}/git/trees/{commit['tree']['sha']}?recursive=1"
        )

    def load_into(self, database_path: str | Path) -> bool:
        ref = self._branch_ref()
        if ref is None:
            return False
        tree = self._tree(ref["object"]["sha"])
        entry = next((item for item in tree.get("tree", []) if item.get("path") == self.path), None)
        if entry is None:
            return False
        blob = self._request("GET", f"/repos/{self.repository}/git/blobs/{entry['sha']}")
        encrypted = base64.b64decode(blob["content"])
        plaintext = self.codec.decrypt(encrypted)
        target = Path(database_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".restore")
        temporary.write_bytes(plaintext)
        temporary.replace(target)
        return True

    def save_from(self, database_path: str | Path) -> str:
        source = Path(database_path)
        if not source.is_file():
            raise StateStoreError(f"SQLite database does not exist: {source}")
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "snapshot.sqlite"
            with sqlite3.connect(str(source)) as original, sqlite3.connect(str(snapshot)) as backup:
                original.backup(backup)
            encrypted = self.codec.encrypt(snapshot.read_bytes())

        ref = self._branch_ref(create=True)
        head_sha = ref["object"]["sha"]
        tree = self._tree(head_sha)
        blob = self._request("POST", f"/repos/{self.repository}/git/blobs", {
            "content": base64.b64encode(encrypted).decode("ascii"), "encoding": "base64"
        })
        new_tree = self._request("POST", f"/repos/{self.repository}/git/trees", {
            "base_tree": tree["sha"],
            "tree": [{"path": self.path, "mode": "100644", "type": "blob", "sha": blob["sha"]}],
        })
        commit = self._request("POST", f"/repos/{self.repository}/git/commits", {
            "message": "chore(state): persist encrypted ENGINE session database",
            "tree": new_tree["sha"],
            "parents": [head_sha],
        })
        self._request("PATCH", self._ref_endpoint(), {"sha": commit["sha"], "force": False})
        return commit["sha"]
