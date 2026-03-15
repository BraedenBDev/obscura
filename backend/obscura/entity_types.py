"""
Entity types for GLiNER PII detection.

Using labels compatible with urchade/gliner_multi_pii-v1 model.
"""

# Labels for the PII-specific GLiNER model
# These are the labels the model was trained on
ENTITY_LABELS = [
    "person",
    "email",
    "phone number",
    "address",
    "date of birth",
    "credit card number",
    "bank account",
    "iban",
    "passport number",
    "social security number",
    "national id",
    "driver license",
    "tax id",
    "medical record",
    "ip address",
    "username",
]

# Map GLiNER output labels to short internal types for placeholders
LABEL_TO_TYPE = {
    "person": "person_name",
    "email": "email",
    "phone number": "phone",
    "address": "address",
    "date of birth": "date_of_birth",
    "credit card number": "credit_card",
    "bank account": "bank_account",
    "iban": "iban",
    "passport number": "passport",
    "social security number": "ssn",
    "national id": "national_id",
    "driver license": "driver_license",
    "tax id": "tax_id",
    "medical record": "medical_id",
    "ip address": "ip_address",
    "username": "username",
}

# For backward compatibility
ENTITY_TYPES = {v: k for k, v in LABEL_TO_TYPE.items()}

# Human-readable display names
DISPLAY_NAMES = {
    "person_name": "Person Name",
    "email": "Email",
    "phone": "Phone",
    "address": "Address",
    "date_of_birth": "Date of Birth",
    "credit_card": "Credit Card",
    "bank_account": "Bank Account",
    "iban": "IBAN",
    "passport": "Passport",
    "ssn": "SSN",
    "national_id": "National ID",
    "driver_license": "Driver License",
    "tax_id": "Tax ID",
    "medical_id": "Medical ID",
    "ip_address": "IP Address",
    "username": "Username",
    # Legacy mappings for backward compatibility
    "government_id": "Government ID",
    "financial_account": "Financial Account",
    "digital_id": "Digital ID",
    "reference_number": "Reference Number",
}
