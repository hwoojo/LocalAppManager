from localapp_manager.identifiers import generate_app_id, slugify


def test_slugify_name() -> None:
    assert slugify("My Useful_App 2!") == "my-useful-app-2"


def test_non_ascii_name_has_safe_fallback() -> None:
    assert slugify("내 앱") == "app"


def test_duplicate_id_uses_first_available_suffix() -> None:
    existing = {"sample", "sample-2", "sample-4"}
    assert generate_app_id("Sample", existing) == "sample-3"

