# Security policy

## Supported versions

| Version | Supported |
|---|---|
| 1.2.x on PyPI | Yes |
| 1.1.x | Security fixes only if still installed in the wild |
| earlier | No |

## Report a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/insightitsGit/PrismThinker/security/advisories/new)
on this repository. Do not open a public issue or Discussion with exploit
details.

Include the package version, a minimal reproduction, and impact. We will
acknowledge the report and say whether a fix or advisory will ship.

## Scope

PrismThinker is a decision gate. Hosts remain responsible for authentication,
argument validation, execution binding, and replay protection. Reports that
only apply to a host that ignores `REFUSE` / `ESCALATE` / `GATHER` are out of
scope for this package.
