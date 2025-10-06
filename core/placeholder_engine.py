from core.llm_utils import llm_detect_meta_intent
import re, logging

logger = logging.getLogger(__name__)

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

def handle_placeholder_reply(llm, session_id: str, sessions: dict, user_input: str) -> tuple[str, bool]:
    """Shared logic for filling placeholders.
    Returns (reply_text, done).
    If done=True, session is complete and manifests are rendered"""

    # Search for current active session
    session = sessions.get(session_id)
    if not session:
        return ("Сессия не найдена. Начните новую сессию.", True)

    user_input = user_input.strip()

    current_placeholder = session.current_placeholder
    expected_type = PLACEHOLDER_TYPES.get(current_placeholder, "str")

    intent = llm_detect_meta_intent(llm, user_input)

    if intent != "OTHER":
        logger.info(f"[MetaIntent] Detected: {intent}")
        if intent == "HOW_MANY_LEFT":
            return (progress_text(session), False)
        if intent == "LIST_PLACEHOLDERS":
            return (list_placeholders_text(session), False)
        if intent == "HELP":
            return(
                "Вы на этапе заполнения YAML-манифеста.\n"
                "- Введите значение текущего плейсхолдера.\n"
                "- Или напишите 'отмена' для выхода.\n"
                "- Или напишите 'список' для просмотра всех плейсхолдеров.\n"
                "- Или напишите 'сколько осталось' для просмотра количества оставшихся плейсхолдеров.\n",
                False
            )

        if intent == "CANCEL":
            sessions.end(session_id)
            return ("Отменяю процесс. Вы можете начать заново", True)
        return (f"Не удалось распознать команду. Попробуйте снова", False)

    if not is_placeholder_valid(user_input, expected_type):
        return (f"`{{{{ ${current_placeholder} }}}}` ожидает тип `{expected_type}`. Попробуйте снова:", False)

    # Save the value of current placeholder
    session.filled_values[current_placeholder] = user_input

    if session.remaining_placeholders:
        next_placeholder = session.remaining_placeholders.pop(0)
        session.current_placeholder = next_placeholder

        try:
            prompt = f"Объясни значение плейсхолдера `{{{{ ${next_placeholder} }}}}` и попроси пользователя ввести значение."
            response = llm.invoke(prompt)
            text = (getattr(response, "content", "") or "").strip()
        except Exception:
            text = f"Введите значение для ${{{next_placeholder}}}:"
        return (text, False)
    
    rendered = fill_placeholders(session.original_doc_text, session.filled_values)
    pretty = f"Все значения заполнены. Итоговые манифесты:\n\n```yaml\n{rendered}\n```"
    return ("Все значения заполнены! Итоговые манифесты:\n\n" + rendered, True)

def progress_text(session: dict) -> str:
    filled = len(session.filled_values)
    remaining = session.remaining_placeholders
    current = session.current_placeholder

    total = filled + len(remaining) + (1 if current else 0)

    return f"""Вы заполнили {filled} из {total} полей.
           Осталось {total - filled}
           Текущие плейсхолдеры: {', '.join([current] + remaining) if current else ', '.join(remaining) or 'Все заполнены!'}"""

def list_placeholders_text(session: dict) -> str:
    placeholders = extract_placeholders(session.original_doc_text)
    status_lines = []
    for placeholder in placeholders:
        if placeholder in session.filled_values:
            status_lines.append(f"- {placeholder} заполнен {session.filled_values[placeholder]}")
        else:
            status_lines.append(f"- {placeholder} не заполнен")
    return "Список всех плейсхолдеров:\n" + "\n".join(status_lines)
