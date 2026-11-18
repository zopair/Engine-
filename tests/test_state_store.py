import base64
import sqlite3

from memory.database import Database
from memory.state_store import EncryptedStateCodec, GitHubBranchStateStore


class FakeGitHubStateStore(GitHubBranchStateStore):
    def __init__(self, codec):
        self.repository = "owner/repo"
        self.token = "test-token"
        self.branch = "engine-state"
        self.path = "state/engine.sqlite.enc"
        self.codec = codec
        self.api_url = "https://api.github.test"
        self.opener = None
        self.ref = {"object": {"sha": "initial-commit"}}
        self.blobs = {}
        self.latest_blob = None
        self.counter = 0

    def _branch_ref(self, create=False):
        return self.ref

    def _tree(self, commit_sha):
        entries = []
        if self.latest_blob:
            entries.append({"path": self.path, "sha": self.latest_blob})
        return {"sha": "tree-current", "tree": entries}

    def _request(self, method, endpoint, payload=None, missing_ok=False):
        if method == "GET" and "/git/blobs/" in endpoint:
            raw = self.blobs[endpoint.rsplit("/", 1)[-1]]
            return {"content": base64.b64encode(raw).decode("ascii")}
        if method == "POST" and endpoint.endswith("/git/blobs"):
            self.counter += 1
            sha = f"blob-{self.counter}"
            self.blobs[sha] = base64.b64decode(payload["content"])
            return {"sha": sha}
        if method == "POST" and endpoint.endswith("/git/trees"):
            return {"sha": "tree-new"}
        if method == "POST" and endpoint.endswith("/git/commits"):
            return {"sha": "commit-new"}
        if method == "PATCH" and endpoint.endswith("/git/ref/heads/engine-state"):
            self.ref = {"object": {"sha": payload["sha"]}}
            return {"ok": True}
        raise AssertionError(f"Unexpected API request: {method} {endpoint}")


def test_encrypted_github_branch_snapshot_round_trip(tmp_path):
    database_path = tmp_path / "source.db"
    database = Database(str(database_path))
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO user_facts(user_id, fact, source) VALUES (?, ?, ?)",
            ("user-1", "prefers local CPU inference", "test"),
        )

    store = FakeGitHubStateStore(EncryptedStateCodec(key=b"s" * 32))
    commit = store.save_from(database_path)
    assert commit == "commit-new"

    uploaded = max(store.blobs)
    store.latest_blob = uploaded
    restored_path = tmp_path / "restored.db"
    assert store.load_into(restored_path) is True

    with sqlite3.connect(restored_path) as restored:
        fact = restored.execute("SELECT fact FROM user_facts").fetchone()
    assert fact == ("prefers local CPU inference",)
    assert store.blobs[uploaded].startswith(EncryptedStateCodec.MAGIC)
