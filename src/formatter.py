import re

from jinja2 import Template

from src.templates.templates import *


def find1(pattern: str, text: str, default: str = UNDEFINED_TEXT) -> str:
    m = re.search(pattern, text, flags=re.IGNORECASE)
    return m.group(1) if m else default


# Класс форматирования сообщений
class Formatter:
    @staticmethod
    def get_template(msg_type: str) -> Template:
        return {
            "FLR": FLR_TEMPLATE,
            "SEP": SEP_TEMPLATE,
            "CME": CME_TEMPLATE,
            "IPS": IPS_TEMPLATE,
            "MPC": MPC_TEMPLATE,
            "GST": GST_TEMPLATE,
            "RBE": RBE_TEMPLATE,
        }[msg_type]
    
    @staticmethod
    
    @staticmethod
    def extract_context(ev: dict) -> dict:
        body = ev.get("messageBody", "")
        ctx = {"event_id": ev.get("messageID", UNDEFINED_TEXT)}

        if ev["messageType"] == "FLR":
            # Первый, «классический» вариант
            start = find1(r"Flare start time:?\s*([0-9T:\-]+Z)", body)
            peak  = find1(r"Flare peak time:?\s*([0-9T:\-]+Z)", body)
            inten = find1(r"Flare intensity:?\s*([\w\.]+)", body)

            if start != UNDEFINED_TEXT and peak != UNDEFINED_TEXT and inten != UNDEFINED_TEXT:
                ctx.update({
                    "start_time": start,
                    "peak_time": peak,
                    "intensity": inten
                })
            else:
                # Вариант «threshold crossing»
                # пример: "Flare M5.0 crossing time: 2025-05-14T03:23Z."
                m = re.search(r"Flare\s+(\S+)\s+crossing time:?\s*([0-9T:\-]+Z)", body)
                if m:
                    intensity_cross = m.group(1)   # например "M5.0"
                    cross_time      = m.group(2)   # например "2025-05-14T03:23Z"
                    ctx.update({
                        "start_time":  cross_time,
                        "peak_time":   cross_time,
                        "intensity":   intensity_cross
                    })
                else:
                    # ни классический, ни «threshold»: всё не найдено
                    ctx.update({
                        "start_time": UNDEFINED_TEXT,
                        "peak_time":  UNDEFINED_TEXT,
                        "intensity":  UNDEFINED_TEXT
                    })

        elif ev["messageType"] == "SEP":
            # здесь пока простой шаблон без полей
            pass

        elif ev["messageType"] == "CME":
            ctx.update({
                "cme_type":  find1(r"(\w-type)\s+CME", body),
                "start_time":find1(r"Start time of the event:?\s*([0-9T:\-]+Z)", body),
                "speed":     find1(r"Estimated speed:?\s*~?([\d\.]+\s*km/s)", body),
                "angle":     find1(r"Estimated opening half-angle:?\s*(\d+\s*deg)", body),
                "direction": find1(r"Direction \(lon\./lat\.\):\s*([\d\/\-]+)", body),
            })

        elif ev["messageType"] == "IPS":
            ctx["detect_time"] = find1(r"at\s+([0-9T:\-]+Z)", body)

        elif ev["messageType"] == "MPC":
            ctx["start_time"] = find1(r"starting at\s+([0-9T:\-]+Z)", body)

        elif ev["messageType"] == "GST":
            ctx.update({
                "start_time": find1(r"during the synoptic period\s+([0-9T:\-]+Z)", body),
                "end_time":   find1(r"to\s+([0-9T:\-]+Z)", body),
                "k-index":    find1(r"Kp index has reached level\s+(\d+\.\d{2})", body),
            })

        elif ev["messageType"] == "RBE":
            ctx["start_time"] = find1(r"at\s+([0-9T:\-]+Z)", body)

        return ctx