from urllib.parse import urlparse

from dispatcher import Context, Decision, Result


NAME = "curl_loopback"
PRIORITY = 10


FORBIDDEN_OPTIONS = {
    # Proxy / alternate routing
    "--proxy",
    "-x",
    "--preproxy",
    "--connect-to",
    "--resolve",

    # External config files can inject arbitrary curl options
    "--config",
    "-K",

    # Redirects could leave localhost
    "--location",
    "-L",
    "--location-trusted",

    # Proxy-related credentials / headers
    "--proxy-anyauth",
    "--proxy-user",
    "--proxy-header",
}


def evaluate(ctx: Context, config: dict) -> Result:
    argv = ctx.argv

    if not argv or argv[0] != "curl":
        return Result(Decision.ABSTAIN)

    allowed_hosts = {
        str(host).lower()
        for host in config.get(
            "allowed_hosts",
            ["localhost", "127.0.0.1", "::1"],
        )
    }

    forbidden_options = set(
        config.get(
            "forbidden_options",
            FORBIDDEN_OPTIONS,
        )
    )

    # Refuse commands using options that can redirect traffic
    # somewhere other than the URL shown on the command line.
    for arg in argv[1:]:
        if arg in forbidden_options:
            return Result(
                Decision.ABSTAIN,
                f"unsafe curl option: {arg}",
            )

    urls: list[str] = []

    for arg in argv[1:]:
        if arg.startswith(("http://", "https://")):
            urls.append(arg)

    if not urls:
        return Result(
            Decision.ABSTAIN,
            "no explicit HTTP(S) URL found",
        )

    for url in urls:
        try:
            parsed = urlparse(url)
        except ValueError:
            return Result(
                Decision.ABSTAIN,
                f"invalid URL: {url}",
            )

        hostname = parsed.hostname

        if hostname is None:
            return Result(
                Decision.ABSTAIN,
                f"URL has no hostname: {url}",
            )

        if hostname.lower() not in allowed_hosts:
            return Result(
                Decision.ABSTAIN,
                f"non-loopback host: {hostname}",
            )

    return Result(
        Decision.ALLOW,
        "all curl targets are loopback",
    )