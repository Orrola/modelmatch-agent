"""Reproducible tie-breaking for overlapping task types, independent of scores."""

import re

POLICY_VERSION = "modelmatch-task-classification-v1"
POLICY = """Primary purpose takes precedence over industry. Explicit coding, tool-agent
or general-assistant purposes retain their corresponding task types. For overlapping
reasoning_analysis/specialized_domain/mixed_or_unknown choices, use this order:
explicit cross-domain scope or multiple recognized domains -> mixed_or_unknown;
one recognized domain -> specialized_domain (including analysis within that domain);
domain-independent analytical work -> reasoning_analysis; otherwise mixed_or_unknown.
An industry name without a concrete task still requires clarification. Unrecognized
domains fall back conservatively; domain classification does not establish U relevance.
Python resolves this overlap from the original request, never from generated paraphrases.
"""
DOMAINS = {
    "finance": r"\b(financ\w*|accounting|banking|investment\w*)\b",
    "legal": r"\b(legal|law|litigation|contract\w*)\b",
    "healthcare": r"\b(medic\w*|healthcare|clinical|patient\w*)\b",
    "engineering": r"\b(engineering|design risks|technical specifications)\b",
    "economics": r"\b(economic\w*|macroeconomic\w*)\b",
    "strategy_operations": r"\b(business strategy|supply chain|logistics|operations management)\b",
}


def resolve_task_type(raw, proposed):
    if proposed not in {"reasoning_analysis", "specialized_domain", "mixed_or_unknown"}:
        return proposed, "primary_purpose_preserved"
    # Structured operational numbers are not signals about task purpose.
    task = raw.split("\n\nStructured requirements (explicit user inputs; authoritative for these fields):", 1)[0]
    domains = [key for key, pattern in DOMAINS.items() if re.search(pattern, task, re.I)]
    if len(domains) > 1 or re.search(r"\b(cross-domain|across domains|unrelated tasks|mixed tasks)\b", task, re.I):
        return "mixed_or_unknown", "cross_domain_scope"
    if len(domains) == 1:
        return "specialized_domain", "single_recognized_domain"
    if re.search(r"\b(analy[sz]\w*|reason\w*|compar\w*|evaluate|deduce|infer\w*|logic\w*)\b", task, re.I):
        return "reasoning_analysis", "domain_independent_analysis"
    return "mixed_or_unknown", "insufficient_task_type_signals"
