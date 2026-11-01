# AgentForge product roadmap

## Product promise
A clear AI workspace where a small business can delegate repeatable work, inspect what happened, and approve consequential actions.

## Experience principles
1. Simple navigation with one obvious next action.
2. Every task has an owner, status, inputs, output and timestamp.
3. Show sources, uncertainty and provider errors.
4. Preview before send, publish, purchase or trade.
5. Explain permissions and costs before connecting services.
6. Responsive desktop-first dashboard with accessible contrast and keyboard support.

## Release sequence

### Foundation (current development branch)
- React + TypeScript workspace shell.
- FastAPI service and SQLite development persistence.
- Five agent task types with a configurable OpenAI-compatible provider.
- Task history and transparent provider-configuration errors.
- Omonux Trading paper-trade journal, with no broker execution.

### Private alpha
- Authentication, email verification and password reset.
- PostgreSQL migrations, tenant isolation and role-based access.
- Redis-backed queue and worker process for long-running jobs.
- File upload, safe parsing, document retrieval and citations.
- Customer support knowledge base and ticket connector.
- CRM import, lead qualification and outreach drafts.
- Content calendar, media-generation provider adapter and approval queue.
- Workflow builder with allowlisted connectors, scoped tokens and audit trail.
- Telegram notifications with opt-in and per-workspace settings.
- Usage metering, plan limits and cost visibility.

### Paid beta
- Payment provider integration and verified webhook handling.
- Subscription lifecycle, invoices, cancellation and refunds.
- Usage caps and abuse prevention.
- Public template gallery and referral attribution.
- Onboarding, help centre, product analytics and feedback loops.
- Automated unit, integration, accessibility and end-to-end tests.

### Omonux Trading expansion
- Licensed market-data providers and transparent quote timestamps.
- Watchlists, alerts and research notebooks.
- Historical backtesting with fees, slippage and survivorship-bias warnings.
- Paper portfolio, drawdown limits and risk reporting.
- Independent security and legal review before considering any broker connectivity.
- Live execution remains disabled until the owner explicitly approves a separate, compliant scope.

## Business validation
Interview target users before adding broad features. Measure activation, weekly active workspaces, successful tasks, repeat usage, support burden, gross margin, conversion and churn. Treat $500/week as a target to validate, not a promise.
