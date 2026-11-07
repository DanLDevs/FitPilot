from datetime import date

from pydantic import BaseModel, Field


class ProfileInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    primary_goal: str
    experience_level: str
    training_days: int = Field(ge=1, le=7)
    strength_days: int = Field(ge=0, le=7)
    running_days: int = Field(ge=0, le=7)
    session_minutes: int = Field(ge=15, le=300)
    equipment: str = ""
    fitness_goals: str = ""
    existing_schedule: str = ""


class StrengthSetInput(BaseModel):
    exercise_name: str = Field(min_length=1, max_length=100)
    sets: int = Field(ge=1, le=20)
    reps: int = Field(ge=1, le=100)
    weight_kg: float = Field(ge=0, le=1000)
    rpe: float | None = Field(default=None, ge=1, le=10)
    notes: str = ""
    pain: bool = False


class StrengthWorkoutInput(BaseModel):
    workout_date: date
    session_name: str = Field(min_length=1, max_length=100)
    notes: str = ""
    exercises: list[StrengthSetInput] = Field(min_length=1)


class RunningWorkoutInput(BaseModel):
    workout_date: date
    run_type: str
    distance_km: float = Field(gt=0, le=500)
    duration_minutes: float = Field(gt=0, le=3000)
    rpe: int | None = Field(default=None, ge=1, le=10)
    notes: str = ""
    pain: bool = False