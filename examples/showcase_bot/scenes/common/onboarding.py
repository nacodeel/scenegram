from __future__ import annotations

from dataclasses import dataclass

from aiogram.utils.formatting import Bold, as_key_value, as_list

from scenegram import Button, FormField, FormScene, Navigate, inline_menu


@dataclass(slots=True)
class OnboardingResult:
    name: str
    email: str
    goal: str


class OnboardingScene(FormScene, state="common.onboarding"):
    __abstract__ = False
    home_scene = "common.start"
    result_model = OnboardingResult
    use_confirm_step = True
    fields = (
        FormField(name="name", prompt="Как вас зовут?", summary_label="Name"),
        FormField(
            name="email",
            prompt="Какой e-mail использовать для связи?",
            validator="validate_email",
            summary_label="Email",
        ),
        FormField(
            name="goal",
            prompt="Какой сценарий хотите автоматизировать первым?",
            summary_label="Goal",
        ),
    )

    async def validate_email(self, value: str) -> str | None:
        if "@" not in value:
            return "Нужен корректный e-mail."
        return None

    async def on_form_submit(self, event, result: OnboardingResult) -> None:
        await self.show(
            event,
            as_list(
                Bold("Анкета заполнена"),
                as_key_value("Name", result.name),
                as_key_value("Email", result.email),
                as_key_value("Goal", result.goal),
                sep="\n\n",
            ),
            reply_markup=inline_menu(
                [[Button(text="🏠 Вернуться в меню", callback_data=Navigate.home("common.start"))]]
            ),
        )
