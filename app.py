from pathlib import Path

from litestar.di import Provide
from sqlalchemy import Column, Integer, Boolean
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
    day = Column(Integer, unique=True, nullable=False)
    completed = Column(Boolean, default=False)


class ChallengeDayRepository(repository.SQLAlchemyAsyncRepository[ChallengeDay]):
    model_type = ChallengeDay


async def provider_challenge_day_repository(db_session: AsyncSession) -> ChallengeDayRepository:
    return ChallengeDayRepository(session=db_session)


# Главная страница
@get("/")
async def index(repo: ChallengeDayRepository) -> Template:
    days = await repo.list()
    if not days:
        for i in range(1, 31):
            await repo.add(ChallengeDay(day=i, completed=False))
        await repo.session.commit()
        days = await repo.list()
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
