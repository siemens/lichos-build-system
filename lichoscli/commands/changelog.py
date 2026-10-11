# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

import logging
import re
from pathlib import Path
from typing import Optional

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.models.git import GitRepo, GitUrl
from lichoscli.core.services import SubmoduleService

logger = logging.getLogger(__name__)


class ChangelogCommand(Command):
    """Generate a changelog between the last tag and HEAD"""

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)
        self.repo = GitRepo(Path.cwd())
        self.submodule_service = di_container.obtain_ref(SubmoduleService)

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument(
            "tag",
            nargs="?",
            help="Tag to compare against (default: compares last two tags)",
        )
        parser.add_argument(
            "--issue-url",
            help="Base URL for issue tracking (e.g. https://jira.example.com/browse/)",
        )
        parser.add_argument(
            "-o",
            "--output",
            required=True,
            help="Output file path (default: print to console)",
        )

    def execute(self) -> int:
        if not self.repo.is_valid:
            self.output.error("Not a valid git repository.")
            return 1

        changelog = self.generate_changelog()
        
        output_path = Path(self.args.output)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(changelog, encoding='utf-8')
            self.output.success(f"Changelog written to {output_path}")
        except OSError as e:
            self.output.error(f"Failed to write changelog to {output_path}: {e}")
            return 1
        
        return 0


    def parse_commit(self, sha: str, repo_url: str, repo: Optional[GitRepo] = None) -> str:
        """Parse a commit and format it with links (matching old script format)."""
        if repo:
            subject, body = repo.get_commit_details(sha)
        else:
            subject = "Unknown commit"
            body = ""

        commit_url = f"{repo_url}/-/tree/{sha}"
        
        mr_match = re.search(r'See merge request [^!]+!(\d+)', body)
        
        if mr_match:
            # This is a merge commit with MR reference
            mr_number = mr_match.group(1)
            mr_url = f"{repo_url}/-/merge_requests/{mr_number}"
            
            # Extract the branch name from subject if it's a merge commit
            title_match = re.search(r"Merge branch '([^']+)'", subject)
            if title_match:
                branch_name = title_match.group(1)
                formatted = f"- Merge Request [!{mr_number}]({mr_url}) - {branch_name} ([{sha[:8]}]({commit_url}))"
            else:
                formatted = f"- Merge Request [!{mr_number}]({mr_url}) ([{sha[:8]}]({commit_url}))"
        else:
            # Regular commit
            formatted = f"- [{sha[:8]}]({commit_url}) {subject}"
        
        return formatted

    def link_issues(self, text: str, issue_url: Optional[str]) -> str:
        """Convert ticket references to links."""
        if not issue_url:
            return text

        pattern = r"\b([A-Z]{2,}-\d+)\b"

        def replace_match(match):
            ticket_id = match.group(1)
            base = issue_url.rstrip("/")
            return f"[{ticket_id}]({base}/{ticket_id})"

        return re.sub(pattern, replace_match, text)

    def generate_changelog(self) -> str:
        """Generate the complete changelog."""
        from_ref = self.args.tag if self.args.tag else self.repo.get_last_tag()
        to_ref = "HEAD"

        changelog = f"# Changelog\n\n"
        changelog += f"## Changes from `{from_ref}` to `{to_ref}`\n\n"

        main_repo_url = GitUrl.to_web_url(self.repo.get_remote_url())
        commits = self.repo.get_commit_log(from_ref, to_ref, no_merges=False)
        
        logger.info(f"Found {len(commits)} commits in main repository between {from_ref} and {to_ref}")

        if commits:
            changelog += "### Main Repository\n\n"
            for sha in commits:
                commit_formatted = self.parse_commit(sha, main_repo_url, self.repo)
                linked_commit = self.link_issues(commit_formatted, self.args.issue_url)
                changelog += f"{linked_commit}\n"
            changelog += "\n"

        submodule_changes = self.submodule_service.diff(self.repo, from_ref, to_ref)

        if submodule_changes:
            changelog += "### Submodule Changes\n\n"

            for change in submodule_changes:
                changelog += f"#### {change.path}\n\n"

                if change.kind != "updated":
                    submodule = change.new or change.old
                    url = GitUrl.to_web_url(submodule.url)
                    changelog += f"*{change.kind.capitalize()} at [{submodule.hexsha[:8]}]({url}/-/tree/{submodule.hexsha})*\n\n"
                    continue

                submodule_full_path = Path.cwd() / change.path
                if submodule_full_path.exists():
                    sub_repo = GitRepo(submodule_full_path)
                    submodule_commits = sub_repo.get_commit_log(
                        change.old.hexsha,
                        change.new.hexsha,
                        no_merges=False
                    )
                    
                    if submodule_commits:
                        submodule_url = GitUrl.to_web_url(sub_repo.get_remote_url())
                        for sha in submodule_commits:
                            commit_formatted = self.parse_commit(sha, submodule_url, sub_repo)
                            linked_commit = self.link_issues(commit_formatted, self.args.issue_url)
                            changelog += f"{linked_commit}\n"
                        changelog += "\n"
                    else:
                        changelog += "*No commits in range*\n\n"
                else:
                    changelog += "*Submodule not checked out*\n\n"
        else:
            changelog += "*No submodule changes*\n\n"

        return changelog
