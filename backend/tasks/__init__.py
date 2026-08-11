"""Task plugins for Graph of Thoughts — engine stays task-agnostic."""

__all__ = ["BaseTask", "SortingTask"]


def __getattr__(name: str):
    if name == "BaseTask":
        from tasks.base_task import BaseTask

        return BaseTask
    if name == "SortingTask":
        from tasks.sorting_task import SortingTask

        return SortingTask
    raise AttributeError(name)
