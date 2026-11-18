from typing import Annotated

from fastapi import Path

WorkspaceID = Annotated[int, Path(gt=0, description="Workspace ID")]
MemberUserID = Annotated[int, Path(gt=0, description="Member User ID")]
ProjectID = Annotated[int, Path(gt=0, description="Project ID")]
TaskID = Annotated[int, Path(gt=0, description="Task ID")]
LabelID = Annotated[int, Path(gt=0, description="Label ID")]
CommentID = Annotated[int, Path(gt=0, description="Comment ID")]
