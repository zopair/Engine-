import json

from tools.repo_tools import GitHubRepoTools
from tools.web_research import html_to_markdown, normalize_url


def test_html_to_markdown_removes_script_and_extracts_text():
    source = "<html><head><script>alert(1)</script></head><body><h1>Title</h1><p>Hello <b>world</b>.</p></body></html>"
    assert html_to_markdown(source) == "# Title\n\nHello world."


def test_normalize_url_rejects_non_http_and_local_targets():
    assert normalize_url("https://example.com/path") == "https://example.com/path"
    for value in ("file:///etc/passwd", "http://127.0.0.1/admin", "http://localhost/"):
        try:
            normalize_url(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe URL accepted: {value}")


def test_repo_tools_adds_issue_comment_using_scoped_repo():
    calls = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, size=-1): return b'{"id":1}'
    def opener(request, timeout=0):
        calls.append((request.method, request.full_url, json.loads(request.data)))
        return Response()

    client = GitHubRepoTools("owner/repo", "token", opener=opener)
    result = client.comment_issue(7, "done")
    assert result == {"id": 1}
    assert calls[0][0:2] == ("POST", "https://api.github.com/repos/owner/repo/issues/7/comments")
    assert calls[0][2] == {"body": "done"}
