import re

from jinja2 import Template

from src.templates.templates import *


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
    def extract_context(ev: dict) -> dict:
        body = ev["messageBody"]
        # общие поля
        ctx = {
            "event_id": ev["messageID"],
        }
        # в зависимости от типа парсим регулярками, SEP - пока пропускаем
    # FLR
        if ev["messageType"] == "FLR":
            ctx.update({
                "start_time":   re.search(r"Flare start time:\s*(\S+Z)", body).group(1),
                "peak_time":    re.search(r"Flare peak time:\s*(\S+Z)", body).group(1),
                "intensity":    re.search(r"Flare intensity:\s*([\w\.]+)", body).group(1),
            })
    # CME
        elif ev["messageType"] == "CME":
            ctx.update({
                "cme_type":  re.search(r"(\w-type) CME", body).group(1),
                "start_time":re.search(r"Start time of the event:\s*(\S+Z)", body).group(1),
                "speed":     re.search(r"Estimated speed:\s*~?([\d\.]+\s*km/s)", body).group(1),
                "angle":     re.search(r"Estimated opening half-angle:\s*(\d+\s*deg)", body).group(1),
                "direction": re.search(r"Direction \(lon\./lat\.\):\s*([\d\/\-]+)", body).group(1),
            })
    # IPS
        elif ev["messageType"] == "IPS":
            ctx["detect_time"] = re.search(r"at\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z)", body).group(1)
    # MPC
        elif ev["messageType"] == "MPC":
            ctx["start_time"] = re.search(r"starting at\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z)", body).group(1)
    # GST
        elif ev["messageType"] == "GST":
            ctx.update({
                "start_time":re.search(r"during the synoptic period\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z))", body).group(1),
                "end_time":re.search(r"to\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z)", body).group(1),
                "k-index": re.search(r"Kp index has reached level\s+(\d+\.\d{2})", body).group(1),
            })
    # RBE
        elif ev["messageType"] == "RBE":
            ctx["start_time"] = re.search(r"at\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z)", body).group(1)

        return ctx