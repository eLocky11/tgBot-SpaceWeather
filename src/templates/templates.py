from jinja2 import Template, Undefined

UNDEFINED_TEXT = "Неизвестно"

class DefaultUndefined(Undefined):
    def __str__(self):
        # при любом доступе к неопределённой переменной возвращаем текст
        return UNDEFINED_TEXT

FLR_TEMPLATE = Template(
    """
<b>Обнаружена <a href="https://ru.wikipedia.org/wiki/Солнечная_вспышка">солнечная вспышка!</a></b>

<u>ID активности:</u> <code>{{ event_id }}</code>
<u>Время начала вспышки:</u> <code>{{ start_time }}</code>
<u>Время пиковой активности:</u> <code>{{ peak_time }}</code>
<u>Класс интенсивности:</u> <code>{{ intensity }}</code>

Ожидаются изменения в поведении геомагнитного поля Земли, возможны шторма.
""".strip(), undefined=DefaultUndefined
)


SEP_TEMPLATE = Template(
    """
<b>↗Обнаружен <a href="https://ru.wikipedia.org/wiki/Солнечная_активность">подъем энергичных частиц</a></b>
""".strip(), undefined=DefaultUndefined
)


CME_TEMPLATE = Template(
    """
<b>Обнаружены <a href="https://ru.wikipedia.org/wiki/Корональные_выбросы_массы">Корональные выбросы массы</a></b>

<u>ID активности:</u> <code>{{ event_id }}</code>
<u>Тип:</u> <code>{{ cme_type }}</code>
<u>Время начала выброса:</u> <code>{{ start_time }}</code>
<u>Расчетная скорость:</u> <code>{{ speed }}</code>
<u>Расчетная угол раскрытия:</u> <code>{{ angle }}</code>
<u>Направление (экв. координаты Земли):</u> <code>{{ direction }}</code> 
""".strip(), undefined=DefaultUndefined
)


IPS_TEMPLATE = Template(
    """
<b>Обнаружены <a href="https://ru.wikipedia.org/wiki/Гелиосфера#Граница_ударной_волны">межпланетные ударные волны</a></b>

<u>ID активности:</u> <code>{{ event_id }}</code>
<u>Время обнаружения:</u> <code>{{ detect_time }}</code>

Прогнозируется геомагнитная буря.
""".strip(), undefined=DefaultUndefined
)


MPC_TEMPLATE = Template(
    """
<b>Обнаружены <a href="https://ru.wikipedia.org/wiki/Магнитное_поле_Земли#Внешнее_магнитное_поле">прорывы магнитопаузы</a></b>

<u>ID активности:</u> <code>{{ event_id }}</code>
<u>Расчетное время начала:</u> <code>{{ start_time }}</code>

Прогнозируется сильное сжатие магнитосферы.
Ожидаются геомагнитные шторма и корональные выбросы массы.
""".strip(), undefined=DefaultUndefined
)


GST_TEMPLATE = Template(
    """
<b>Обнаружен <a href="https://ru.wikipedia.org/wiki/Геомагнитная_буря">геомагнитный шторм</a></b>

<u>ID активности:</u> <code>{{ event_id }}</code>
<u>Время начала шторма:</u> <code>{{ start_time }}</code>
<u>Расчетное время окончания:</u> <code>{{ end_time }}</code>
<u><a href="https://ru.wikipedia.org/wiki/K-индекс">К-индекс</a>:</u> <code>{{ k-index }}</code>

В зависимости от показателя индекса прогнозируются различные эффекты на сердечно-сосудистые заболевания.
""".strip(), undefined=DefaultUndefined
)


RBE_TEMPLATE = Template(
    """
<b>Обнаружено усиление <a href="https://ru.wikipedia.org/wiki/Радиационный_пояс">радиационных поясов</a></b>

<u>ID активности:</u> <code>{{ event_id }}</code>
<u>Расчетное время начала:</u> <code>{{ start_time }}</code>

Значительно повышенные потоки энергичных электронов во внешнем радиационном поясе Земли.
Ожидаются разные влияния на сердечно-сосудистыми заболевания, а также повышается риск возникновения мигрени.
""".strip(), undefined=DefaultUndefined
)