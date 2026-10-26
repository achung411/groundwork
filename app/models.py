"""Versioned, deliberately small contract shared with the extraction skill."""

from datetime import date
from decimal import Decimal
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Evidence(ContractModel):
    page: Annotated[StrictInt, Field(ge=1)]
    section: Annotated[str, Field(min_length=1, max_length=300)]
    quote: Annotated[str, Field(min_length=1, max_length=6000)]


class RentValue(ContractModel):
    amount: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
    currency: Literal["USD"]

    @field_validator("amount", mode="before")
    @classmethod
    def reject_boolean(cls, value):
        if isinstance(value, bool):
            raise ValueError("Rent amount must be a dollar amount, not true/false")
        return value


class DueValue(ContractModel):
    day: Annotated[StrictInt, Field(ge=1, le=31)]


class GraceValue(ContractModel):
    days: Annotated[StrictInt, Field(ge=0, le=365)]


class DateValue(ContractModel):
    date: date

    @field_validator("date", mode="before")
    @classmethod
    def iso_date(cls, value):
        return require_iso_date(value)


class OptionValue(ContractModel):
    options_count: Annotated[StrictInt, Field(ge=1, le=10)]
    term_months: Annotated[StrictInt, Field(ge=1, le=1200)]
    notice_earliest_months: Annotated[StrictInt, Field(ge=0, le=120)]
    notice_latest_months: Annotated[StrictInt, Field(ge=0, le=120)]

    @model_validator(mode="after")
    def window_order(self):
        if self.notice_earliest_months < self.notice_latest_months:
            raise ValueError("Earliest notice must be at least as many months before expiration as latest notice")
        return self


def require_iso_date(value):
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("Use a calendar date in YYYY-MM-DD format")
    return date.fromisoformat(value)


class FactBase(ContractModel):
    effective_from: Optional[date]
    effective_to: Optional[date] = None
    status: Literal["proposed"]
    uncertainty: Optional[Annotated[str, Field(min_length=1, max_length=2000)]] = None
    evidence: Annotated[List[Evidence], Field(min_length=1, max_length=10)]

    @field_validator("effective_from", "effective_to", mode="before")
    @classmethod
    def iso_date(cls, value):
        return None if value is None else require_iso_date(value)

    @model_validator(mode="after")
    def dates(self):
        if self.effective_from is None and not self.uncertainty:
            raise ValueError("An unknown effective date requires an uncertainty explanation")
        if self.effective_to and self.effective_from and self.effective_to < self.effective_from:
            raise ValueError("Effective end cannot precede effective start")
        return self


class RentFact(FactBase):
    fact_type: Literal["monthly_base_rent"]
    value: RentValue


class DueFact(FactBase):
    fact_type: Literal["rent_due_day"]
    value: DueValue


class GraceFact(FactBase):
    fact_type: Literal["grace_period"]
    value: GraceValue


class StartFact(FactBase):
    fact_type: Literal["lease_start"]
    value: DateValue


class EndFact(FactBase):
    fact_type: Literal["lease_end"]
    value: DateValue


class OptionFact(FactBase):
    fact_type: Literal["extension_option"]
    value: OptionValue


Fact = Annotated[Union[RentFact, DueFact, GraceFact, StartFact, EndFact, OptionFact], Field(discriminator="fact_type")]


class ExtractionProposal(ContractModel):
    schema_version: Literal["1.0"]
    document_filename: Annotated[str, Field(min_length=1, max_length=255)]
    facts: Annotated[List[Fact], Field(min_length=1, max_length=50)]
