# pyright: reportPrivateUsage=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportArgumentType=false

import copy
from types import SimpleNamespace

from anthropic_billing_bypass import (
    _BILLING_ENTRYPOINT,
    _SESSION_ID,
    _SYSTEM_IDENTITY,
    _fix_temperature_for_oauth_adaptive,
    _install_anthropic_transport_unwrap_hook,
    _install_response_pascalcase_unhook,
    _namespace_tool_name,
    _pascalcase_mcp_name,
    _restore_tool_name,
    apply_claude_code_bypass,
)


def test_apply_claude_code_bypass_injects_billing_header_and_preserves_identity(
    basic_api_kwargs,
):
    apply_claude_code_bypass(basic_api_kwargs, "2.1.90")

    system = basic_api_kwargs["system"]
    assert system[0]["text"].startswith("x-anthropic-billing-header: ")
    assert system[1]["text"] == _SYSTEM_IDENTITY
    assert system[1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


def test_apply_claude_code_bypass_uses_sdk_cli_entrypoint(basic_api_kwargs):
    apply_claude_code_bypass(basic_api_kwargs, "2.1.112")

    billing_text = basic_api_kwargs["system"][0]["text"]
    assert "cc_entrypoint=sdk-cli;" in billing_text
    assert _BILLING_ENTRYPOINT == "sdk-cli"


def test_apply_claude_code_bypass_relocates_non_identity_system_text_to_first_user_message(
    basic_api_kwargs,
):
    apply_claude_code_bypass(basic_api_kwargs, "2.1.90")

    user_content = basic_api_kwargs["messages"][0]["content"]
    assert isinstance(user_content, list)
    text = user_content[0]["text"]
    assert "<system-reminder>\nStay helpful.\n</system-reminder>" in text
    assert "<system-reminder>\nExtra system guidance\n</system-reminder>" in text
    assert text.endswith("hello world")


def test_apply_claude_code_bypass_is_idempotent(basic_api_kwargs):
    apply_claude_code_bypass(basic_api_kwargs, "2.1.90")
    once = copy.deepcopy(basic_api_kwargs)

    apply_claude_code_bypass(basic_api_kwargs, "2.1.90")

    assert len(basic_api_kwargs["system"]) == 2
    assert basic_api_kwargs["system"][0]["text"].startswith(
        "x-anthropic-billing-header: "
    )
    assert basic_api_kwargs["system"][1]["text"] == _SYSTEM_IDENTITY
    assert basic_api_kwargs["system"][1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert basic_api_kwargs["messages"] == once["messages"]


def test_apply_claude_code_bypass_normalizes_string_system(simple_messages):
    api_kwargs = {
        "system": "plain system",
        "messages": [dict(message) for message in simple_messages],
        "model": "claude-opus-4-6-20260101",
    }

    apply_claude_code_bypass(api_kwargs, "2.1.90")

    assert isinstance(api_kwargs["system"], list)
    assert api_kwargs["system"][1]["text"] == _SYSTEM_IDENTITY
    assert (
        "<system-reminder>\nplain system\n</system-reminder>"
        in api_kwargs["messages"][0]["content"][0]["text"]
    )


def test_apply_claude_code_bypass_strips_legacy_identity_without_leaking(simple_messages):
    api_kwargs = {
        "system": [
            {"type": "text", "text": "You are Claude Code, Anthropic's official CLI for Claude.\nlegacy guidance"},
        ],
        "messages": [dict(message) for message in simple_messages],
        "model": "claude-opus-4-6-20260101",
    }

    apply_claude_code_bypass(api_kwargs, "2.1.90")

    system_texts = [entry.get("text") for entry in api_kwargs["system"]]
    assert _SYSTEM_IDENTITY in system_texts
    user_text = api_kwargs["messages"][0]["content"][0]["text"]
    assert "You are Claude Code" not in user_text
    assert "legacy guidance" in user_text


def test_apply_claude_code_bypass_without_messages_is_noop():
    api_kwargs = {"system": "plain system", "model": "claude-opus-4-6-20260101"}

    apply_claude_code_bypass(api_kwargs, "2.1.90")

    assert api_kwargs == {"system": "plain system", "model": "claude-opus-4-6-20260101"}


def test_fix_temperature_for_oauth_adaptive_removes_non_default_temperature():
    api_kwargs = {"model": "claude-opus-4-6-20260101", "temperature": 0.2}
    _fix_temperature_for_oauth_adaptive(api_kwargs, site="test")
    assert "temperature" not in api_kwargs


def test_fix_temperature_for_oauth_adaptive_keeps_temperature_one():
    api_kwargs = {"model": "claude-opus-4-6-20260101", "temperature": 1}
    _fix_temperature_for_oauth_adaptive(api_kwargs, site="test")
    assert api_kwargs["temperature"] == 1


def test_fix_temperature_for_oauth_adaptive_keeps_temperature_for_other_models():
    api_kwargs = {"model": "claude-3-7-sonnet", "temperature": 0.2}
    _fix_temperature_for_oauth_adaptive(api_kwargs, site="test")
    assert api_kwargs["temperature"] == 0.2


def test_fix_temperature_for_oauth_adaptive_removes_for_opus_4_7():
    api_kwargs = {"model": "claude-opus-4-7-20260201", "temperature": 0.2}
    _fix_temperature_for_oauth_adaptive(api_kwargs, site="test")
    assert "temperature" not in api_kwargs


def test_fix_temperature_for_oauth_adaptive_without_temperature_is_noop():
    api_kwargs = {"model": "claude-opus-4-6-20260101"}
    _fix_temperature_for_oauth_adaptive(api_kwargs, site="test")
    assert api_kwargs == {"model": "claude-opus-4-6-20260101"}


def test_pascalcase_mcp_name_uppercases_first_char_after_prefix():
    assert _pascalcase_mcp_name("mcp_bash") == "mcp_Bash"
    assert _pascalcase_mcp_name("mcp_read") == "mcp_Read"
    assert _pascalcase_mcp_name("mcp_background_output") == "mcp_Background_output"


def test_pascalcase_mcp_name_leaves_already_pascalcase_unchanged():
    assert _pascalcase_mcp_name("mcp_Bash") == "mcp_Bash"
    assert _pascalcase_mcp_name("mcp_Background_output") == "mcp_Background_output"


def test_pascalcase_mcp_name_ignores_unprefixed_names():
    assert _pascalcase_mcp_name("bash") == "bash"
    assert _pascalcase_mcp_name("not_mcp_bash") == "not_mcp_bash"
    assert _pascalcase_mcp_name("") == ""


def test_namespace_tool_name_wraps_for_current_validator():
    assert _namespace_tool_name("mcp_bash") == "mcp__hermes__bash"
    assert _namespace_tool_name("bash") == "mcp__hermes__bash"
    assert _namespace_tool_name("mcp__browser__back") == "mcp__hermes__browser__back"


def test_restore_tool_name_unwraps_namespace_and_legacy_pascalcase():
    assert _restore_tool_name("mcp__hermes__bash") == "bash"
    assert _restore_tool_name("_hermes__Background_output") == "background_output"
    assert _restore_tool_name("Bash") == "bash"


def test_apply_claude_code_bypass_wraps_tool_names_for_validator(basic_api_kwargs):
    basic_api_kwargs["tools"] = [
        {"name": "mcp_bash"},
        {"name": "mcp_background_output"},
        {"name": "mcp_Already_pascal"},
    ]
    basic_api_kwargs["messages"] = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "hello world"},
                {"type": "tool_use", "name": "mcp_bash", "id": "tool_1", "input": {}},
            ],
        }
    ]

    apply_claude_code_bypass(basic_api_kwargs, "2.1.112")

    tool_names = [tool["name"] for tool in basic_api_kwargs["tools"]]
    assert tool_names == ["mcp__hermes__bash", "mcp__hermes__background_output", "mcp__hermes__Already_pascal"]

    tool_use_block = basic_api_kwargs["messages"][0]["content"][-1]
    assert tool_use_block["name"] == "mcp__hermes__bash"


def test_apply_claude_code_bypass_injects_stainless_and_direct_browser_headers(
    basic_api_kwargs,
):
    apply_claude_code_bypass(basic_api_kwargs, "2.1.112")

    extra_headers = basic_api_kwargs["extra_headers"]
    assert extra_headers["anthropic-dangerous-direct-browser-access"] == "true"
    assert extra_headers["User-Agent"] == "claude-cli/2.1.112 (external, sdk-cli)"
    assert extra_headers["x-claude-code-session-id"] == _SESSION_ID
    assert extra_headers["X-Stainless-Lang"] == "js"
    assert extra_headers["X-Stainless-Runtime"] == "node"
    assert extra_headers["X-Stainless-Runtime-Version"] == "v24.3.0"
    assert extra_headers["X-Stainless-Package-Version"] == "0.81.0"
    assert extra_headers["X-Stainless-Retry-Count"] == "0"
    assert extra_headers["X-Stainless-Timeout"] == "600"
    assert extra_headers["X-Stainless-OS"] in ("MacOS", "Linux", "Windows")
    assert extra_headers["X-Stainless-Arch"] in ("x64", "arm64", "ia32", "unknown")
    assert "x-stainless-lang" not in extra_headers


def test_apply_claude_code_bypass_sets_beta_true_query_param(basic_api_kwargs):
    apply_claude_code_bypass(basic_api_kwargs, "2.1.112")

    assert basic_api_kwargs["extra_query"] == {"beta": "true"}


def test_apply_claude_code_bypass_preserves_existing_extra_headers(basic_api_kwargs):
    basic_api_kwargs["extra_headers"] = {"anthropic-beta": "fast-mode-2026-02-01"}

    apply_claude_code_bypass(basic_api_kwargs, "2.1.112")

    assert basic_api_kwargs["extra_headers"]["anthropic-beta"] == "fast-mode-2026-02-01"
    assert (
        basic_api_kwargs["extra_headers"]["anthropic-dangerous-direct-browser-access"]
        == "true"
    )


def test_apply_claude_code_bypass_injects_metadata_user_id(tmp_path, monkeypatch, basic_api_kwargs):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude.json").write_text(
        '{"userID":"device-123","groveConfigCache":{"account-456":{}}}'
    )
    basic_api_kwargs["metadata"] = {"existing": "kept"}

    apply_claude_code_bypass(basic_api_kwargs, "2.1.112")

    assert basic_api_kwargs["metadata"]["existing"] == "kept"
    user_id = basic_api_kwargs["metadata"]["user_id"]
    assert '"device_id":"device-123"' in user_id
    assert '"account_uuid":"account-456"' in user_id
    assert _SESSION_ID in user_id


def _make_fake_adapter_module(tool_names):
    def original_normalize(response, strip_tool_prefix=False):
        tool_calls = []
        for name in tool_names:
            stripped = name[len("mcp_"):] if strip_tool_prefix and name.startswith("mcp_") else name
            tool_calls.append(
                SimpleNamespace(
                    id="tool_1",
                    type="function",
                    function=SimpleNamespace(name=stripped, arguments="{}"),
                )
            )
        msg = SimpleNamespace(content=None, tool_calls=tool_calls or None, reasoning=None)
        return msg, "tool_calls"

    module = SimpleNamespace(normalize_anthropic_response=original_normalize)
    return module


def test_response_unhook_lowercases_first_char_of_tool_names_after_strip():
    adapter = _make_fake_adapter_module(["mcp_Bash", "mcp_Background_output"])

    assert _install_response_pascalcase_unhook(adapter) is True

    msg, _reason = adapter.normalize_anthropic_response(
        response=object(), strip_tool_prefix=True
    )

    names = [tc.function.name for tc in msg.tool_calls]
    assert names == ["bash", "background_output"]


def test_response_unhook_is_noop_when_strip_tool_prefix_false():
    adapter = _make_fake_adapter_module(["mcp_Bash"])

    _install_response_pascalcase_unhook(adapter)

    msg, _reason = adapter.normalize_anthropic_response(
        response=object(), strip_tool_prefix=False
    )

    assert msg.tool_calls[0].function.name == "mcp_Bash"


def test_response_unhook_is_idempotent():
    adapter = _make_fake_adapter_module(["mcp_Bash"])

    assert _install_response_pascalcase_unhook(adapter) is True
    assert _install_response_pascalcase_unhook(adapter) is True

    msg, _reason = adapter.normalize_anthropic_response(
        response=object(), strip_tool_prefix=True
    )
    assert msg.tool_calls[0].function.name == "bash"


def test_transport_unwrap_hook_restores_namespaced_tool_calls():
    class FakeTransport:
        def normalize_response(self, response):
            msg = SimpleNamespace(
                tool_calls=[
                    SimpleNamespace(function=SimpleNamespace(name="mcp__hermes__bash")),
                    SimpleNamespace(function=SimpleNamespace(name="_hermes__Background_output")),
                ]
            )
            return msg, "tool_calls"

    module = SimpleNamespace(AnthropicTransport=FakeTransport)

    assert _install_anthropic_transport_unwrap_hook(module) is True
    msg, _reason = FakeTransport().normalize_response(object())

    names = [tc.function.name for tc in msg.tool_calls]
    assert names == ["bash", "background_output"]
