### Designing and implementing End-to-end test for compliance

##### Purpose:
- Spins up full FastAPO app via ```httpx.AsyncClient```
- Mocks ```litellm.acompletion``` so no real API calls are made
- Sends requests with known PII
- Save requests with known PII and compare with redacred BEFORE the LLM call
- Verify the audit record was written to database