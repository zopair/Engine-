from __future__ import annotations

import argparse
import os
from pathlib import Path

from tools.repo_tools import GitHubRepoTools


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--issue', type=int, required=True)
    parser.add_argument('--result-file', required=True)
    args = parser.parse_args()
    result = Path(args.result_file).read_text(encoding='utf-8')
    client = GitHubRepoTools(os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_TOKEN'])
    client.comment_issue(args.issue, '## ENGINE task result\n\n' + result[:50000])
    client.close_issue(args.issue)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
