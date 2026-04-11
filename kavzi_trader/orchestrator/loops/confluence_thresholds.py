# Confluence hysteresis bands for Analyst verdicts.
#
# The router requires confluence >= CONFLUENCE_ENTER_MIN to escalate to
# the Trader tier. The reasoning loop treats scores in the borderline band
# (CONFLUENCE_REJECT_MAX+1 to CONFLUENCE_ENTER_MIN-1) as "wait for a new
# bar" rather than "aggressive rejection". Bar-close dedup in the router
# prevents flip-flop by memoizing the Analyst verdict within the same bar.
CONFLUENCE_REJECT_MAX = 4  # score <= 4 → escalating rejection cooldown
CONFLUENCE_ENTER_MIN = 6  # score >= 6 required (combined with setup_valid)
# Scores in the range [CONFLUENCE_REJECT_MAX + 1, CONFLUENCE_ENTER_MIN) form
# the borderline band: light cooldown, no counter escalation.
