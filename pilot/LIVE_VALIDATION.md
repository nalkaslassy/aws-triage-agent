# Small live collection validation

Pending: an authenticated sandbox AWS environment. The recorded pilot runner cannot deploy infrastructure, collect live application telemetry, or establish live AWS correctness. Use the existing [sandbox deployment and cleanup guide](../sandbox/README.md).

1. Confirm the sandbox account/profile and region locally. Install the project AWS extra, AWS CLI, and SAM CLI as described in the sandbox guide. Review the template and intended resources before deployment.
2. Deploy `FaultMode=normal`. Generate the collection manifest from stack outputs. Send one signed synthetic request. Record UTC time, HTTP status, request IDs, and stack/function/table names privately. Normal should return 201.
3. Wait for telemetry, then collect a complete minute-aligned incident window spanning the request. Analyze it. Missing datapoints remain unknown; no supported application failure should be invented.
4. Update only this disposable stack to `FaultMode=permission_denied`. Wait for update completion, send one request, and collect a separate window while the failure remains active. Keep the operator's fault-selection record separate from investigator input.
5. Verify the recorded failure includes an in-window request ID, PutItem action, and intended table. Compare it with the actual injected permission change. A read failure by the collector is a visibility gap, not a healthy result or proof of the application's failure.
6. Restore normal, verify one successful request, and delete the sandbox using the documented cleanup steps. Check retained SAM artifacts/logs and the account's resources/billing. Do not leave a failing sandbox running between sessions.
7. Record actual commands, sanitized observations, mismatches, telemetry delays, costs when available, and cleanup verification. Do not label this complete until those checks actually occurred.

No production resources or real customer data are needed. For later research use, preserve provenance and sanitize identifiers consistently. Do not replace synthetic packets with live records without creating a new version/hash and rechecking ground truth. Live validation of two scenarios validates that collection path only, not general incident diagnosis or VPN/network coverage.
