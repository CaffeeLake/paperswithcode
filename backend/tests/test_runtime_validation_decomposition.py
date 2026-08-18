import json
from itertools import count

import pytest

from backend.services import openrouter_budget_service
from backend.services import runtime_validation
from backend.tests.test_deployment_runtime import deployed_settings, make_bundle
from deploy.release import profile_features


@pytest.fixture(autouse=True)
def _avoid_live_openrouter_guardrail(monkeypatch):
    monkeypatch.setattr(
        openrouter_budget_service,
        "validate_openrouter_guardrail",
        lambda _settings: None,
    )


@pytest.fixture
def settings_factory(tmp_path):
    sequence = count()

    def build(environment):
        root = tmp_path / f"{environment}-{next(sequence)}"
        release = make_bundle(root, chat=environment == "staging")
        settings = deployed_settings(root, release, environment)
        return settings, release

    return build


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_deployment_identity_isolated_from_auth(settings_factory, environment):
    settings, _release = settings_factory(environment)
    settings.jwt_secret = ""

    runtime_validation.validate_deployment_identity(settings)

    settings.environment = "preview"
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_deployment_identity(settings)
    assert str(exc_info.value) == "PWC_ENVIRONMENT must be production or staging"


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_auth_configuration_isolated_from_storage(settings_factory, environment):
    settings, _release = settings_factory(environment)
    settings.runtime_data_dir = "./invalid-runtime"

    runtime_validation.validate_auth_configuration(settings)

    settings.jwt_secret = ""
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_auth_configuration(settings)
    assert str(exc_info.value) == "PWC_JWT_SECRET is required"


def test_runtime_storage_isolated_from_auth(settings_factory):
    settings, _release = settings_factory("production")
    settings.jwt_secret = ""

    runtime_validation.validate_runtime_storage(settings)

    settings.runtime_data_dir = "./invalid-runtime"
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_runtime_storage(settings)
    assert str(exc_info.value) == (
        "PWC_RUNTIME_DATA_DIR must be absolute in deployed environments"
    )


def test_codex_jobs_configuration_isolated_from_auth(settings_factory):
    settings, _release = settings_factory("staging")
    settings.jwt_secret = ""

    runtime_validation.validate_codex_jobs_configuration(settings)

    settings.codex_jobs_api_url = "https://paperswithcode.co/api/v1"
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_codex_jobs_configuration(settings)
    assert str(exc_info.value) == (
        "staging Codex jobs must target https://staging.paperswithcode.co/api/v1"
    )


def test_scheduled_curation_requires_digest_pinned_worker_image(settings_factory):
    settings, _release = settings_factory("production")
    settings.codex_curation_scheduler_enabled = True
    settings.codex_curation_direct_apply_enabled = True
    settings.codex_curation_trace_upload_enabled = True
    settings.codex_curation_trace_hf_bucket_id = "example/private-traces"
    settings.codex_jobs_image = "ghcr.io/example/curator:latest"

    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_codex_jobs_configuration(settings)

    assert str(exc_info.value) == (
        "scheduled paper curation requires an immutable curator image"
    )


def test_chat_runtime_descriptor_classifies_enabled_dormant_and_legacy(
    settings_factory,
):
    enabled, _release = settings_factory("staging")
    assert runtime_validation.validate_chat_runtime_descriptor(enabled) is True

    dormant, _release = settings_factory("production")
    assert dormant.chat_default_backend == "modal_cli"
    assert runtime_validation.validate_chat_runtime_descriptor(dormant) is False

    prepared, _release = settings_factory("production")
    prepared.chat_persistent_worker_enabled = True
    assert runtime_validation.validate_chat_runtime_descriptor(prepared) is True

    legacy, _release = settings_factory("production")
    legacy.chat_default_backend = "local_mcp"
    legacy.chat_modal_image_version = ""
    legacy.chat_pwc_cli_version = ""
    legacy.chat_worker_contract_version = ""
    legacy.chat_system_prompt_sha256 = ""
    assert runtime_validation.validate_chat_runtime_descriptor(legacy) is False


def test_chat_runtime_descriptor_rejects_partial_and_armed_legacy_states(
    settings_factory,
):
    partial, _release = settings_factory("production")
    partial.chat_pwc_cli_version = ""
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_chat_runtime_descriptor(partial)
    assert str(exc_info.value) == (
        "disabled production contains an active or incomplete chat runtime descriptor"
    )

    legacy, _release = settings_factory("production")
    legacy.chat_default_backend = "local_mcp"
    legacy.chat_modal_image_version = ""
    legacy.chat_pwc_cli_version = ""
    legacy.chat_worker_contract_version = ""
    legacy.chat_system_prompt_sha256 = ""
    legacy.chat_title_generation_enabled = True
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_chat_runtime_descriptor(legacy)
    assert str(exc_info.value) == (
        "legacy production cannot contain armed chat preparation"
    )


def test_chat_provider_policy_isolated_from_capacity(settings_factory):
    settings, _release = settings_factory("staging")
    settings.chat_max_concurrency = 999

    runtime_validation.validate_chat_provider_policy(settings)

    settings.hf_oauth_credential_secret = ""
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_chat_provider_policy(settings)
    assert str(exc_info.value) == (
        "enabled chat requires the Hugging Face OAuth authentication path"
    )


def test_environment_policy_isolated_from_storage(settings_factory):
    settings, _release = settings_factory("production")
    settings.runtime_data_dir = "./invalid-runtime"

    runtime_validation.validate_environment_policy(settings)

    settings.catalog_mutations_enabled = False
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_environment_policy(settings)
    assert str(exc_info.value) == (
        "production catalog mutations and CRON must remain enabled"
    )


def test_chat_provider_policy_accepts_isolated_production_openrouter(
    settings_factory,
):
    settings, _release = settings_factory("production")
    settings.chat_gateway_url = (
        "https://chat-gateway.paperswithcode.co/api/internal/chat-gateway"
    )

    runtime_validation.validate_chat_provider_policy(settings)


def test_chat_provider_policy_rejects_empty_preferred_provider_order(
    settings_factory,
):
    settings, _release = settings_factory("staging")
    settings.chat_openrouter_routing_enabled = True
    settings.chat_openrouter_routing_policy = "preferred_provider"
    settings.chat_openrouter_preferred_providers = ""

    with pytest.raises(RuntimeError, match="requires valid provider slugs"):
        runtime_validation.validate_chat_provider_policy(settings)


def test_chat_capacity_and_spend_policy_isolated_from_provider(settings_factory):
    settings, _release = settings_factory("staging")
    settings.hf_oauth_credential_secret = ""

    runtime_validation.validate_chat_capacity_and_spend_policy(settings)

    settings.chat_sandbox_warning_microusd = 1
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_chat_capacity_and_spend_policy(settings)
    assert str(exc_info.value) == (
        "sandbox spend policy must be $75/$100/$250 with no environment cap"
    )


def test_chat_descriptor_owns_immutable_runtime_identity(settings_factory):
    settings, _release = settings_factory("staging")
    settings.chat_workspace_snapshots_enabled = True

    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_chat_runtime_descriptor(settings)
    assert str(exc_info.value) == "directory snapshots must remain disabled"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "chat_gateway_url",
            "https://paperswithcode.co/api/internal/chat-gateway",
            "chat gateway must use chat-gateway-staging.paperswithcode.co",
        ),
        (
            "chat_openrouter_api_key",
            "",
            "server-funded OpenRouter chat requires an OpenRouter key",
        ),
    ],
)
def test_chat_provider_policy_owns_gateway_and_openrouter(
    settings_factory, field, value, message
):
    settings, _release = settings_factory("staging")
    setattr(settings, field, value)

    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_chat_provider_policy(settings)
    assert str(exc_info.value) == message


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "chat_openrouter_api_key",
            "",
            "an OpenRouter title credential is required",
        ),
        (
            "chat_sandbox_cpu_limit",
            0.5,
            "chat CPU limit is below its request",
        ),
        (
            "chat_persistent_worker_enabled",
            False,
            "blank pool requires persistent workers",
        ),
    ],
)
def test_chat_capacity_policy_owns_title_resources_and_pool(
    settings_factory, field, value, message
):
    settings, _release = settings_factory("staging")
    setattr(settings, field, value)

    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_chat_capacity_and_spend_policy(settings)
    assert str(exc_info.value) == message


def test_runtime_finishes_local_chat_policy_before_openrouter_guardrail(
    settings_factory, monkeypatch
):
    settings, _release = settings_factory("staging")
    calls = []

    def provider(_settings, *, include_openrouter):
        assert include_openrouter is False
        calls.append("provider")

    monkeypatch.setattr(runtime_validation, "validate_chat_provider_policy", provider)
    monkeypatch.setattr(
        runtime_validation,
        "validate_chat_capacity_and_spend_policy",
        lambda _settings: calls.append("capacity"),
    )
    monkeypatch.setattr(
        runtime_validation,
        "_validate_chat_openrouter_policy",
        lambda _settings: calls.append("openrouter"),
    )

    runtime_validation.validate_runtime(settings)

    assert calls == ["provider", "capacity", "openrouter"]


def test_release_manifest_isolated_from_storage_and_tolerates_extra_keys(
    settings_factory,
):
    settings, release = settings_factory("production")
    settings.runtime_data_dir = "./invalid-runtime"
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["future_release_metadata"] = {"safe": True}
    manifest["chat_runtime"]["future_descriptor_field"] = "ignored"
    manifest_path.write_text(json.dumps(manifest))

    runtime_validation.validate_release_manifest(settings)

    settings.release_id = "different-release"
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_release_manifest(settings)
    assert str(exc_info.value) == (
        "running chat runtime differs from the release manifest"
    )


def test_frontend_dist_isolated_from_identity_and_preserves_exact_error(
    settings_factory,
):
    settings, release = settings_factory("production")
    settings.release_id = ""

    assert runtime_validation.validate_frontend_dist(settings) == profile_features(
        "production"
    )

    (release / "frontend-dist" / "index.html").write_text(
        '<script type="module" src="/src/main.tsx"></script>'
    )
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_frontend_dist(settings)
    assert str(exc_info.value) == ("deployed frontend shell references /src/main.tsx")


def test_deployed_mutation_policy_isolated_from_auth(settings_factory):
    settings, _release = settings_factory("production")
    settings.jwt_secret = ""

    runtime_validation.validate_deployed_mutation_policy(settings)

    settings.thumbnail_mutations_enabled = True
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_deployed_mutation_policy(settings)
    assert str(exc_info.value) == ("deployed web services must not mutate thumbnails")
