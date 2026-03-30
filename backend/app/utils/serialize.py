from typing import Any, Dict, List
from bson import ObjectId


def serialize_id(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    if "_id" in doc:
        doc["id"] = str(doc["_id"])
        doc.pop("_id", None)
    return doc


def serialize_list(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [serialize_id(item) for item in items]


def ensure_item_ids(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for item in items:
        if "id" not in item:
            item["id"] = str(ObjectId())
    return items
