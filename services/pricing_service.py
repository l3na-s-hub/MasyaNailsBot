from typing import Dict, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import Service, ServiceParameter


class PricingService:
    """Расчёт итоговой длительности и цены на основе выбранных параметров"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_service_by_code(self, code: str) -> Service | None:
        result = await self.session.execute(
            select(Service).where(Service.code == code, Service.is_active == True)
        )
        return result.scalar_one_or_none()

    async def get_parameters_for_step(self, service_id: int, step_code: str) -> list[ServiceParameter]:
        result = await self.session.execute(
            select(ServiceParameter)
            .where(
                ServiceParameter.service_id == service_id,
                ServiceParameter.step_code == step_code,
                ServiceParameter.is_active == True
            )
            .order_by(ServiceParameter.sort_order)
        )
        return list(result.scalars().all())

    async def get_all_steps_for_service(self, service_id: int) -> list[str]:
        """Возвращает упорядоченный список step_code для услуги"""
        result = await self.session.execute(
            select(ServiceParameter.step_code)
            .where(ServiceParameter.service_id == service_id, ServiceParameter.is_active == True)
            .distinct()
            .order_by(ServiceParameter.sort_order)  # приблизительно
        )
        # Жёсткий порядок для ноготочков
        order = ["has_coating", "nails_condition", "length", "design", "claws", "communication"]
        existing = {row[0] for row in result.all()}
        return [s for s in order if s in existing]

    async def calculate(
        self,
        service: Service,
        selected_params: Dict[str, str]
    ) -> Tuple[int, float]:
        """
        Возвращает (total_duration_minutes, total_price)
        """
        duration = service.base_duration_minutes
        price = service.base_price

        if not selected_params:
            return duration, price

        result = await self.session.execute(
            select(ServiceParameter).where(
                ServiceParameter.service_id == service.id,
                ServiceParameter.is_active == True
            )
        )
        all_params = result.scalars().all()
        param_map = {(p.step_code, p.option_code): p for p in all_params}

        for step, option in selected_params.items():
            key = (step, option)
            if key in param_map:
                p = param_map[key]
                duration += p.duration_modifier
                price += p.price_modifier

        # Минимальные значения
        duration = max(duration, 30)
        price = max(price, 0)

        return duration, price

    async def get_option(self, service_id: int, step_code: str, option_code: str) -> ServiceParameter | None:
        result = await self.session.execute(
            select(ServiceParameter).where(
                ServiceParameter.service_id == service_id,
                ServiceParameter.step_code == step_code,
                ServiceParameter.option_code == option_code
            )
        )
        return result.scalar_one_or_none()
