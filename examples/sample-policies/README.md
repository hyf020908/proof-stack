# Policy examples

`default.yml` balances blocking safety signals with advisory evidence thresholds.
`strict-security.yml` demonstrates a higher-assurance merge gate. `advisory.yml` is useful
while a team is learning what its normal signal level looks like.

Validate any file before applying it:

```bash
proofstack policy validate examples/sample-policies/default.yml
```
