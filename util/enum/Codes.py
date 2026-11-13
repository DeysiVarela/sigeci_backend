from enum import Enum

class Codes(Enum):
    NOT_PERMISSION = "0000"
    SUCCESS = "0001"
    ERROR = "0002"
    UNAUTHORIZED = "0003"
    NOT_FOUND = "0004"