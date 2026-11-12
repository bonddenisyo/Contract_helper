"""What the copilot looks for, and which categories are too high-stakes to leave to the AI."""

CATEGORIES: dict[str, str] = {
    "auto_renewal": "Contract renews automatically unless cancelled in a narrow window",
    "termination": "One-sided or very short-notice termination rights",
    "early_termination_penalty": "Fees or forfeits for leaving early",
    "uncapped_liability": "Signer's liability is unlimited or very broad",
    "indemnification": "Signer must cover the other party's losses or legal costs",
    "non_compete": "Restricts where/for whom the signer can work or do business",
    "ip_assignment": "Signer gives away IP beyond the paid work",
    "payment_terms": "Late fees, long payment delays, or withheld payment",
    "deposit": "Deposit can be kept for vague or broad reasons",
    "rent_increase": "Rent or price can rise at the other party's discretion",
    "unilateral_changes": "Other party can change terms without signer's consent",
    "dispute_resolution": "Mandatory arbitration, jury waiver, or distant jurisdiction",
    "confidentiality": "Overly broad or never-ending confidentiality duties",
    "personal_guarantee": "Signer personally guarantees obligations",
    "entry_access": "Landlord/other party may enter or access without proper notice",
    "other": "Anything else a careful reader would want to know",
}

# Automation boundary: in these categories a high-risk flag always goes to a lawyer handoff,
# no matter how confident the model is. This is a product decision, not a model decision.
HIGH_STAKES = {
    "uncapped_liability",
    "indemnification",
    "personal_guarantee",
    "non_compete",
    "ip_assignment",
    "dispute_resolution",
}

ROLES = {
    "tenant": "a tenant signing a residential lease",
    "freelancer": "a freelancer/contractor signing a client services agreement",
    "small_business": "a small business owner signing a vendor or service contract",
}
