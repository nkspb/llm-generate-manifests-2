import re
import logging

PLACEHOLDER_PATTERN = r"\{\{\s*\$(\w+)\s*\}\}" # {{ $dpPort1 }}

PLACEHOLDER_TYPES = {
    "secretServerHost": "str",
    "egressLabel": "str",
    "serverHostDB1": "str",
    "serverHostDB1ip": "str",
    "serverHostDB2": "str",
    "serverHostDB2ip": "str",
    "serverPort": "int",
    "virtualPortDB1": "int",
    "virtualPortDB2": "int",
    "pathToCACert": "str",
    "pathToCert": "str",
    "pathToKey": "str"
}

def extract_placeholders(yaml_text: str) -> list[str]:
    """Extract unique placeholders like {{ $dbPort1 }}."""
    return sorted(set(re.findall(PLACEHOLDER_PATTERN, yaml_text)))

def fill_placeholders(yaml_text: str, values: dict[str, str]) -> str:
    print("[DEBUG] Starting fill_placeholders")
    print("[DEBUG] values = ", values)

    for key, value in values.items():
        pattern = re.compile(r"\{\{\s*\$" + re.escape(key) + r"\s*\}\}")
        yaml_text = pattern.sub(value, yaml_text)
    return yaml_text

def is_placeholder_valid(value: str, expected_type: str) -> bool:
    value = value.strip()

    if expected_type == "int":
        return value.isdigit()

    elif expected_type == "url":
        return re.match(r'^https?://', value) is not None

    elif expected_type == "str":
        # Accept only strings that look like hostnames, labels, paths etc
        # Reject empty, whitespace-only, or long phrases with spaces
        if not value:
            return False

        if len(value.split()) > 1:
            return False

        if value.isdigit():
            return False

        return True

def format_placeholder_list(placeholders: list[str]) -> str:
    """Formats a list of placeholders for printing."""
    if not placeholders:
        return "Найденные манифесты не содержат параметров для заполнения"
    return "Список параметров для заполнения:\n" + "\n".join(f"- ${name}" for name in placeholders)
