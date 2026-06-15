import re

# Victorian Driver Licence — 9-digit numeric OR alpha-numeric (letter at start or end)
VIC_DL = re.compile(r"\b(?:\d{9}|[A-Z]\d{8}|\d{8}[A-Z])\b")

# Victorian number plates — standard (1AB 2CD) and custom (2–6 alphanumeric)
VIC_PLATE = re.compile(r"\b[A-Z0-9]{2,3}[- ]?[A-Z0-9]{2,3}\b")

# Australian phone numbers — 04xx xxx xxx mobile or (0x) xxxx xxxx landline
AU_PHONE = re.compile(
    r"(?<!\d)(?:\+61\s?|0)4\d{2}\s?\d{3}\s?\d{3}(?!\d)"   # mobile (+ country code or 0)
    r"|(?<!\d)\(0[2-9]\)\s?\d{4}\s?\d{4}(?!\d)"            # landline with area code
    r"|\b0[2-9]\d{8}\b"                                     # landline no spaces
)

# Email addresses
EMAIL = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")

# Australian Medicare card — 10 digits starting with 2–6
MEDICARE = re.compile(r"\b[2-6]\d{9}\b")

# Street addresses — number + street name + type
ADDRESS = re.compile(
    r"\b\d{1,4}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*"
    r"\s+(?:Street|St|Road|Rd|Avenue|Ave|Drive|Dr|Court|Ct|Lane|Ln|"
    r"Boulevard|Blvd|Crescent|Cres|Place|Pl|Way|Close|Cl)\b",
    re.IGNORECASE,
)

# Ordered list: most specific first to avoid partial matches
PATTERNS: list[tuple[re.Pattern, str]] = [
    (VIC_DL,      "[REDACTED_VIC_DL]"),
    (MEDICARE,    "[REDACTED_MEDICARE]"),
    (AU_PHONE,    "[REDACTED_PHONE]"),
    (EMAIL,       "[REDACTED_EMAIL]"),
    (ADDRESS,     "[REDACTED_ADDRESS]"),
    # VIC_PLATE last — broad pattern, only catches what regex above missed
    (VIC_PLATE,   "[REDACTED_PLATE]"),
]
