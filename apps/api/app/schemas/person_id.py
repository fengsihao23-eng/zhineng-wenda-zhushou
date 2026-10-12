from typing import Annotated
from uuid import UUID
from pydantic import StringConstraints

# UUIDs remain an API compatibility bridge; new platform IDs travel as strings.
PersonReference = UUID | Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]{7,9}$")]
