# Security

AgentAck processes trace and policy files as untrusted input. It does not execute actions described by traces.

Please report vulnerabilities using GitHub Security Advisories for this repository rather than opening a public issue with exploit details.

The default parser bounds line size, event count, JSON nesting and policy approval lifetime. Network access and shell execution are not part of the checker.
