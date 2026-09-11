# Silent-failure modes (WDK accepts your request; the science is wrong)

Each of these was learned the hard way in pathfinder and is machine-checked
there (docs/knowledge/wdk/rules). The CLI guards the starred ones.

1. ★ Tree parent submitted directly under countOnlyLeaves → 0 rows, no error.
   Guard: encode_params expands parents to leaves.
2. ★ Guest tokens: uncredentialed requests mint a fresh guest per request —
   results belong to nobody and /users paths 401. Guard: whoami / user_id()
   refuse guests.
3. ★ Duplicate Authorization cookie pairs: Tomcat honors the first. Guard: the
   client sends exactly one.
4. ★ Retrying a committed create after a proxy 502 duplicates objects. Guard:
   creates are single-attempt.
5. ★ estimatedSize/count 0 vs absent vs -1: absent/-1 means "nobody measured",
   not "empty". Guard: shaping reports "unmeasured", never fabricates 0.
6. ★ input-step params given real values are rejected or mis-wired. Guard:
   always "".
7. Hidden params are still validated (isVisible is presentation-only) — they
   are auto-submitted with defaults; if a hidden default is invalid the WDK
   422 names it.
8. Multi-pick enumeration: one representative value ≠ the covered set. List
   every value you mean. A vocabulary + free-text pair covering the same
   concept is ORed by the search — pass "N/A" to the half you don't use (the
   sheet default usually does this).
9. initialDisplayValue is not a promise: a default may be stale; a 0 count
   with defaults means check the params, not the biology.
10. `isValid: true` at validation level NONE means "nobody checked", not
    "valid". Only the level the response names was checked.
11. Single-pick param + JSON array value = HTTP 500 (not 422). Send a scalar.
12. Number-ish params reject thousands separators ("10,000" → 422).
13. One-sided ranges are invalid; supply both bounds (defaults cover the
    other side if you only care about one).
14. A count of 0 after AND-ing many criteria usually means over-narrowing —
    prefer few broad criteria, verify each leaf's count > 0 before combining
    (use `count` per leaf; they're anonymous and parallelizable).
15. ★ Empty initialDisplayValue ('[]') on required multi-pick params: WDK uses
    "[]" as the unselected initial display value for params like `text_search_organism`
    and `organism`, but requires at least 1 selection. `encode_params` enforces
    this locally instead of sending an empty list that triggers HTTP 422.
