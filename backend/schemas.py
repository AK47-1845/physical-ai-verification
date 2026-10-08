from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

Number = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=-100_000, le=100_000)]
Positive = Annotated[float, Field(strict=True, allow_inf_nan=False, gt=0, le=100_000)]
Fraction = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0, le=1)]
Identifier = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")]
Vector = Annotated[list[Number], Field(min_length=2, max_length=3)]
PathPoints = Annotated[list[Vector], Field(min_length=8, max_length=512)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)


class Provenance(StrictModel):
    source: str = Field(min_length=1, max_length=1024)
    license: str = Field(min_length=1, max_length=300)
    transforms: list[Annotated[str, Field(max_length=300)]] = Field(default_factory=list, max_length=20)
    source_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    attribution: str = Field(default="User-supplied source declaration", max_length=300)


class PerceptionEvidence(StrictModel):
    confidence: list[Fraction] = Field(min_length=8, max_length=512)
    corroborated: list[StrictBool] = Field(min_length=8, max_length=512)
    method: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def aligned(self) -> Self:
        if len(self.confidence) != len(self.corroborated):
            raise ValueError("Perception confidence and corroboration must align")
        return self


class Generation(StrictModel):
    generation: Annotated[StrictInt, Field(ge=0, le=100)]
    real_samples: Annotated[StrictInt, Field(ge=0, le=1_000_000_000)]
    synthetic_samples: Annotated[StrictInt, Field(ge=0, le=1_000_000_000)]
    diversity: Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0, le=100_000)]
    quality: Fraction

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if self.real_samples + self.synthetic_samples == 0:
            raise ValueError("A generation must contain samples")
        return self


class LineageEvidence(StrictModel):
    generations: list[Generation] = Field(min_length=1, max_length=30)
    metric_definition: str = Field(min_length=1, max_length=500)
    evidence_kind: Literal["synthetic", "measured"]

    @model_validator(mode="after")
    def ordered(self) -> Self:
        values = [entry.generation for entry in self.generations]
        if any(right <= left for left, right in zip(values, values[1:])):
            raise ValueError("Generation identifiers must be strictly increasing")
        return self


class ContactEvidence(StrictModel):
    normal_force_n: list[Annotated[Number, Field(ge=0)]] = Field(min_length=8, max_length=512)
    tangential_force_n: list[Annotated[Number, Field(ge=0)]] = Field(min_length=8, max_length=512)
    friction_coefficient: Annotated[float, Field(strict=True, ge=0, le=2, allow_inf_nan=False)]
    method: str = Field(min_length=1, max_length=300)


class Trace(StrictModel):
    schema_version: Literal["verification.trace/1"] = "verification.trace/1"
    name: str = Field(min_length=1, max_length=120)
    task: str = Field(min_length=1, max_length=120)
    embodiment_id: Identifier
    policy_version: str = Field(min_length=1, max_length=120)
    evidence_kind: Literal["synthetic", "recorded", "simulator"]
    reference_kind: Literal["commanded", "simulator", "ground_truth"]
    units: Literal["m", "abstract"]
    coordinate_frame: Identifier
    reference: PathPoints
    observed: PathPoints
    timestamps_s: list[Annotated[Number, Field(ge=0)]] | None = Field(default=None, min_length=8, max_length=512)
    probed: PathPoints | None = None
    probe_method: str | None = Field(default=None, min_length=1, max_length=300)
    rollouts: list[PathPoints] | None = Field(default=None, min_length=2, max_length=8)
    perception: PerceptionEvidence | None = None
    lineage: LineageEvidence | None = None
    contact: ContactEvidence | None = None
    provenance: Provenance

    @model_validator(mode="after")
    def compatible(self) -> Self:
        count = len(self.reference)
        dimension = len(self.reference[0])
        paths = [self.reference, self.observed]
        if self.probed is not None:
            if not self.probe_method:
                raise ValueError("A controlled-probe method is required")
            paths.append(self.probed)
        if self.rollouts:
            paths.extend(self.rollouts)
        if any(len(path) != count for path in paths):
            raise ValueError("All paths must have equal sample counts; implicit truncation is forbidden")
        if any(len(point) != dimension for path in paths for point in path):
            raise ValueError("All path points must have the same dimension")
        if self.timestamps_s is not None:
            if len(self.timestamps_s) != count:
                raise ValueError("Timestamps must align with path samples")
            if any(right - left < 0.000001 for left, right in zip(self.timestamps_s, self.timestamps_s[1:])):
                raise ValueError("Timestamps must increase by at least one microsecond")
        if self.perception and len(self.perception.confidence) != count:
            raise ValueError("Perception evidence must align with the trace")
        if self.contact:
            if len(self.contact.normal_force_n) != count or len(self.contact.tangential_force_n) != count:
                raise ValueError("Contact evidence must align with the trace")
        return self


class GateRule(StrictModel):
    metric: Identifier
    direction: Literal["upper", "lower"]
    pass_limit: Number
    review_limit: Number
    required: StrictBool = True

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.direction == "upper" and self.pass_limit > self.review_limit:
            raise ValueError("Upper gates require pass_limit <= review_limit")
        if self.direction == "lower" and self.pass_limit < self.review_limit:
            raise ValueError("Lower gates require pass_limit >= review_limit")
        return self


class GateProfile(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    version: Annotated[StrictInt, Field(ge=1, le=1_000_000)] = 1
    calibration: Literal["draft"] = "draft"
    coordinate_frame: Identifier = "task"
    units: Literal["m", "abstract"] = "m"
    dimension: Literal[2, 3] = 3
    workspace_lower: Vector = [-1.0, -1.0, 0.0]
    workspace_upper: Vector = [1.0, 1.0, 1.5]
    drift_breach_m: Positive = 0.06
    breach_run: Annotated[StrictInt, Field(ge=1, le=20)] = 3
    rules: list[GateRule] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if len(self.workspace_lower) != self.dimension or len(self.workspace_upper) != self.dimension:
            raise ValueError("Workspace bounds must match the profile dimension")
        if any(high <= low for low, high in zip(self.workspace_lower, self.workspace_upper)):
            raise ValueError("Workspace upper bounds must exceed lower bounds")
        if len({rule.metric for rule in self.rules}) != len(self.rules):
            raise ValueError("Duplicate gate metrics are forbidden")
        return self


class Embodiment(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    family: Literal["manipulator", "mobile", "humanoid", "other"]
    degrees_of_freedom: Annotated[StrictInt, Field(ge=1, le=100)]
    coordinate_frame: Identifier
    units: Literal["m", "abstract"] = "m"
    dimension: Literal[2, 3] = 3
    hardware_validated: Literal[False] = False
    description: str = Field(max_length=500)


class Telemetry(StrictModel):
    sequence: Annotated[StrictInt, Field(ge=0, le=2**53 - 1)]
    timestamp_ms: Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0)]
    position_m: Annotated[list[Number], Field(min_length=3, max_length=3)]
    velocity_m_s: Annotated[list[Number], Field(min_length=3, max_length=3)]
    sensor_agreement: Fraction
    emergency_stop: StrictBool = False

    @field_validator("timestamp_ms")
    @classmethod
    def bounded_timestamp(cls, value: float) -> float:
        if not math.isfinite(value) or value > 10**15:
            raise ValueError("Invalid timestamp")
        return value