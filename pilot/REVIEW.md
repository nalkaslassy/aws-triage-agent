# Review instructions

Inspect each `packets.json` item without `PRIVATE-key.json`. The packet includes the symptom, evidence available at the end, raw proposals, and accepted assessment. The final evidence can include follow-ups collected after an earlier proposal. Each raw proposal has a corresponding `proposal_contexts` snapshot containing the actual curated evidence and journal supplied for that turn. Judge the proposal using that snapshot. Do not treat later evidence as support the model had earlier.

Each accepted candidate is one category-level claim, not a confirmed root cause. Mark it supported if its cited available evidence supports that scoped hypothesis. A timeout can support further connectivity investigation; it cannot identify a VPN outage or exact firewall. A current denied policy without an incident-linked request is a configuration observation, not an explanation of reported failures. A current allow does not refute a historical failed request. Candidate reference qualification is necessary but not sufficient for human acceptance.

Fill `scoring.csv`:

- `reviewer`: reviewer identifier.
- `accepted_supported`, `accepted_unsupported`: nonnegative category counts in the accepted assessment.
- `missed_useful_categories`: count useful supported categories omitted; consult the separate case rubric after evidence-first review. Explain disagreements.
- `raw_unsupported`: count unsupported candidate proposals across raw finish decisions, including rejected decisions. Do not count checks as diagnoses.
- `appropriate_uncertainty`: 1 or 0. Empty/rejected results are not automatically appropriate; consider what could reasonably be established.
- `useful_next_step`: 1 or 0. The suggestion should address a concrete uncertainty. The prewritten next-step vocabulary limits specificity.
- `exact_cause_overclaim`: 1 or 0. Flag an interpretation that names an exact cause beyond the available evidence; explain it in notes. The current fixed category interface may rarely express such a claim.
- `notes`: evidence IDs, missing visibility, counterevidence, disagreements, or an unscorable reason. Leave unavailable scores blank rather than inventing them.

Do not enter spreadsheet formulas in free-text cells. Keep review artifacts private and outside Git. Retain independent reviewer sheets and reconcile disagreements explicitly, preferably with a second reviewer. Arm blinding is partial because rejection patterns may reveal the treatment. Initial review can be done with the project owner; disclose reviewer involvement and development-case familiarity.

Unblind after scoring. Report per-case paired results, raw proposal versus accepted assessment differences, useful findings lost, and all unfinished runs. Do not present the automatic rubric pass rate as diagnosis accuracy. The current exporter supplies a blank sheet; it does not claim that independent review has happened.
