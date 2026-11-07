from datetime import date
from typing import Self

from pydantic import BaseModel, Field, model_validator


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
    target_reps_min: int | None = Field(default=None, ge=1, le=100)
    target_reps_max: int | None = Field(default=None, ge=1, le=100)
    rpe: float | None = Field(default=None, ge=1, le=10)
    notes: str = ""
    pain: bool = False
    technique_concern: bool = False

    @model_validator(mode="after")
    def validate_optional_rep_range(self) -> Self:
        if (self.target_reps_min is None) != (self.target_reps_max is None):
            raise ValueError("Both target rep limits must be set together")
        if self.target_reps_min is not None and self.target_reps_min > self.target_reps_max:
            raise ValueError("Minimum target reps cannot exceed maximum target reps")
        return self


class StrengthWorkoutInput(BaseModel):
    workout_date: date
    session_name: str = Field(min_length=1, max_length=100)
    notes: str = ""
    exercises: list[StrengthSetInput] = Field(min_length=1)


class StrengthSetLogInput(BaseModel):
    reps: int = Field(ge=1, le=100)
    weight_kg: float = Field(ge=0, le=1000)
    rpe: float | None = Field(default=None, ge=1, le=10)
    pain: bool = False
    technique_concern: bool = False
    notes: str = ""


class StrengthExerciseLogInput(BaseModel):
    exercise_name: str = Field(min_length=1, max_length=100)
    target_reps_min: int | None = Field(default=None, ge=1, le=100)
    target_reps_max: int | None = Field(default=None, ge=1, le=100)
    sets: list[StrengthSetLogInput] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def validate_rep_range(self) -> Self:
        if (self.target_reps_min is None) != (self.target_reps_max is None):
            raise ValueError("Both target rep limits must be set together")
        if self.target_reps_min is not None and self.target_reps_min > self.target_reps_max:
            raise ValueError("Minimum target reps cannot exceed maximum target reps")
        return self


class StrengthWorkoutLogInput(BaseModel):
    workout_date: date
    session_name: str = Field(min_length=1, max_length=100)
    notes: str = ""
    exercises: list[StrengthExerciseLogInput] = Field(min_length=1)


class RoutineExerciseInput(BaseModel):
    exercise_name: str = Field(min_length=1, max_length=100)
    sets: int = Field(ge=1, le=30)
    target_reps_min: int = Field(ge=1, le=100)
    target_reps_max: int = Field(ge=1, le=100)
    starting_weight_kg: float | None = Field(default=None, ge=0, le=1000)
    notes: str = ""

    @model_validator(mode="after")
    def validate_rep_range(self) -> Self:
        if self.target_reps_min > self.target_reps_max:
            raise ValueError("Minimum target reps cannot exceed maximum target reps")
        return self


class WorkoutRoutineInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    notes: str = ""
    exercises: list[RoutineExerciseInput] = Field(min_length=1)


class RunningWorkoutInput(BaseModel):
    workout_date: date
    run_type: str
    distance_km: float = Field(gt=0, le=500)
    duration_minutes: float = Field(gt=0, le=3000)
    rpe: int | None = Field(default=None, ge=1, le=10)
    notes: str = ""
    pain: bool = False