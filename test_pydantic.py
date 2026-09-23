from pydantic import BaseModel
from typing import List, Optional, Union

class PropertyImageSync(BaseModel):
    id: Optional[Union[int, str]] = None
    image_url: str
    file_key: Optional[str] = None
    is_primary: bool = False
    sort_order: int = 0
    alt_text: Optional[str] = None

class PropertyUpdate(BaseModel):
    images: Optional[List[PropertyImageSync]] = None

data = {
    "images": [
        {"id": 1, "image_url": "url1", "is_primary": False},
        {"id": 2, "image_url": "url2", "is_primary": True}
    ]
}

model = PropertyUpdate(**data)
dump = model.model_dump(exclude_unset=True)
print(dump)
