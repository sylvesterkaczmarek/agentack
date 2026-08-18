# Standards mapping

AgentAck attaches informational references to findings so engineering teams can connect concrete test failures with broader security and oversight frameworks.

The mappings are not compliance claims.

## OWASP Agentic Top 10

The OWASP Top 10 for Agentic Applications 2026 identifies risks including:

- ASI02 Tool Misuse;
- ASI03 Identity and Privilege Abuse;
- ASI09 Human-Agent Trust Exploitation;
- ASI10 Rogue Agents.

AgentAck is most directly concerned with ASI09 because it tests whether human approval and intervention remain effective at the execution boundary. Denial route-around and unapproved tool execution also relate to ASI02. Replay and stale approval behavior can relate to ASI03 when approval acts as delegated authority. Continued execution after a stop event is relevant to ASI10.

Primary source:

- OWASP Top 10 for Agentic Applications for 2026, OWASP GenAI Security Project

## EU AI Act

Regulation (EU) 2024/1689 includes requirements for high-risk AI systems concerning logging, human oversight, robustness and cybersecurity.

Article 14 requires high-risk AI systems to be designed so that natural persons can effectively oversee them during use. Article 15 requires an appropriate level of accuracy, robustness and cybersecurity and consistent performance across the lifecycle. Article 12 addresses record-keeping and logging capabilities for high-risk AI systems.

AgentAck findings can contribute narrow technical evidence about approval and interruption behavior. They do not determine whether a system is high-risk, whether an obligation applies, whether oversight is legally adequate or whether a conformity assessment succeeds.

Primary source:

- Regulation (EU) 2024/1689, EUR-Lex

## Rule crosswalk

| Rule | Relevant OWASP areas | Relevant EU AI Act areas |
| --- | --- | --- |
| `ACK001` | ASI09, ASI02 | Article 14 |
| `ACK002` | ASI09, ASI02 | Article 14 |
| `ACK003` | ASI09 | Article 14 |
| `ACK004` | ASI09, ASI03 | Article 14 |
| `ACK005` | ASI09, ASI03 | Article 14 |
| `ACK006` | ASI09 | Article 14 |
| `ACK007` | ASI09, ASI02 | Article 14 |
| `ACK008` | ASI09, ASI10 | Articles 14 and 15 |
| `ACK009` | evidence quality | Articles 12 and 14 |
