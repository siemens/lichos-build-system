import re
from dataclasses import dataclass
from typing import Optional, NamedTuple
from urllib.parse import urlparse


_URL_PATTERNS = [
    # Web URL with optional branch: https://host/group/pkg/-/tree/branch
    r"^https?://(?P<host>[^/]+)/(?P<path>[^?#]+?)(?:/-/tree/(?P<branch>[^?#]+?))?/?(?:[?#].*)?$",
    # SSH protocol: ssh://user@host/group/pkg.git
    r"^ssh://(?P<user>[^@]+)@(?P<host>[^/]+)/(?P<path>[^?#]+?)/?(?:[?#].*)?$",
    # SCP-style SSH: git@host:group/pkg.git
    r"^(?P<user>[^@]+)@(?P<host>[^:]+):(?P<path>.+)$",
]

class UrlComponents(NamedTuple):
    """Components parsed from a repository URL."""
    host: str
    group: str
    package: str
    branch: Optional[str] = None

@dataclass(frozen=True)
class GitUrl():
    host: str = ""
    group: str = ""
    package: str = ""
    branch: Optional[str] = None

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @classmethod
    def parse(cls, url: str) -> Optional["GitUrl"]:
        """Parse a git remote URL (SSH or HTTPS) into components.
        
        Supports multiple URL formats:
        - Web URLs with optional branch: https://host/group/pkg/-/tree/branch
        - SSH protocol: ssh://user@host/group/pkg.git
        - SCP-style SSH: git@host:group/pkg.git
        
        Returns ``None`` when the URL does not match any known pattern.
        """
        url = re.sub(r'\.git/?$', '', url)
        
        for pattern in _URL_PATTERNS:
            match = re.match(pattern, url)
            if match:
                host = match.group("host")
                branch = match.groupdict().get("branch", None)
                
                if "path" in match.groupdict():
                    path = match.group("path").rstrip("/").lstrip("/")
                    path_parts = path.split("/")
                    if len(path_parts) < 2:
                        continue  # Invalid path, need at least group/package
                    package = path_parts[-1]
                    group = "/".join(path_parts[:-1])
                
                return cls(
                    host=host,
                    group=group,
                    package=package,
                    branch=branch,
                )
        return None
    
    def parse_web_url(self, url: str) -> Optional[UrlComponents]:

        result = GitUrl.parse(url)
        if result:
            return UrlComponents(
                host=result.host,
                group=result.group,
                package=result.package,
                branch=result.branch,
            )
        return None

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    @property
    def web_url(self) -> str:
        """HTTPS web URL for this repository."""
        return f"https://{self.host}/{self.group}/{self.package}"

    @property
    def clone_url(self) -> str:
        """SSH clone URL for this repository.
        
        Returns the SSH-style git clone URL regardless of the original URL format.
        This is the preferred format for cloning repositories.
        """
        return f"git@{self.host}:{self.group}/{self.package}.git"

    @staticmethod
    def to_web_url(git_url: str) -> str:
        """Convert any git remote URL to a browsable web URL."""
        parsed = GitUrl.parse(git_url)
        if parsed:
            return parsed.web_url
        # Already an HTTP(S) URL – just strip a trailing .git
        if git_url.startswith("http"):
            return git_url.rstrip(".git")
        return git_url

    @staticmethod
    def parse_group_url(url: str) -> tuple:
        """Parse a group/collection URL into (host, group_path). """
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            return parsed.netloc, parsed.path.strip("/")
        return None, url.strip("/")

    # ------------------------------------------------------------------
    # Branch-name utilities
    # ------------------------------------------------------------------

    @staticmethod
    def sanitize_branch_name(branch_name: str) -> str:
        """Convert ``branch/main`` to ``branch/*``."""
        if branch_name.endswith("/main"):
            return branch_name[: branch_name.rfind("/")] + "/*"
        return branch_name

    @staticmethod
    def slugify_ref(branch: str) -> str:
        """Convert a branch name to a CI-safe ref slug (max 63 chars)."""
        return re.sub(r"[^a-z0-9]", "-", branch.lower()).strip("-")[:63]
