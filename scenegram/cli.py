from __future__ import annotations

import argparse
from pathlib import Path
from textwrap import dedent

from .base import AppScene
from .bootstrap import (
    discover_callback_prefixes,
    discover_scene_descriptors,
    discover_scene_modules,
)


def render_scene_template(
    *,
    state: str,
    class_name: str,
    home_scene: str | None = None,
) -> str:
    lines = [
        "from __future__ import annotations",
        "",
        "from aiogram.utils.formatting import Bold, as_list",
        "",
        "from scenegram import MenuScene",
        "",
        "",
        f'class {class_name}(MenuScene, state="{state}"):',
        "    __abstract__ = False",
    ]
    if home_scene:
        lines.append(f'    home_scene = "{home_scene}"')
    lines.extend(
        [
            "    menu_text = as_list(",
            f'        Bold("{class_name}"),',
            '        "Опишите содержимое сцены и добавьте кнопки.",',
            '        sep="\\n\\n",',
            "    )",
        ]
    )
    return dedent(
        "\n".join(lines)
    )


def render_module_template(
    *,
    name: str,
    package_name: str,
    target_state: str,
    menu_target: str,
) -> str:
    return dedent(
        f"""\
        from __future__ import annotations

        from scenegram import MenuContribution, SceneModule


        SCENEGRAM_MODULE = SceneModule(
            name="{name}",
            package_name="{package_name}",
            title="{name.title()}",
            description="Portable scene module",
            menu_entries=(
                MenuContribution(
                    target_state="{menu_target}",
                    target_scene="{target_state}",
                    text="{name.title()}",
                ),
            ),
        )
        """
    )


def check_packages(*packages: str) -> str:
    package_name = packages if len(packages) != 1 else packages[0]
    modules = discover_scene_modules(package_name)
    descriptors = discover_scene_descriptors(package_name, AppScene, modules=modules)
    prefixes = discover_callback_prefixes(package_name)
    lines = [
        "scenegram check ok",
        f"packages: {', '.join(packages)}",
        f"modules: {len(modules)}",
        f"scenes: {len(descriptors)}",
        f"callback_prefixes: {len(prefixes)}",
    ]
    for descriptor in descriptors:
        lines.append(f"- {descriptor.state} roles={','.join(sorted(descriptor.roles))}")
    return "\n".join(lines)


def _write_or_print(content: str, output: str | None) -> None:
    if output is None:
        print(content)
        return
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scenegram")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser(
        "check",
        help="Validate scene package discovery and callback prefixes",
    )
    check.add_argument("packages", nargs="+")

    generate = subparsers.add_parser("generate", help="Generate scene or module templates")
    generate_subparsers = generate.add_subparsers(dest="kind", required=True)

    scene = generate_subparsers.add_parser("scene", help="Generate a scene template")
    scene.add_argument("--state", required=True)
    scene.add_argument("--class-name", required=True)
    scene.add_argument("--home-scene")
    scene.add_argument("--output")

    module = generate_subparsers.add_parser("module", help="Generate a module manifest template")
    module.add_argument("--name", required=True)
    module.add_argument("--package-name", required=True)
    module.add_argument("--target-state", required=True)
    module.add_argument("--menu-target", required=True)
    module.add_argument("--output")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "check":
        print(check_packages(*args.packages))
        return 0

    if args.command == "generate" and args.kind == "scene":
        content = render_scene_template(
            state=args.state,
            class_name=args.class_name,
            home_scene=args.home_scene,
        )
        _write_or_print(content, args.output)
        return 0

    if args.command == "generate" and args.kind == "module":
        content = render_module_template(
            name=args.name,
            package_name=args.package_name,
            target_state=args.target_state,
            menu_target=args.menu_target,
        )
        _write_or_print(content, args.output)
        return 0

    parser.error("Unknown command")
    return 1


__all__ = [
    "build_parser",
    "check_packages",
    "main",
    "render_module_template",
    "render_scene_template",
]
