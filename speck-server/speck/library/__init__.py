from typing import Any, List, Optional, get_type_hints, Callable, Dict
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


class FunctionResult(BaseModel):
    success: bool
    success_message: Optional[str] = None
    error_message: Optional[str] = None


class SpeckLibrary(BaseModel):
    functions: Dict[str, SpeckFunction]

    def execute_function(self, function_name: str, arguments: Dict[str, Any]) -> FunctionResult:
        try:
            success_message = self.functions[function_name].func(**arguments)
            return FunctionResult(success=True, success_message=success_message)
        except Exception as e:
            return FunctionResult(success=False, error_message=str(e))

# TODO: Add a decorator to the SpeckFunction class to make it easy to add a function to the library
from . import usps_hold_mail

speck_library = SpeckLibrary(
    functions={
        'usps_hold_mail': usps_hold_mail.usps_hold_mail_function
    }
)
