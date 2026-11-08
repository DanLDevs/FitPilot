from datetime import date
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from typing import Literal, Self

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
    weight_unit: Literal["kg", "lb"] = "kg"


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


class LiveSetInput(BaseModel):
    reps: int = Field(default=8, ge=1, le=100)
    weight_kg: float = Field(default=0, ge=0, le=1000)
    rpe: float | None = Field(default=None, ge=1, le=10)
    pain: bool = False
    technique_concern: bool = False
    notes: str = ""
    is_completed: bool = False


class LiveExerciseInput(BaseModel):
    exercise_key: str = Field(default_factory=lambda: uuid4().hex)
    exercise_name: str = Field(min_length=1, max_length=100)
    target_reps_min: int = Field(default=8, ge=1, le=100)
    target_reps_max: int = Field(default=12, ge=1, le=100)
    rest_seconds: int | None = Field(default=None, ge=0, le=3600)
    notes: str = ""
    sets: list[LiveSetInput] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def validate_rep_range(self):
        if self.target_reps_min > self.target_reps_max:
            raise ValueError("Minimum target reps cannot exceed maximum target reps")
        return self


class LiveWorkoutInput(BaseModel):
    workout_date: date
    session_name: str = Field(min_length=1, max_length=100)
    notes: str = ""
    default_rest_seconds: int = Field(default=90, ge=0, le=3600)
    auto_start_rest: bool = True
    exercises: list[LiveExerciseInput] = Field(default_factory=list, max_length=30)


class RoutineExerciseInput(BaseModel):
    exercise_name: str = Field(min_length=1, max_length=100)
    sets: int = Field(ge=1, le=30)
    target_reps_min: int = Field(ge=1, le=100)
    target_reps_max: int = Field(ge=1, le=100)
    starting_weight_kg: float | None = Field(default=None, ge=0, le=1000)
    rest_seconds: int | None = Field(default=None, ge=0, le=3600)
    notes: str = ""

    @model_validator(mode="after")
    def validate_rep_range(self):
        if self.target_reps_min > self.target_reps_max:
            raise ValueError("Minimum target reps cannot exceed maximum target reps")
        return self


class WorkoutRoutineInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    notes: str = ""
    default_rest_seconds: int = Field(default=90, ge=0, le=3600)
    auto_start_rest: bool = True
    exercises: list[RoutineExerciseInput] = Field(min_length=1, max_length=30)


RUN_TYPES = ("Easy", "Tempo", "Interval", "Long Run", "Recovery", "Other")


class GeneratedExercise(BaseModel):
    exercise_name: str = Field(min_length=1, max_length=100)
    sets: int = Field(ge=1, le=30)
    target_reps_min: int = Field(ge=1, le=100)
    target_reps_max: int = Field(ge=1, le=100)
    rest_seconds: int | None = Field(default=None, ge=0, le=3600)
    notes: str = ""

    @model_validator(mode="after")
    def validate_rep_range(self):
        if self.target_reps_min > self.target_reps_max:
            raise ValueError("Minimum target reps cannot exceed maximum target reps")
        return self


class GeneratedDay(BaseModel):
    weekday: str = Field(default="", max_length=40)
    session_kind: str
    title: str = Field(min_length=1, max_length=100)
    notes: str = ""
    default_rest_seconds: int = Field(default=90, ge=0, le=3600)
    auto_start_rest: bool = True
    exercises: list[GeneratedExercise] = Field(default_factory=list, max_length=30)
    run_type: str | None = None
    distance_km: float | None = None
    duration_minutes: float | None = None

    @model_validator(mode="after")
    def validate_session(self):
        self.session_kind = self.session_kind.strip().lower()
        if self.run_type:
            match = next((item for item in RUN_TYPES if item.lower() == self.run_type.strip().lower()), None)
            self.run_type = match or self.run_type.strip()
        if self.session_kind == "strength":
            if not self.exercises:
                raise ValueError("Strength days need at least one exercise")
            self.run_type = None
            self.distance_km = None
            self.duration_minutes = None
            return self
        if self.session_kind != "running":
            raise ValueError("Each day must be a strength or running session")
        if self.run_type not in RUN_TYPES:
            raise ValueError("Running days need a supported run type")
        if self.distance_km is None or self.duration_minutes is None:
            raise ValueError("Running days need distance and duration")
        if not 0 < self.distance_km <= 500:
            raise ValueError("Running distance must be greater than 0 and at most 500 km")
        if not 0 < self.duration_minutes <= 3000:
            raise ValueError("Running duration must be greater than 0 and at most 3000 minutes")
        if self.exercises:
            raise ValueError("Running days cannot include exercises")
        return self


class GeneratedWeek(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    summary: str = ""
    days: list[GeneratedDay] = Field(min_length=1, max_length=7)


class RunningWorkoutInput(BaseModel):
    workout_date: date
    run_type: str
    distance_km: float = Field(gt=0, le=500)
    duration_minutes: float = Field(gt=0, le=3000)
    rpe: int | None = Field(default=None, ge=1, le=10)
    notes: str = ""
    pain: bool = False