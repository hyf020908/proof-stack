# Unified diff fixtures

- `complex-change.patch` covers modification, rename metadata, addition, deletion, hunks,
  and a binary-file marker.
- `../demo-python-service/change.diff` is the complete risky FastAPI demonstration change.

Analyze the complex fixture against a matching source tree with:

```bash
proofstack analyze diff examples/sample-diffs/complex-change.patch --source ./repository
```
