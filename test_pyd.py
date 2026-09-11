from pydantic import BaseModel
from enum import Enum

class ListingType(str, Enum):
    buy = "buy"
    rent = "rent"

class Prop(BaseModel):
    listing_type: ListingType

p = Prop(listing_type="rent")
print(repr(p.model_dump()["listing_type"]))
