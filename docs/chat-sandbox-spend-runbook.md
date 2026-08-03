# Chat sandbox spend circuit

This runbook covers the application circuit only. Modal Workspace and Environment budget changes must be made by the sole Workspace operator in Modal and recorded in the private operations audit trail. Never place a provider budget-write credential in the web application.

## Required provider policy

- Workspace: `$250` enforced monthly budget and native account-email notifications.
- Staging while production chat is disabled: dedicated `pwc-chat-staging` Environment, `$125` compute budget; application warning/trip `$75`/`$100`.
- Before production chat is approved: reduce staging to `$25` with `$15`/`$20` warning/trip, create the dedicated `pwc-chat-production` identity, and attest production `$175`/`$200`/`$225` beneath the shared Workspace cap.
- Environment-scoped service credentials must not list or terminate the other chat Environment's sandboxes.

## Incident response

1. Confirm the read-only Chat Compute dashboard state and event ID.
2. Verify the Modal Workspace and active Environment enforced budgets and native notification recipients.
3. Enumerate provider sandboxes tagged `service=pwc-chat`; compare them with live compute intervals.
4. Run the watchdog from the active immutable staging release or wait for its next 15-second pass. It terminates tracked workers and tagged orphans.
5. Confirm zero provider sandboxes and zero unresolved reservations/termination states. Keep the circuit tripped on uncertainty.
6. Compare the conservative ledger with Modal's month-to-date report. Provider spend is a floor and may only raise effective spend.
7. Investigate non-chat Workspace spend before changing any cap.

## Recovery

Normal recovery occurs only at a confirmed provider billing-cycle boundary with fresh reconciliation, matching policy attestation, zero live/orphan sandboxes, and no unresolved intervals or reservations. Operator-disable and accounting-integrity trips never auto-rearm. Exceptional early rearm uses `backend.scripts.manage_chat_sandbox_circuit` with a typed environment/cycle confirmation, an audited reason, and an explicit `accounting-correction` or `reviewed-higher-caps` basis; it is never available from the dashboard.

After any provider policy change, record the Workspace and Environment settings, native notification recipients, operator identity, timestamp, and matching deployment attestation in the private operations audit trail. The sole owner must maintain MFA, verified recovery and billing email, and the current Modal support recovery path outside source control.
