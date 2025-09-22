import json
import logging
from pydantic import BaseModel
from typing import Literal
from models import Intent

logger = logging.getLogger(__name__)

class MetaIntentModel(BaseModel):
    intent: Literal[
        "HOW_MANY_LEFT",
        "LIST_PLACEHOLDERS",
        "HELP",
        "CANCEL",
        "OTHER"
    ]

# Expected response from LLM json
class SpecificityModel(BaseModel):
    is_specific: bool
    rephrased_query: str = ""
    followups: list[str] = []

def llm_classify_intent(llm, text: str) -> Intent:
    """Determine the purpose of the user's request"""
    prompt = f""" Ты - классификатор запросов пользователя. Выбери намерение пользователя на основании его запроса:
    - GET_MANIFESTS: запросил манифесты, yaml, интеграцию, сценарий и т.п.
    - HELP: спрашивает, что ты умеешь, как с тобой работать, просит инструкцию по твоему использованию
    - CHAT: любой другой запрос, который не требует манифестов

    Верни только одно слово: GET_MANIFESTS, HELP или CHAT

    Пользователь: {text}
    """

    try:
        response = llm.invoke(prompt)
        label = (getattr(response, "content", "") or "").strip().upper()
        logger.info(f"llm_classify_intent label: {label}")
        return Intent(label) if label in Intent._value2member_map_ else Intent.CHAT
        # if label in ["GET_MANIFESTS", "HELP", "CHAT"]:
        #     return label
    except Exception as e:
        logger.error(f"Произошла ошибка при классификации запроса пользователя: {e}")
        return "CHAT"

def llm_assess_specificity(llm, user_text: str) -> dict:
    """
    Запрос к LLM для оценки, насколько запрос пользователя позволяет понять, какие манифесты генерировать
    """
    prompt = f""" Ты - ассистент, который помогает пользователю сформировать манифесты для интеграции сервисов.
    Определи, достаточно ли специфичен запрос пользователя, чтобы искать нужные манифесты (True/False).
    Если нет - предложи 2-4 коротких уточняющих вопроса.
    Если да - перефразируй запрос кратко и предметно.

    Считай запрос достаточно специфичным, если он одновременно содержит:
    1) "Явное упоминание istio/Istio/истио/Истио и"
    2) "Конкретное название внешнего сервиса/БД/системы (например: secman, postgres, kafka, redis и т.д.)
    Формулировки вида "Хочу...", "Нужны..." не влияют на специфичность."

    Верни строго JSON вида:
    {{
        "is_specific": true|false,
        "rephrased_query": "строка (может быть пустой)",
        "followups": ["вопрос1", "вопрос2", ...]
    }}

    Запрос: {user_text}
    """

    try:
        response = llm.invoke(prompt)
        # If response is not a string and falsy, make sure at least string is returned
        raw = (getattr(response, "content", "") or "").strip()
        parsed = json.loads(raw)

        # Validate & normalize the LLM response with Pydantic
        model = SpecificityModel.model_validate(parsed)
        data = model.model_dump()

        logger.info(f"data['is_specific']: {data['is_specific']}")
        logger.info(f"data['rephrased_query']: {data['rephrased_query']}")
        return data

    except Exception as e:
        logger.error(f"Ошибка при оценке специфичности запроса: {e}")
        return {
            "is_specific": False,
            "rephrased_query": "",
            "followups": [
                "С каким сервисом вы хотите интегрировать istio service mesh?",
            ]
        }

def llm_rephrase_history(llm, messages: list[str]) -> str:
    """
    Rephrase user's request if it is vague or contains duplicates after combining user's previous messages
    """
    history = " | ".join(m.strip() for m in messages if m and m.strip())
    
    prompt = f"""
    Ты получаешь историю сообщений пользователя, которые уточняют один и тот же запрос.
    Перефразируй их в одно короткое и однозначное предложение, которое выражает суть, убери повторы и лишние слова.
    Верни ТОЛЬКО перефразированный запрос без каких-либо пояснений.

    История:
    {history}
    """

    try:
        response = llm.invoke(prompt)
        rephrased = (getattr(response, "content", "") or "").strip()
        return rephrased or (messages[-1].strip() if messages else "")
    except Exception:
        return messages[-1].strip() if messages else ""

def llm_detect_meta_intent(llm, user_text: str) -> str:
    """For situations when a user enters a non-value during MANIFEST mode
    Returns one of: HOW_MANY_LEFT, LIST_PLACEHOLDERS, HELP, CANCEL, OTHER"""

    prompt = f"""
    Ты - классификатор коротких пользовательских сообщений, введенных во время заполнения плейсхолдеров в YAML.
    Верни строго JSON одного из следующих видов, ничего кроме JSON не добавляй:

    {{"intent": "HOW_MANY_LEFT"}} - если пользователь спрашивает, сколько плейсхолдеров или параметров осталось
    {{"intent": "LIST_PLACEHOLDERS"}} - если пользователь спрашивает, какие плейсхолдеры или параметры есть, или что надо заполнить
    {{"intent": "HELP"}} - если пользователь просит помощь, пишет "помощь", "что ты умеешь"
    {{"intent": "CANCEL"}} - если пользователь хочет отменить заполнение, выйти из сессии или прекратить (например: "отмена", "стоп", "закончить")
    {{"intent": "OTHER"}} - любое другое сообщение (в т.ч. случайный текст, который не является значением)
    Текст: {user_text}
    """
    try:
        resp = llm.invoke(prompt)
        raw = (getattr(resp, "content", "") or "").strip()
        logger.info(f"[MetaIntent] LLM raw = {raw}")

        parsed = json.loads(raw)
        logger.info(f"[MetaIntent] Parsed JSON: {parsed}")

        model = MetaIntentModel.model_validate(parsed)
        return model.intent
    except Exception as e:
        # fallback in case of parsing failure or bad LLM output
        logger.warning(f"[MetaIntent] Parsing failed: {e}")
        return "OTHER"

def llm_detect_meta_in_scenario_mode(llm, user_text: str) -> str:
    """
    Detects meta-intent in ASK_SCENARIO mode.
    Returns one of: "HELP", "CANCEL", "OTHER"
    """

    prompt = f"""
    Ты - помощник, который классифицирует сообщения пользователя на этапе сбора сценария.

    Возможные категории:
    - HELP: пользователь спрашивает, кто ты, что ты умеешь, просит помощи, хочет узнать о возможностях.
    - CANCEL: пользователь хочет выйти, прервать, отменить процесс.
    - OTHER: любое другое сообщение, связанное с описанием сценария или задачи.

    Проанализируй следующее сообщение: 

    \"{user_text}\"

    Ответь только одной категорией: HELP, CANCEL или OTHER.
    """

    try:
        response = llm.invoke(prompt)
        text = (getattr(response, "content", "") or "").strip().upper()

        # Normalize result just in case
        if "HELP" in text:
            return "HELP"
        elif "CANCEL" in text:
            return "CANCEL"
        else:
            return "OTHER"

    except Exception as e:
        logger.warning(f"[llm_detect_meta_in_scenario_mode] Ошибка при вызове LLM: {e}")
        return "OTHER"
