from core.llm_utils import llm_detect_meta_intent
from placeholder_utils import PLACEHOLDER_TYPES, extract_placeholders, fill_placeholders, is_placeholder_valid
import logging

logger = logging.getLogger(__name__)

def handle_placeholder_reply(llm, session_id: str, sessions: dict, user_input: str) -> tuple[str, bool]:
    """Shared logic for filling placeholders.
    Returns (reply_text, done).
    If done=True, session is complete and manifests are rendered"""

    # Search for current active session
    session = sessions.get(session_id)
    if not session:
        return ("Сессия не найдена. Начните новую сессию.", True)

    user_input = user_input.strip()
    current_placeholder = session.get("current_placeholder")
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
            sessions.pop(session_id, None)
            return ("Отменяю процесс. Вы можете начать заново", True)
        return (f"Не удалось распознать команду. Попробуйте снова", False)

    if not is_placeholder_valid(user_input, expected_type):
        return (f"`{{{{ ${current_placeholder} }}}}` ожидает тип `{expected_type}`. Попробуйте снова:", False)

    # Save the value of current placeholder
    session["filled_values"][current_placeholder] = user_input

    if session["remaining_placeholders"]:
        next_placeholder = session["remaining_placeholders"].pop(0)
        session["current_placeholder"] = next_placeholder

        try:
            prompt = f"Объясни значение плейсхолдера `{{{{ ${next_placeholder} }}}}` и попроси пользователя ввести значение."
            response = llm.invoke(prompt)
            text = (getattr(response, "content", "") or "").strip()
        except Exception:
            text = f"Введите значение для ${{{next_placeholder}}}:"
        return (text, False)
    
    rendered = fill_placeholders(session["original_doc_text"], session["filled_values"])
    pretty = f"Все значения заполнены. Итоговые манифесты:\n\n```yaml\n{rendered}\n```"
    return ("Все значения заполнены! Итоговые манифесты:\n\n" + rendered, True)

def progress_text(session: dict) -> str:
    filled = len(session["filled_values"])
    remaining = session["remaining_placeholders"]
    current = session.get("current_placeholder")

    total = filled + len(remaining) + (1 if current else 0)

    return f"""Вы заполнили {filled} из {total} полей.
           Осталось {total - filled}
           Текущие плейсхолдеры: {', '.join([current] + remaining) if current else ', '.join(remaining) or 'Все заполнены!'}"""

def list_placeholders_text(session: dict) -> str:
    placeholders = extract_placeholders(session["original_doc_text"])
    status_lines = []
    for placeholder in placeholders:
        if placeholder in session["filled_values"]:
            status_lines.append(f"- {placeholder} заполнен {session['filled_values'][placeholder]}")
        else:
            status_lines.append(f"- {placeholder} не заполнен")
    return "Список всех плейсхолдеров:\n" + "\n".join(status_lines)
