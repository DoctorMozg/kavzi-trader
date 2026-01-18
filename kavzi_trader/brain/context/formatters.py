from pydantic import BaseModel


def dump_json(model: BaseModel) -> str:
    return model.model_dump_json()


def dump_optional_json(model: BaseModel | None) -> str | None:
    if model is None:
        return None
    return model.model_dump_json()
