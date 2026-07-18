# Security Policy

`lfpolicy` is designed to make Lake Formation changes reviewable
before they run. The default planner avoids revokes and removals unless the user
passes an explicit allow flag.

## Reporting Vulnerabilities

Please report security issues privately through the GitHub repository owner.
Avoid opening public issues for vulnerabilities that could expose credentials,
permissions, or data lake access paths.

## Credential Handling

- The package does not store AWS credentials.
- Live AWS operations use the standard boto3 credential provider chain.
- Prefer PyPI Trusted Publishing for releases instead of long-lived PyPI tokens.
