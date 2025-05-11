import re

from jinja2 import Template


# Форматирование текста, два этапа: 
#   -сырой json разбивается строки и достаются переменные
#   -готовое сообщение для отправки
class Formatter:
    # Шаблон сообщения
    MSG_TEMPLATE = Template(
        """
**[{{ msg_type }}]** - {{ event_id }} - **{{ event_name }}**

База Данных Уведомлений, Знаний и информации Центра Координируемого Сообществом Моделирования ([CCMC DONKI](https://ccmc.gsfc.nasa.gov/tools/DONKI/))

**Сводка**:
{% for line in lines -%}
{{ line }}
{% endfor %}

{% if notes %}
**Примечания**:
{% for note in notes -%}
{{ note }}
{% endfor %}
{% endif %}

{% if links %}
**Ссылки на смоделированные анимации**:
{% for url in links -%}
- {{ url }}
{% endfor %}
{% endif %}
""".strip()
    )

    # Установка имени в зависимости от типа события
    @staticmethod
    def set_name(msg_type: str):
        match msg_type:
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
            case _:
                return f"Неизвестный тип {msg_type}"

    # Метод форматирования сырого json, убирает ненужные на этом этапе строки
    @classmethod
    def pre_format(cls, ev: dict) -> dict:
        raw = ev.get("messageBody", "") or ""

        # Убираем всё до summary
        parts = re.split(r"##\s*Summary\s*:", raw, maxsplit=1)
        summary_block = parts[1] if len(parts) > 1 else raw

        # Делим на summary и notes
        parts = re.split(r"##\s*Notes\s*:", summary_block, maxsplit=1)
        summary_part = parts[0]
        notes_part = parts[1] if len(parts) > 1 else ""

        # Вырезаем ссылки
        lines, links = [], []
        for ln in summary_part.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            # Убираем автоматические комментарии по анимациям
            if re.search(r"Links? to the movies? of the modeled event", ln, flags=re.IGNORECASE):
                continue
            if re.search(r"Links? to the movies? of the modeled event", ln, flags=re.IGNORECASE):
                continue
            if re.search(r"^\([a-z]\)", ln, flags=re.IGNORECASE):
                continue
            if ln.startswith("http"):
                links.append(ln)
            else:
                lines.append(ln)

        # Убираем лишнее
        
        
        # Разбираем notes на отдельные непустые строки, убираем notes совсем если пусто
        notes = [ln.strip() for ln in notes_part.splitlines() if ln.strip()]

        # Собираем, возвращаем
        return {
            "event_id":     ev.get("messageID", ""),
            "event_name":   cls.set_name(ev.get("messageType", "")),
            "msg_type":     ev.get("messageType", ""),
            "lines":        lines,
            "notes":        notes,
            "links":        links,
        }

    # Форматируем окончательный текст по шаблону, добавляя или возвращая контент
    @classmethod
    def post_format(cls, data: dict) -> str:
        return cls.MSG_TEMPLATE.render(**data)
    
    @staticmethod
    def split_line(line: str) -> tuple[list[str], list[str]]:
        parts = re.split(r"(\. |: )", line)
        texts = parts[::2]
        delims = parts[1::2]
        return texts, delims
    
    @staticmethod
    def rejoin_line(texts: list[str], delims: list[str]) -> str:
        out = ""
        for i, txt in enumerate(texts):
            out += txt
            if i < len(delims):
                out += delims[i]
        return out