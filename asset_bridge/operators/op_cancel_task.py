import bpy
from ..helpers.main_thread import run_in_main_thread
from bpy.props import StringProperty
from bpy.types import Operator

from ..settings import AssetTask, get_ab_settings
from ..helpers.btypes import BOperator


@BOperator("asset_bridge")
class AB_OT_cancel_task(Operator):
    """Cancel an Asset Bridge task"""

    name: StringProperty()

    def execute(self, context):
        if not self.name:
            raise ValueError("No task name specified")

        ab = get_ab_settings(context)
        task: AssetTask = ab.tasks[self.name]
        if not task.progress:
            raise ValueError(f"Task '{self.name}' has no progress")

        task.cancel(remove=False)
        return {"FINISHED"}


def cancel_task(name: str, main_thread=False):
    if main_thread:
        run_in_main_thread(cancel_task, (name, False))
    else:
        bpy.ops.asset_bridge.cancel_task("INVOKE_DEFAULT", name=name)