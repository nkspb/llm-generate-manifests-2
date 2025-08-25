import re

PLACEHOLDER_PATTERN = r"\{\{\s*\$(\w+)\s*\}\}" # {{ $dpPort1 }}

def extract_placeholders(yaml_text: str) -> list[str]:
    """Extract unique placeholders like {{ $dbPort1 }}."""
    return sorted(set(re.findall(PLACEHOLDER_PATTERN, yaml_text)))

def is_placeholder_valid(value: str, expected_type: str) -> bool:
    if expected_type == "int":
        return value.strip().isdigit()
    elif expected_type == "str":
        return bool(value.strip())
    elif expected_type == "url":
        return re.match(r'^https:?//', value.strip()) is not None
    return True

def fill_placeholders(yaml_text: str, values: dict[str, str]) -> str:
    print("[DEBUG] Starting fill_placeholders")
    print("[DEBUG] values = ", values)

    for key, value in values.items():
        pattern = re.compile(r"\{\{\s*\$" + re.escape(key) + r"\s*\}\}")
        yaml_text = pattern.sub(value, yaml_text)
    return yaml_text
    
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
