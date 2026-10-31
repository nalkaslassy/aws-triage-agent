# Architecture and boundaries

## Target system

Monitoring alerts and optional reports identify an application, environment, symptom, and UTC time window. A manifest maps that application to authorized resources and dependencies. Collectors retrieve bounded evidence from AWS and observability providers. An investigator proposes checks and competing explanations through a validated tool boundary. Reports cite evidence and distinguish facts, hypotheses, and missing visibility.

The model will not receive arbitrary cloud credentials or choose unrestricted SDK operations. Deterministic code will execute allowlisted operations against manifest resources. Logs and external reports are untrusted data and cannot grant permission or instruct the investigator to run commands.

## Implemented data flow

1. `collect` validates the manifest, window, and authenticated account.
2. Fixed AWS read operations create a versioned evidence bundle. Errors become unavailable evidence rather than a passing check.
3. `analyze` reads a bundle offline and applies a small set of deterministic checks.
4. A report includes evidence IDs, observations or hypotheses, next checks, suggested owners, and gaps.

The sandbox lab adds an operator-only signed HTTP request and deployment template outside the investigator. The template's fault selector and unfiltered environment are excluded from investigator input. The investigator can compare the current `ORDERS_TABLE` with the manifest's intended table and observe reserved concurrency at zero; it does not infer an exact historical cause from those snapshots.

Observation time and incident time are separate. Metrics/logs cover the requested window; network configuration and VPN sessions describe current state when collected. Historical configuration, historical user authorization, and the onset of a network incident cannot be inferred from current state.

## Network investigation target

Compare failed and working cohorts using the hostname, destination port, source network, time, and identity where authorized. Inspect VPN authentication separately from destination authorization. Check DNS, client routing, VPN routing, forward/return paths, and applicable security controls. Correlate the evidence with actual destination behavior.

AWS configuration analysis covers supported AWS paths, not an arbitrary home router or corporate firewall. Probes must run from representative locations; a probe inside AWS cannot establish reachability from a user's laptop. Third-party VPN/firewall or client data needs a separate authorized integration.

Network configuration collection exists in this milestone; automated network diagnosis does not. Route and authorization rules alone are insufficient without the actual destination, effective user/group membership, NAT behavior, and full path.

## Evidence contract

Bundles have `schema_version`, `application`, `start`, `end`, and `evidence`. Each evidence item has a unique ID, kind, resource, source operation, collection timestamp, status, and data. Statuses are `observed`, `partial`, `unavailable`, or `not_collected`. An observed API response confirms collection, not service health.

Evidence may include an optional HTTPS AWS console `source_url`. Kind-specific validation rejects invalid numeric and metadata fields. Reports include curated evidence references, not arbitrary imported data. API observations distinguish incident and baseline windows; configuration remains a current snapshot. Source pointers are service entry points rather than immutable event links.

Future model responses must be schema validated, may cite only collected evidence IDs, and must include supporting and contradicting evidence plus unresolved checks. Numerical confidence scores will not be used without calibration.
