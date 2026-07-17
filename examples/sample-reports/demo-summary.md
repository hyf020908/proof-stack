# ProofStack sample acceptance summary

> This compact, sanitized example shows the report shape. It is not a runtime-generated
> Evidence Bundle and is not used by Demo mode.

**Verdict:** Fail  
**Risk:** 90 / 100

The proposed change adds useful currency and export behavior, but it cannot be accepted in
its current form. Critical evidence includes shell execution with request-derived input and
a token-shaped value. The export requirement also lacks authorization, audit, and test
evidence.

Recommended next actions:

1. Replace shell execution with a fixed argument array and strict format allowlist.
2. Revoke and remove the credential-like value, then load credentials at runtime.
3. Add the missing database migration and document `DEMO_EXPORT_BUCKET`.
4. Add API authorization, audit, unit, and integration tests.

Generate a real, checksummed report with `proofstack demo`.
