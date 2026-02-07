# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

We take the security of confluence-bidir-sync seriously. If you discover a security vulnerability, please follow these steps:

### 1. **Do Not Open a Public Issue**

Please **do not** create a public GitHub issue for security vulnerabilities, as this could put users at risk before a fix is available.

### 2. **Report Privately**

Send your vulnerability report to: **217068802+PatD42@users.noreply.github.com**

Include in your report:
- Description of the vulnerability
- Steps to reproduce the issue
- Potential impact
- Suggested fix (if you have one)

### 3. **Response Timeline**

- **Initial Response**: Within 48 hours of receiving your report
- **Assessment**: Within 1 week we'll provide an assessment and timeline for a fix
- **Fix & Disclosure**: We aim to release a patch within 30 days for critical vulnerabilities

### 4. **Coordinated Disclosure**

We follow a coordinated disclosure process:
1. We'll work with you to understand and validate the vulnerability
2. We'll develop and test a fix
3. We'll release the fix and publish a security advisory
4. We'll credit you in the advisory (if you wish)

## Security Features

This project includes several built-in security measures:

- **Input Validation**: Page IDs, URLs, and file paths are validated
- **Path Traversal Protection**: File operations are restricted to project directories
- **Credential Sanitization**: Sensitive data is removed from error messages and logs
- **Rate Limiting**: Exponential backoff prevents API abuse
- **Parser Security**: Uses safe HTML parser (html.parser) for user content
- **Command Injection Prevention**: Git commands use numeric validation
- **XXE Prevention**: XML parsing configured to prevent entity expansion attacks

## Security Best Practices

When using this tool:

1. **Protect Your Credentials**
   - Store API tokens in `.env` files (never commit to git)
   - Use environment variables in CI/CD environments
   - Rotate tokens regularly

2. **Keep Dependencies Updated**
   - Run `pip-audit` regularly to check for vulnerable dependencies
   - Update to the latest version of confluence-bidir-sync

3. **Validate Input**
   - Review content before syncing to Confluence
   - Use `--dry-run` to preview changes
   - Be cautious with `--force-push` and `--force-pull` commands

4. **Monitor Logs**
   - Review sync logs for unusual activity
   - Use `--logdir` to maintain audit trails

## Known Limitations

- **Confluence Data Center**: Only Confluence Cloud has been tested
- **Inline Comments**: Comments may be lost during page updates (Confluence API limitation)
- **Attachments**: Binary attachments are not synced (URLs are preserved)

## Acknowledgments

We appreciate security researchers who help keep our users safe. If you report a valid security vulnerability, we'll gladly credit you in our security advisories (unless you prefer to remain anonymous).
