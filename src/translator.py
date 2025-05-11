import deepl, googletrans, re, logging

from src.database import DataBase


MANUAL_DICT = {
    "SCORE CME typification system:": "Система типизации выбросов корональной массы:",
    "S-type": "S-тип",
    "C-type": "C-тип",
    "O-type": "O-тип",
    "R-type": "R-тип",
    "ER-type": "ER-тип",
    "Estimated speed": "Расчетная скорость",
    "Estimated opening half-angle": "Расчетный угол раскрытия",
    "Direction (lon./lat.)": "Направление (долгота/широта)",
    "Activity ID": "ID активности",
    "Start time of the event": "Время начала события",
    "CMEs with speeds less than 500 km/s": "менее 500 км/с",
    "Common 500-999 km/s": "500-999 км/с",
    "Occasional 1000-1999 km/s": "1000-1999 км/с",
    "Rare 2000-2999 km/s": "2000-2999 км/с",
    "Extremely Rare >3000 km/s": "более 3000 км/с",
}


# Переводчик - Google или DeepL
class Translator:
    def __init__(self, deepl_key: str = None, db: DataBase = None) -> None:
        self.deepl = deepl.Translator(deepl_key) if deepl_key else None
        self.google = googletrans.Translator()
        self.db = db

        # Инициализация и добавление ручного словаря в кэш
        self.db.add_cache_lines(list(MANUAL_DICT.items()))


# Основной метод перевода, принимает список строк, построчно делит на предложения или отделяет через ":", возвращает переведенный список
    async def on_translate(self, text_list: list[str], src_lang: str = "en", target_lang: str = "ru") -> list[str]:
        result_lines: list[str] = []               # итоговый список переводов
        cache_pairs: list[tuple[str,str]] = []     # пары для кэша

        for line in text_list:
            if not self.db.get_translate_line(line):
                translated = await self.google_translate(line, src_lang.lower(), target_lang.lower())
                cache_pairs.append((line, translated))
                result_lines.append(translated)
            else:
                result_lines.append(self.db.get_translate_line(line))
        
        # один единственный вызов пакетной вставки
        if cache_pairs:
            self.db.add_cache_lines(cache_pairs)
        return result_lines


# Google (async) translate
    async def google_translate(self, text: str, src_lang: str, target_lang: str) -> str:
        async with googletrans.Translator() as tr:
            res = await tr.translate(text, src=src_lang, dest=target_lang)
            return res.text


# DeepL checker
    def deepl_check(self) -> bool:
        usage = self.deepl.get_usage()
        if usage.character.limit_exceeded:
            logging.warning("DeepL character limit exceeded")
            return False
        else:
            logging.info(f"DeepL limit usege: {usage.character}")
            return True


# DeepL translate
    def deepl_translate(self):
        pass