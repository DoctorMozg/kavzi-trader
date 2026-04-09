# Confluence hysteresis bands for Analyst verdicts.
#
# The old schema validator forced setup_valid=True whenever confluence >= 6,
# which meant a 1-point sampling swing at the cutoff (5↔6) could flip the
# entire pipeline. The router now requires confluence >= 6 to escalate to
# the Trader tier — matching the Analyst prompt's own rubric — and the
# reasoning loop treats scores in the borderline band (4-5) as "wait for a
# new bar" rather than "aggressive rejection". Bar-close dedup in the router
# prevents flip-flop by memoizing the Analyst verdict within the same bar.
CONFLUENCE_REJECT_MAX = 3  # score <= 3 → escalating rejection cooldown
CONFLUENCE_ENTER_MIN = 6  # score >= 6 required (combined with setup_valid)
# Scores in the range [CONFLUENCE_REJECT_MAX + 1, CONFLUENCE_ENTER_MIN) form
# the borderline band: light cooldown, no counter escalation.
