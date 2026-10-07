from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional


@dataclass(frozen=True)
class MealSlot:
    date: date
    meal_type: str
    max_cooking_time: Optional[int] = None

    @property
    def slot_id(self) -> str:
        return f"{self.date.isoformat()}_{self.meal_type.lower()}"

    def to_dict(self) -> dict:
        return {
            "slot_id": self.slot_id,
            "date": self.date.isoformat(),
            "meal_type": self.meal_type.lower(),
            "max_cooking_time": self.max_cooking_time,
        }


def generate_meal_slots(
    start_date: date,
    days: int,
    meal_types: list[str],
    schedule: Optional[dict] = None,
) -> list[MealSlot]:

    if days <= 0:
        raise ValueError("days must be greater than 0")

    if not meal_types:
        raise ValueError("meal_types cannot be empty")

    schedule = schedule or {}

    slots = []

    for day_offset in range(days):
        current_date = start_date + timedelta(days=day_offset)

        day_schedule = schedule.get(current_date.isoformat(), {})

        for meal_type in meal_types:

            meal_schedule = day_schedule.get(meal_type, {})

            max_time = meal_schedule.get("max_cooking_time")

            slots.append(
                MealSlot(
                    date=current_date,
                    meal_type=meal_type.lower(),
                    max_cooking_time=max_time,
                )
            )

    return slots