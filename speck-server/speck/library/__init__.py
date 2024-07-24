from typing import List, get_type_hints, Callable, Dict
from pydantic import BaseModel, Field, model_validator


class SpeckFunction(BaseModel):
    name: str
    description: str = Field(default=None)
    func: Callable
    parameters: List[dict] = Field(default_factory=list)

    @model_validator(mode='after')
    def set_description(cls, values):
        if not values.description:
            values.description = values.func.__doc__
        return values

    @model_validator(mode='after')
    def set_parameters(cls, values):
        func = values.func
        if func:
            values.parameters = [
                {'name': k, 'type': str(v)} for k, v in get_type_hints(func).items()
            ]
        return values


class SpeckLibrary(BaseModel):
    functions: Dict[str, SpeckFunction]

from . import usps_hold_mail

speck_library = SpeckLibrary(
    functions={
        'usps_hold_mail': usps_hold_mail.usps_hold_mail_function
    }
)
