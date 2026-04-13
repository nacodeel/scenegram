from __future__ import annotations

from scenegram import AppScene, DeepLinkMenuScene, SceneModule, deep_link_handler, deep_link_scene


async def module_deep_link(scene, event, context):
    return None


SCENEGRAM_MODULE = SceneModule(
    name="fixtures.deep-links",
    package_name=__name__,
    deep_links=(
        deep_link_handler("fixture.module", module_deep_link),
    ),
)


class DeepLinkStartScene(DeepLinkMenuScene, state="deep.start"):
    __abstract__ = False
    menu_text = "Deep links start"


class DeepLinkTargetScene(AppScene, state="deep.target"):
    __abstract__ = False
    deep_links = (
        deep_link_scene(
            "fixture.scene",
            payload_key="item_id",
            back_target="deep.start",
        ),
    )
