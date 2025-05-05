import re

from jinja2 import Template


# Форматирование текста, два этапа: сырое до перевода, готовое сообщение для отправки
class Formatter:
    # Шаблон сообщения
    MSG_TEMPLATE_LEGACY = Template(
        """
**[{{ msg_type }}]** - {{ event_id }} - **{{ event_name }}**

**Сводка**:
{{ summary_text }}

{% if notes %}
Примечания:
{{ notes }}
{% endif %}

{% if links %}
Ссылки на анимации:
{% for url in links -%}
- {{ url }}
{% endfor %}
{% endif %}
""".strip()
    )

    MSG_TEMPLATE = Template(
        """
**[{{ msg_type }}]** - {{ event_id }} - **{{ event_name }}**

**Сводка**:
{{ summary_text }}

{% if notes %}
Примечания:
{{ notes }}
{% endif %}
""".strip()
    )

    @staticmethod
    def _find(text: str, pattern: str) -> str | None:
        m = re.search(pattern, text)
        return m.group(1).strip() if m else None

    @staticmethod
    def set_name(id: str):
        match id:
            case "FLR":
                return "Солнечная вспышка"
            case "SEP":
                return "Подъём энергичных частиц"
            case "CME":
                return "Корональный выброс массы"
            case "IPS":
                return "Межпланетные ударные волны"
            case "MPC":
                return "Прорывы магнитопаузы"
            case "GST":
                return "Геомагнитные бури"
            case "RBE":
                return "Усиление радиационных поясов"

    @classmethod
    def base_data(cls, ev: dict) -> dict:
        msg_type = ev.get("messageType", "")
        msg_id = ev.get("messageID", "")
        msg_time = ev.get("messageIssueTime", "")
        msg_name = cls.set_name(msg_type)
        body = ev.get("messageBody", "") or ""
        lines = cls.extract_body_lines(body)
        links = cls.extract_links(ev, body)
        return {
            "event_id": msg_id,
            "event_name": msg_name,
            "msg_type": msg_type,
            "msg_time": msg_time,
            "body": body,
            "lines": lines,
            "links": links,
        }
    
    # Класс разбития сообщения по строкам
    @classmethod
    def extract_body_lines(cls, text: str) -> list[str]:
        lines = []

    # Удалить, его заменит метод extract_summary_lines
    @classmethod
    def extract_summary_notes(cls, body: str) -> tuple[str, str]:
        """
        Разбивает body на два куска:
        - summary: всё, что между '## Summary:' и (перед) '## Notes:' или концом строки
        - notes: всё, что после '## Notes:' до конца body
        """
        # 1) Найдём и вырежем Notes
        notes = ""
        m_notes = re.search(r"##\s*Notes:\s*([\s\S]+)$", body)
        if m_notes:
            notes = m_notes.group(1).strip()
            # обрезаем тело до начала Notes
            body = body[: m_notes.start()]

        # 2) Найдём Summary
        summary = ""
        m_sum = re.search(r"##\s*Summary:\s*([\s\S]+?)(?=(\n##\s*\w+:)|\Z)", body)
        if m_sum:
            summary = m_sum.group(1).strip()

        # 3) Уберём Markdown-заголовки '## ' из summary
        #    (например строки, начинающиеся с '## ')
        summary = re.sub(r"(?m)^##\s*", "", summary)

        return summary, notes

    @classmethod
    def extract_links(cls, ev: dict, body: str) -> list[str]:
        """
        Собирает все HTTP(S)-ссылки из body и возвращает их списком.
        Не мутирует ev или body — но при желании можно вырезать ссылки из body.
        """
        # найдём все вхождения ссылок
        urls = re.findall(r"https?://\S+", body)
        # убираем дубли, сохраняя порядок
        seen = set()
        unique = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                unique.append(u)
        return unique

    # Главная точка входа для разбора сырого JSON
    @classmethod
    def pre_format(cls, ev: dict) -> dict:
        data = cls.base_data(ev)

        return data

    # Форматируем окончательный текст по шаблону
    @classmethod
    def post_format(cls, data: dict) -> str:
        return cls.MSG_TEMPLATE.render(**data)