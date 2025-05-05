import deepl, googletrans, re, logging

from src.database import CacheDB


# Переводчик - Google или DeepL
class Translator:
    def __init__(self, deepl_key: str = None, db: CacheDB = None, manual_dict: dict[str, str] = None,) -> None:
        self.deepl = deepl.Translator(deepl_key) if deepl_key else None
        self.google = googletrans.Translator()
        self.db = db
        # Словарь ручного перевода строк
        self.manual_dict = manual_dict or {
        }
        # 1) шаблон для разбивки
        self._manual_re = re.compile(
            "|".join(re.escape(k) for k in self.manual_dict),
        )

    def apply_manual(self, text: str) -> str:
        """
        Заменяем все вхождения ключей из manual_dict на их перевод.
        Используем границы слов, чтобы не задеть части других слов.
        """
        for src, tgt in self.manual_dict.items():
            # \b — граница «слово»
            pattern = r"\b" + re.escape(src) + r"\b"
            text = re.sub(pattern, tgt, text)
        return text

    async def translate(self, text: str, target_lang: str = "RU", test: bool = False) -> str:
        parts = re.split(f"({self._manual_re.pattern})", text)
        result_parts = []

        for part in parts:
            if part in self.manual_dict:
                # 2a) если нашли “заблокированное” слово — возвращаем сразу
                result_parts.append(self.manual_dict[part])
            elif part:
                # 2b) иначе — привычная цепочка: кеш → DeepL/Google
                tr = await self._translate_segment(part, target_lang, test)
                result_parts.append(tr)
            else:
                # пустые строки/разделители
                result_parts.append(part)

        return "".join(result_parts)

    async def _translate_segment(self, seg: str, target_lang: str, test: bool) -> str:
        # копируем вашу логику кеша и вызова API, только на сегмент
        if self.db:
            cur = self.db.conn.cursor()
            cur.execute("SELECT translated FROM translations WHERE source=?", (seg,))
            if row := cur.fetchone():
                return row[0]

        if test or not self.should_use_deepl():
            translated = await self.translate_google(seg, target_lang)
        else:
            translated = self.translate_deepl(seg, target_lang)

        if self.db:
            cur = self.db.conn.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO translations(source, translated) VALUES(?,?)",
                (seg, translated),
            )
            self.db.conn.commit()

        return translated

    # Проверка на работоспособность и лимиты DeepL
    def should_use_deepl(self) -> bool:
        if not self.deepl:
            return False
        usage = self.deepl.get_usage()
        return not usage.character.limit_exceeded

    # Перевод с помощью deepl
    def translate_deepl(self, text: str, target_lang: str) -> str:
        logging.info("Using DeepL for translation")
        translated = self.deepl.translate_text(
            text=text, target_lang=target_lang.upper()
        )
        return translated.text

    # Перевод с помощью google
    async def translate_google(self, text: str, target_lang: str) -> str:
        logging.info("Using Google for translation")
        translated = await self.google.translate(text=text, dest=target_lang.lower())
        return translated.text

    # Перевод по строкам
    async def translate_lines(self, lines: list[str]) -> list[str]:
        translated = []
        for line in lines:
            tr = await self.translate(line, target_lang="RU")
            translated.append(tr)
        return translated