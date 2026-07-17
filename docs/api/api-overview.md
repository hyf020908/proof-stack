# REST API overview

The versioned API is rooted at `http://localhost:8000/api/v1`. Interactive OpenAPI is served
at `/api/docs`, ReDoc at `/api/redoc`, and the schema at `/api/v1/openapi.json`.

## Authentication

Register with `POST /auth/register`, or use `POST /auth/demo` only when Demo mode is enabled.
`POST /auth/login` returns an access and refresh token pair; rotate access tokens through
`POST /auth/refresh`. Send the access token as `Authorization: Bearer <token>` and inspect the
current subject with `GET /auth/me`.

Demo login creates a maintainer with a random, unknown password. It is not a production
backdoor: production configuration disables Demo mode.

## Resources

| Area | Main endpoints |
| --- | --- |
| Organization | `GET/PATCH /organizations/current`, members list and owner updates |
| Projects | `GET/POST /projects`, `GET/PATCH/DELETE /projects/{id}` |
| Analysis creation | `POST /projects/{id}/analyses/demo`, `/upload`, `/github` |
| Analysis reads | analysis, progress, events, changed files, graph, requirements, tests, policy decisions |
| Findings | filtered analysis findings and reviewer status updates |
| Evidence | artifact manifest and ZIP download |
| Policies | list built-in policies and validate YAML |
| Audit | filtered, paginated organization audit events |
| System | health, readiness, version, safe public configuration, dashboard, metrics |

Upload analysis is `multipart/form-data`: `source` is a required ZIP, `diff` is an optional
UTF-8 `.diff` or `.patch`, and requirements, policy, runner, and structured validation
commands are optional fields. Poll `GET /analyses/{id}/progress`; events provide the ordered
stage history.

## Pagination and errors

List responses use `items`, `total`, `page`, `page_size`, and `pages`. Page size is bounded.
Filters are explicit query parameters and organization scope is always derived from the
access token.

Errors have one stable envelope:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "request_id": "8c29e37d-71fd-4ab0-8783-a7327cb06d50",
    "details": {}
  }
}
```

The request ID is also returned as `X-Request-ID`. Unexpected production errors never expose
internal tracebacks. Health and version are public; tenant data requires authentication.
