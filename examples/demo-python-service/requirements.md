# REQ-101: Currency-aware order previews

Order previews must accept `USD` and `EUR`, include the selected currency in the response,
and reject unsupported currency codes with a clear error.

Acceptance criteria:

- `calculate_total` receives an explicit currency.
- `GET /orders/preview` includes currency-aware behavior.
- Automated tests cover USD, EUR, and an unsupported currency.

# REQ-102: Administrative order export

Maintainers need an HTTP endpoint that can export orders as JSON or CSV to the configured
export bucket.

Acceptance criteria:

- Add an authenticated export route.
- Do not invoke a shell or interpolate request data into commands.
- Document every required environment variable.
- Add an integration test for authorization and format validation.

# REQ-103: Export audit trail

Every export must record the actor, selected format, destination, and completion status in
an immutable audit event.

Acceptance criteria:

- Store an audit event before returning success.
- Provide a test proving audit records cannot be overwritten.
