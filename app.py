import calendar
from datetime import datetime
from pathlib import Path

from litestar.di import Provide
from sqlalchemy import Column, Integer, Boolean, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession
from litestar import Litestar, get, post
from litestar.plugins.htmx import HTMXPlugin, HTMXRequest, HTMXTemplate
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.template.config import TemplateConfig
from litestar.response import Template
from litestar.plugins.sqlalchemy import (
    AsyncSessionConfig,
    SQLAlchemyAsyncConfig,
    SQLAlchemyInitPlugin,
    repository,
    base,
)

# Настройки базы данных
session_config = AsyncSessionConfig(expire_on_commit=False)
sqlalchemy_config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///challenge.sqlite", session_config=session_config, create_all=True
)  # Create 'async_session' dependency.


# Модель для хранения выполнения дней челленджа
class ChallengeDay(base.BigIntBase):
    __tablename__ = "challenge_days"
    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    day = Column(Integer, nullable=False)
    completed = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint('year', 'month', 'day', name='unique_year_month_day'),
    )


class ChallengeDayRepository(repository.SQLAlchemyAsyncRepository[ChallengeDay]):
    model_type = ChallengeDay


async def provider_challenge_day_repository(db_session: AsyncSession) -> ChallengeDayRepository:
    return ChallengeDayRepository(session=db_session)


# Главная страница
@get("/")
async def index(repo: ChallengeDayRepository) -> Template:
    # Получаем текущий месяц и год
    current_year = datetime.now().year
    current_month = datetime.now().month

    # Вычисляем количество дней в месяце
    days_in_month = calendar.monthrange(current_year, current_month)[1]

    # Запрашиваем существующие дни из базы
    days = await repo.list()

    # Если дней нет, создаем их с учетом текущего месяца
    if not days:
        for i in range(1, days_in_month + 1):
            await repo.add(ChallengeDay(
                year=current_year,
                month=current_month,
                day=i,
                completed=False
            ))
        await repo.session.commit()
        days = await repo.list()

    # Передаем количество дней в шаблон
    return Template("index.html.jinja2", context={"days": days})


# Обновление состояния дня с использованием HTMX
@post("/toggle/{day:int}")
async def toggle_day(day: int, repo: ChallengeDayRepository) -> HTMXTemplate:
    challenge_day = await repo.get_one(day=day)
    if challenge_day:
        challenge_day.completed = not challenge_day.completed
        await repo.add(challenge_day, auto_commit=True)
    return HTMXTemplate(template_name="day.html.jinja2", context={"day": challenge_day}, re_swap="outerHTML", re_target=f"#day-{day}")


# Конфигурация Jinja2 и запуск приложения
app = Litestar(
    route_handlers=[index, toggle_day],
    debug=True,
    plugins=[HTMXPlugin(), SQLAlchemyInitPlugin(config=sqlalchemy_config)],
    template_config=TemplateConfig(
        directory=Path("templates"),
        engine=JinjaTemplateEngine,
    ),
    request_class=HTMXRequest,
    dependencies={"repo": Provide(provider_challenge_day_repository)},
)
