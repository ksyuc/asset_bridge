import os
from time import sleep
from typing import Callable
from threading import Thread

import bpy
from bpy.types import Object, Context, Material, Collection, MaterialSlot
from mathutils import Vector as V

from ..api import get_asset_lists
from .library import get_dir_size
from .process import format_traceback
from ..settings import get_ab_settings, get_asset_settings
from .main_thread import force_ui_update, run_in_main_thread
from ..apis.asset_types import Asset
from ..apis.asset_utils import HDRI
from ..operators.op_report_message import report_message


def download_asset(
        context: Context,
        asset: Asset,
        draw: bool = True,
        location: V = V(),
) -> str:
    """Download a given asset in the background while managing errors, and drawing the progress in the UI.
    It returns the name of the task that tracks the progress of the download. The reason it only returns the name
    instead of the task as well is because Blender moves references to objects around in memory quite a lot,
    so keeping direct references to those objects will result in problems.

    Args:
        context (Context): The blender context
        asset (Asset): An asset bridge asset instance
        draw (bool, optional): Draw the progress of the download in the UI. Defaults to True.
        draw_location (V, optional): The 3D coordinates to draw the progress widget at. Defaults to V().

    Returns:
        str: The name of the download task.
    """

    ab = get_ab_settings(context)
    all_assets = get_asset_lists().all_assets
    asset_list_item = asset.list_item

    # Handle if the asset is not in the list. Could happen if list is still loading for some reason, but is unlikely
    if not asset_list_item:
        report_message(
            f"Could not find asset {asset_list_item.label} in the asset list (Number of assets: {len(all_assets)})",
            "ERROR",
        )
        task = ab.new_task()
        task.cancel(remove=False)
        return task.name

    elif message := asset_list_item.poll():
        report_message(message, "ERROR")
        task = ab.new_task()
        task.cancel(remove=False)
        return task.name

    elif asset.is_downloaded and not ab.reload_asset:
        task = ab.new_task()
        task.finish(remove=False)
        return task.name

    ab = get_ab_settings(context)
    max_size = asset.get_download_size()
    task = ab.new_task()
    task.new_progress(max_size)
    task_name = task.name

    if draw:
        # Run the draw operator
        bpy.ops.asset_bridge.draw_import_progress("INVOKE_DEFAULT", task_name=task.name, location=location)

    def download():

        # Delete existing files
        if asset.list_item.type == HDRI:
            # We need to sleep here in to allow the blender UI to reload the hdri file if it is in cycles rendered view.
            # Otherwise the file is deleted first, and cycles loads in as a pink texture, until it is reloaded.
            # This might need to be longer on lower end hardware, but it's a pretty niche bug,
            # that doesn't have a serious impact.
            sleep(.05)
            i = 0
            while True and i < 10:
                for file in asset.get_files():
                    try:
                        os.remove(file)
                    except PermissionError:
                        sleep(.05)
                        break
                else:
                    break
                i += 1
        else:
            # For the other asset types, it's not necessary
            for file in asset.get_files():
                os.remove(file)

        def check_progress():
            """Check to total file size of the downloading files, and update the progress accordingly"""
            # Blender moves memory around a lot so it's best to get a new reference to the task each time.
            # Otherwise it causes errors when importing multiple assets at once.
            task = ab.tasks.get(task_name)
            if not task or task.finished:
                return None
            if task.progress:
                orig_progress = task.progress.progress
                if (size := get_dir_size(asset.download_dir)) != orig_progress:
                    task.progress.progress = size
                    force_ui_update(area_types="VIEW_3D")
                return .01
            return None

        # Download the asset
        bpy.app.timers.register(check_progress)
        try:
            asset.download_asset()
        except Exception as e:
            report_message(
                f"Error downloading asset {asset.idname}:\n{format_traceback(e)}",
                severity="ERROR",
                main_thread=True,
            )

        task = ab.tasks[task_name]
        force_ui_update(area_types="VIEW_3D")
        run_in_main_thread(task.finish, kwargs={"remove": False})

    thread = Thread(target=download)
    thread.start()

    return task.name


def import_asset(context: Context, asset: Asset, location: V = V(), material_slot: MaterialSlot = None):
    """Import an asset while handling errors, and properties necessary for Asset Bridge to work properly.
    This modifies blend data, so it needs to be run in the main thread."""
    asset_list_item = asset.list_item
    try:
        imported = asset.import_asset(context)

        def update_settings(data_block):
            settings = get_asset_settings(data_block)
            settings.is_asset_bridge = True
            settings.idname = asset_list_item.idname
            settings.quality_level = asset.quality_level

        if not isinstance(imported, Collection):
            update_settings(imported)

        if isinstance(imported, Material):
            if material_slot:
                material_slot.material = imported
        elif isinstance(imported, Object):
            imported.location += location
        elif isinstance(imported, Collection):
            for obj in imported.objects:
                update_settings(obj)
                obj.location += location
    except Exception as e:
        # This is needed so that the errors are shown to the user.
        report_message(f"Error importing asset {asset.idname}:\n{format_traceback(e)}", severity="ERROR")


def download_and_import_asset(
        context: Context,
        asset: Asset,
        material_slot: MaterialSlot = None,
        draw: bool = True,
        location: V = V(),
        on_completion: Callable = None,
        on_cancel: Callable = None,
):

    ab = get_ab_settings(context)
    task_name = download_asset(context, asset, draw, location)

    def check_download():
        if ab.tasks[task_name].cancelled:
            if on_cancel:
                on_cancel()
            return
        elif ab.tasks[task_name].finished:
            import_asset(context, asset, location, material_slot)
            if on_completion:
                on_completion()
            return
        return .1

    bpy.app.timers.register(check_download, first_interval=.1)