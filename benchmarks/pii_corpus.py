"""
Labelled corpus for PII detection accuracy benchmarking.

Each CorpusEntry targets exactly one entity_tag — the string that appears in
RedactionResult.redacted_types when the entity is detected.  Tags match the
constants defined in patterns.py and redactor.py verbatim.

is_positive=True  → text MUST trigger detection of entity_tag (True Positive)
is_positive=False → text MUST NOT trigger detection of entity_tag (True Negative)

Negative entries deliberately include adversarial cases that probe the false-positive
rate of each pattern.  Some are marked as known gaps in the comments; the benchmark
runner counts and surfaces them honestly.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CorpusEntry:
    text: str
    entity_tag: str
    is_positive: bool
    label: str


CORPUS: list[CorpusEntry] = [

    # ── VIC_DL ─────────────────────────────────────────────────────────────────
    # Source: patterns.py  VIC_DL = re.compile(r"\b(?:\d{9}|[A-Z]\d{8}|\d{8}[A-Z])\b")
    # Three forms: 9-digit numeric, alpha-prefix (A########), alpha-suffix (########A)

    CorpusEntry("My licence number is 123456789.", "REDACTED_VIC_DL", True, "VIC_DL/TP/9-digit-basic"),
    CorpusEntry("Driver licence: 987654321", "REDACTED_VIC_DL", True, "VIC_DL/TP/9-digit-colon"),
    CorpusEntry("Please check A12345678 is still active.", "REDACTED_VIC_DL", True, "VIC_DL/TP/alpha-prefix"),
    CorpusEntry("Licence 12345678Z has expired.", "REDACTED_VIC_DL", True, "VIC_DL/TP/alpha-suffix"),
    CorpusEntry("Drivers A: 111222333 and B: 444555666", "REDACTED_VIC_DL", True, "VIC_DL/TP/multiple-in-sentence"),
    CorpusEntry("Applicant 000000001 submitted the form.", "REDACTED_VIC_DL", True, "VIC_DL/TP/leading-zeros"),
    # True negatives — must NOT match
    CorpusEntry("Reference ID: 12345678", "REDACTED_VIC_DL", False, "VIC_DL/TN/8-digit-ref"),
    CorpusEntry("Invoice number: 1234567890", "REDACTED_VIC_DL", False, "VIC_DL/TN/10-digit-invoice"),
    CorpusEntry("Postcode is 3000", "REDACTED_VIC_DL", False, "VIC_DL/TN/postcode"),
    CorpusEntry("ABN: 51824753556", "REDACTED_VIC_DL", False, "VIC_DL/TN/11-digit-abn"),
    # KNOWN GAP: \b fires between the hyphen and the first digit, so 9 digits match.
    # Fix would be a negative lookbehind (?<!-) but that changes the regex scope.
    CorpusEntry("REF-123456789 is the tracking code.", "REDACTED_VIC_DL", False, "VIC_DL/TN/hyphen-prefix-known-fp"),
    CorpusEntry("What are the road rules for merging lanes?", "REDACTED_VIC_DL", False, "VIC_DL/TN/no-numbers"),
    CorpusEntry("Speed limit is 100 km/h on freeways.", "REDACTED_VIC_DL", False, "VIC_DL/TN/short-number"),
    CorpusEntry("Section 42 of the Road Safety Act applies.", "REDACTED_VIC_DL", False, "VIC_DL/TN/section-ref"),

    # ── MEDICARE ────────────────────────────────────────────────────────────────
    # Source: patterns.py  MEDICARE = re.compile(r"\b[2-6]\d{9}\b")
    # 10 digits total; leading digit must be 2–6 (rules out phones starting 0, refs starting 1 or 7+)

    CorpusEntry("Medicare card: 2123456701", "REDACTED_MEDICARE", True, "MEDICARE/TP/starts-2"),
    CorpusEntry("Medicare number: 3987654321", "REDACTED_MEDICARE", True, "MEDICARE/TP/starts-3"),
    CorpusEntry("Card number 4111111111 on file.", "REDACTED_MEDICARE", True, "MEDICARE/TP/starts-4"),
    CorpusEntry("Patient ID: 5000000001", "REDACTED_MEDICARE", True, "MEDICARE/TP/starts-5"),
    CorpusEntry("Health card: 6999999999", "REDACTED_MEDICARE", True, "MEDICARE/TP/starts-6"),
    # True negatives
    CorpusEntry("Reference code: 1123456789", "REDACTED_MEDICARE", False, "MEDICARE/TN/starts-1"),
    CorpusEntry("Account number: 7123456789", "REDACTED_MEDICARE", False, "MEDICARE/TN/starts-7"),
    CorpusEntry("Mobile: 0412345678", "REDACTED_MEDICARE", False, "MEDICARE/TN/phone-starts-0"),
    CorpusEntry("9-digit ref: 212345678", "REDACTED_MEDICARE", False, "MEDICARE/TN/9-digits-too-short"),
    CorpusEntry("Long code: 21234567012", "REDACTED_MEDICARE", False, "MEDICARE/TN/11-digits-too-long"),
    CorpusEntry("Please check your road registration status.", "REDACTED_MEDICARE", False, "MEDICARE/TN/no-numbers"),

    # ── AU_PHONE ────────────────────────────────────────────────────────────────
    # Source: patterns.py  Three sub-patterns:
    #   mobile  : (?<!\d)(?:\+61\s?|0)4\d{2}\s?\d{3}\s?\d{3}(?!\d)
    #   landline: (?<!\d)\(0[2-9]\)\s?\d{4}\s?\d{4}(?!\d)
    #   landline: \b0[2-9]\d{8}\b

    CorpusEntry("Call me on 0412 345 678.", "REDACTED_PHONE", True, "PHONE/TP/mobile-spaces"),
    CorpusEntry("Mobile: 0487654321", "REDACTED_PHONE", True, "PHONE/TP/mobile-no-spaces"),
    CorpusEntry("International: +61412345678", "REDACTED_PHONE", True, "PHONE/TP/mobile-country-code-nospace"),
    CorpusEntry("Call +61 412 345 678 for support.", "REDACTED_PHONE", True, "PHONE/TP/mobile-country-code-spaces"),
    CorpusEntry("Office: (03) 9123 4567", "REDACTED_PHONE", True, "PHONE/TP/landline-area-03"),
    CorpusEntry("Sydney office: (02) 8765 4321", "REDACTED_PHONE", True, "PHONE/TP/landline-area-02"),
    CorpusEntry("Fax: 0395551234", "REDACTED_PHONE", True, "PHONE/TP/landline-no-spaces"),
    CorpusEntry("Reach us at 0499 000 111 anytime.", "REDACTED_PHONE", True, "PHONE/TP/mobile-0499"),
    # True negatives
    CorpusEntry("UK contact: +44 7700 123456", "REDACTED_PHONE", False, "PHONE/TN/uk-number"),
    CorpusEntry("Call 1300 655 506 for support.", "REDACTED_PHONE", False, "PHONE/TN/au-1300-service"),
    CorpusEntry("Emergency services: 000", "REDACTED_PHONE", False, "PHONE/TN/triple-zero"),
    CorpusEntry("Interpreter line: 13 14 50", "REDACTED_PHONE", False, "PHONE/TN/short-service-number"),
    CorpusEntry("Incomplete: 0412345 not a full number.", "REDACTED_PHONE", False, "PHONE/TN/7-digit-too-short"),
    CorpusEntry("US toll-free: +1 800 555 0100", "REDACTED_PHONE", False, "PHONE/TN/us-number"),

    # ── EMAIL ───────────────────────────────────────────────────────────────────
    # Source: patterns.py  EMAIL = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")

    CorpusEntry("Contact john.smith@vicroads.vic.gov.au for details.", "REDACTED_EMAIL", True, "EMAIL/TP/gov-au"),
    CorpusEntry("Send the form to user+tag@example.com.", "REDACTED_EMAIL", True, "EMAIL/TP/plus-tag"),
    CorpusEntry("Email: test@test.org", "REDACTED_EMAIL", True, "EMAIL/TP/org-tld"),
    CorpusEntry("admin@company.net.au is the shared inbox.", "REDACTED_EMAIL", True, "EMAIL/TP/net-au"),
    CorpusEntry("firstname.lastname@domain.co is valid.", "REDACTED_EMAIL", True, "EMAIL/TP/two-char-tld"),
    # True negatives
    CorpusEntry("Visit vicroads.vic.gov.au for more information.", "REDACTED_EMAIL", False, "EMAIL/TN/url-no-at"),
    CorpusEntry("The at-sign (@) is used in handles.", "REDACTED_EMAIL", False, "EMAIL/TN/at-symbol-prose"),
    CorpusEntry("Incomplete address: user@", "REDACTED_EMAIL", False, "EMAIL/TN/no-domain-after-at"),
    CorpusEntry("This is not.an.email address at all.", "REDACTED_EMAIL", False, "EMAIL/TN/no-at-sign"),
    CorpusEntry("Road rules apply to all drivers here.", "REDACTED_EMAIL", False, "EMAIL/TN/clean-text"),

    # ── ADDRESS ─────────────────────────────────────────────────────────────────
    # Source: patterns.py  ADDRESS = re.compile(r"\b\d{1,4}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*"
    #                                            r"\s+(?:Street|St|Road|Rd|...|Close|Cl)\b", IGNORECASE)
    # Pattern: number + title-case words + recognised street type

    CorpusEntry("I live at 42 Collins Street Melbourne.", "REDACTED_ADDRESS", True, "ADDRESS/TP/collins-street"),
    CorpusEntry("Office at 10 Smith Road.", "REDACTED_ADDRESS", True, "ADDRESS/TP/smith-road"),
    CorpusEntry("Moved to 100 Bourke Avenue last year.", "REDACTED_ADDRESS", True, "ADDRESS/TP/bourke-avenue"),
    CorpusEntry("Drop off at 5 Park Court please.", "REDACTED_ADDRESS", True, "ADDRESS/TP/park-court"),
    CorpusEntry("Located at 1 Flinders Lane in the city.", "REDACTED_ADDRESS", True, "ADDRESS/TP/flinders-lane"),
    # True negatives — street-type words without a leading house number
    CorpusEntry("Road Safety Institute publishes reports.", "REDACTED_ADDRESS", False, "ADDRESS/TN/org-with-road-word"),
    CorpusEntry("Lane closure ahead due to roadworks.", "REDACTED_ADDRESS", False, "ADDRESS/TN/lane-word-no-number"),
    CorpusEntry("PO Box 1234 Melbourne", "REDACTED_ADDRESS", False, "ADDRESS/TN/po-box"),
    CorpusEntry("Drive carefully on wet road surfaces.", "REDACTED_ADDRESS", False, "ADDRESS/TN/drive-word-no-number"),
    CorpusEntry("Speed limit applies along the boulevard.", "REDACTED_ADDRESS", False, "ADDRESS/TN/boulevard-word-no-number"),

    # ── VIC_PLATE ───────────────────────────────────────────────────────────────
    # Source: patterns.py  VIC_PLATE = re.compile(r"\b[A-Z0-9]{2,3}[- ]?[A-Z0-9]{2,3}\b")
    # NOTE: No IGNORECASE — only uppercase letters and digits match.
    # The pattern is intentionally broad to catch both standard and custom formats.
    # Adversarial negatives below probe known FPs against common uppercase abbreviations.

    CorpusEntry("Plate 1AB 2CD was sighted at the scene.", "REDACTED_PLATE", True, "PLATE/TP/standard-1ab-2cd"),
    CorpusEntry("Custom plate ABC123 belongs to the fleet.", "REDACTED_PLATE", True, "PLATE/TP/custom-abc123"),
    CorpusEntry("Vehicle ZZZ999 was flagged by the camera.", "REDACTED_PLATE", True, "PLATE/TP/custom-zzz999"),
    CorpusEntry("Registration VIC007 is currently active.", "REDACTED_PLATE", True, "PLATE/TP/vic007"),
    # True negatives — lowercase text cannot match [A-Z0-9]{2,3}
    CorpusEntry("the road rules apply to every driver here", "REDACTED_PLATE", False, "PLATE/TN/lowercase-safe"),
    CorpusEntry("registration is currently active and valid", "REDACTED_PLATE", False, "PLATE/TN/lowercase-valid"),
    # KNOWN GAP: [A-Z0-9]{2,3}[- ]?[A-Z0-9]{2,3} matches common uppercase word pairs
    CorpusEntry("Please NO GO beyond this checkpoint.", "REDACTED_PLATE", False, "PLATE/TN/common-words-known-fp"),
    CorpusEntry("Check AI CD pipeline deployment status.", "REDACTED_PLATE", False, "PLATE/TN/tech-abbrev-known-fp"),
    # Safe TNs: digit-only strings too short or too long, lowercase context
    CorpusEntry("section 42 of the traffic regulations", "REDACTED_PLATE", False, "PLATE/TN/section-lowercase"),
    # KNOWN GAP: 3000 matches as first-group=30, sep=empty, second-group=00
    CorpusEntry("postcode for Melbourne CBD is 3000", "REDACTED_PLATE", False, "PLATE/TN/postcode-digits-known-fp"),

    # ── REDACTED_NAME (SpaCy PERSON) ────────────────────────────────────────────
    # Source: redactor.py  _NER_LABEL_MAP["PERSON"] = "[REDACTED_NAME]"
    # SpaCy en_core_web_sm — good recall for Western full names in sentence context;
    # lower recall for names without surrounding context or non-Western names.

    CorpusEntry("The applicant John Smith submitted the form.", "REDACTED_NAME", True, "NAME/TP/full-name"),
    CorpusEntry("Contact Jane Williams at the office.", "REDACTED_NAME", True, "NAME/TP/female-name"),
    CorpusEntry("Officer Michael Brown completed the review.", "REDACTED_NAME", True, "NAME/TP/officer-name"),
    CorpusEntry("Dr Sarah Thompson signed the report.", "REDACTED_NAME", True, "NAME/TP/titled-name"),
    CorpusEntry("Registered owner: David Chen.", "REDACTED_NAME", True, "NAME/TP/owner-name"),
    # True negatives — entities that are GPE/ORG/DATE, or no entity at all
    CorpusEntry("The incident occurred in Melbourne CBD.", "REDACTED_NAME", False, "NAME/TN/location-not-name"),
    CorpusEntry("What are the road rules for merging lanes?", "REDACTED_NAME", False, "NAME/TN/no-entities"),
    CorpusEntry("The vehicle was red and travelling north.", "REDACTED_NAME", False, "NAME/TN/descriptive-text"),
    CorpusEntry("Speed limit is 60 km/h on this road.", "REDACTED_NAME", False, "NAME/TN/regulatory-text"),
    CorpusEntry("Registration renewal is due annually.", "REDACTED_NAME", False, "NAME/TN/admin-text"),

    # ── REDACTED_LOCATION (SpaCy GPE/LOC) ──────────────────────────────────────
    # Source: redactor.py  _NER_LABEL_MAP["GPE"] = "[REDACTED_LOCATION]"
    #                       _NER_LABEL_MAP["LOC"] = "[REDACTED_LOCATION]"

    CorpusEntry("The incident occurred in Melbourne CBD.", "REDACTED_LOCATION", True, "LOCATION/TP/melbourne"),
    CorpusEntry("Driver travelling from Geelong to Sydney.", "REDACTED_LOCATION", True, "LOCATION/TP/multiple-cities"),
    CorpusEntry("Registered address is in Victoria.", "REDACTED_LOCATION", True, "LOCATION/TP/state-name"),
    CorpusEntry("Vehicle observed travelling through Ballarat.", "REDACTED_LOCATION", True, "LOCATION/TP/regional-city"),
    # True negatives — no geographic entity
    CorpusEntry("Speed limit is 100 km/h on freeways.", "REDACTED_LOCATION", False, "LOCATION/TN/speed-text"),
    CorpusEntry("The applicant submitted the form on time.", "REDACTED_LOCATION", False, "LOCATION/TN/no-location"),
    CorpusEntry("Registration expires at the end of the month.", "REDACTED_LOCATION", False, "LOCATION/TN/admin-text"),
    CorpusEntry("Section 45 penalty applies immediately.", "REDACTED_LOCATION", False, "LOCATION/TN/legal-reference"),

    # ── REDACTED_ORG (SpaCy ORG) ────────────────────────────────────────────────
    # Source: redactor.py  _NER_LABEL_MAP["ORG"] = "[REDACTED_ORG]"

    CorpusEntry("Employed by Department of Transport Victoria.", "REDACTED_ORG", True, "ORG/TP/govt-dept"),
    CorpusEntry("Contact VicRoads for licence renewal.", "REDACTED_ORG", True, "ORG/TP/vicroads"),
    CorpusEntry("Insured through RACV for comprehensive cover.", "REDACTED_ORG", True, "ORG/TP/racv"),
    CorpusEntry("Works at ANZ Bank Geelong branch.", "REDACTED_ORG", True, "ORG/TP/bank"),
    # True negatives — no organisation entity
    CorpusEntry("The car was travelling at high speed.", "REDACTED_ORG", False, "ORG/TN/no-org"),
    CorpusEntry("Road conditions were wet and slippery.", "REDACTED_ORG", False, "ORG/TN/descriptive"),
    CorpusEntry("Speed limit is 60 km/h in this zone.", "REDACTED_ORG", False, "ORG/TN/speed-limit"),
    CorpusEntry("The vehicle registration has expired.", "REDACTED_ORG", False, "ORG/TN/admin-text"),

    # ── REDACTED_DATE (SpaCy DATE) ──────────────────────────────────────────────
    # Source: redactor.py  _NER_LABEL_MAP["DATE"] = "[REDACTED_DATE]"
    # Guard: bare all-digit DATE entities are skipped (ent.text.replace(" ","").isdigit())
    # so formatted dates (letters/separators) are redacted; raw digit strings are not.

    CorpusEntry("Born on 15 January 1985.", "REDACTED_DATE", True, "DATE/TP/full-date-written"),
    CorpusEntry("Licence registered in March 2023.", "REDACTED_DATE", True, "DATE/TP/month-year"),
    CorpusEntry("Expiry date: 01/06/2025", "REDACTED_DATE", True, "DATE/TP/slash-format"),
    CorpusEntry("Licence expired in January 2024.", "REDACTED_DATE", True, "DATE/TP/month-year-2"),
    # True negatives — bare digits correctly skipped by isdigit() guard
    CorpusEntry("Reference number 20240115 on file.", "REDACTED_DATE", False, "DATE/TN/bare-digits-guarded"),
    CorpusEntry("ID code 12345 is currently active.", "REDACTED_DATE", False, "DATE/TN/id-digits"),
    # True negatives — no date entity at all
    CorpusEntry("The vehicle is blue and duly registered.", "REDACTED_DATE", False, "DATE/TN/no-date"),
    CorpusEntry("Speed limit applies on this road section.", "REDACTED_DATE", False, "DATE/TN/no-date-2"),
]
