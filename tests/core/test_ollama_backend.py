"""
Ollama backend tests (stdlib unittest — no ollama package, no server needed).

Run:
    python -m unittest tests.core.test_ollama_backend -v

Verifies the local-LLM adapter for role agents:
  - Gemini schema -> JSON-Schema conversion (so tool_calls pass correctly to qwen3)
  - the manifest system prompt is carried through as a system message (Tier req #4)
  - tool_calls and final text parse back into ModelTurn / ToolCall
  - a backend failure degrades to text, never an exception (Tier 3)
  - end-to-end: the adapter works as a RoleAgent model_fn AND the dispatch allowlist
    (Tier 2) still holds when driven by the local backend
"""

import unittest

from core.manifest import AgentManifest
from core.role_agent import RoleAgent, ModelTurn, ToolCall
from core.ollama_backend import (
    convert_schema,
    to_ollama_tool,
    build_messages,
    parse_response,
    ollama_chat,
    DEFAULT_MODEL,
)


GEMINI_DECL = {
    "name": "web_search",
    "description": "search the web",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "the query"},
            "items": {"type": "ARRAY", "items": {"type": "STRING"}},
            "depth": {"type": "INTEGER"},
        },
        "required": ["query"],
    },
}


class FakeClient:
    """Stand-in for ollama.Client — returns scripted responses, records the call."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def chat(self, model, messages, tools):
        self.calls.append({"model": model, "messages": messages, "tools": tools})
        return self._responses.pop(0)


class TestSchemaConversion(unittest.TestCase):
    def test_types_lowercased_recursively(self):
        out = convert_schema(GEMINI_DECL["parameters"])
        self.assertEqual(out["type"], "object")
        self.assertEqual(out["properties"]["query"]["type"], "string")
        self.assertEqual(out["properties"]["items"]["type"], "array")
        self.assertEqual(out["properties"]["items"]["items"]["type"], "string")
        self.assertEqual(out["properties"]["depth"]["type"], "integer")
        # 'required' is preserved untouched
        self.assertEqual(out["required"], ["query"])

    def test_to_ollama_tool_shape(self):
        tool = to_ollama_tool(GEMINI_DECL)
        self.assertEqual(tool["type"], "function")
        self.assertEqual(tool["function"]["name"], "web_search")
        self.assertEqual(tool["function"]["parameters"]["type"], "object")

    def test_empty_params_get_defaults(self):
        tool = to_ollama_tool({"name": "ping", "description": "p"})
        self.assertEqual(tool["function"]["parameters"]["type"], "object")
        self.assertIn("properties", tool["function"]["parameters"])


class TestSystemPrompt(unittest.TestCase):
    def test_system_prompt_carried_as_system_message(self):
        m = AgentManifest(name="eva", system_prompt="You are Eva, the gold desk.")
        msgs = build_messages(m, [{"role": "user", "content": "gold price?"}])
        self.assertEqual(msgs[0]["role"], "system")
        self.assertIn("Eva", msgs[0]["content"])
        self.assertEqual(msgs[1]["role"], "user")

    def test_falls_back_to_description(self):
        m = AgentManifest(name="x", description="desc only")
        msgs = build_messages(m, [{"role": "user", "content": "hi"}])
        self.assertEqual(msgs[0]["content"], "desc only")

    def test_tool_results_become_tool_messages(self):
        m = AgentManifest(name="x", system_prompt="s")
        msgs = build_messages(
            m,
            [
                {"role": "user", "content": "q"},
                {"role": "tool", "name": "web_search", "content": "result"},
            ],
        )
        self.assertEqual(msgs[-1]["role"], "tool")
        self.assertEqual(msgs[-1]["name"], "web_search")

    def test_assistant_tool_call_turn_reconstructed(self):
        # Regression: an assistant tool-call turn must precede tool results so the
        # local model reads the result instead of re-calling the tool to the cap.
        m = AgentManifest(name="x", system_prompt="s")
        msgs = build_messages(
            m,
            [
                {"role": "user", "content": "gold?"},
                {"role": "assistant", "content": "",
                 "tool_calls": [{"name": "web_search", "args": {"query": "gold"}}]},
                {"role": "tool", "name": "web_search", "content": "2412"},
            ],
        )
        asst = msgs[2]
        self.assertEqual(asst["role"], "assistant")
        self.assertEqual(asst["tool_calls"][0]["function"]["name"], "web_search")
        self.assertEqual(asst["tool_calls"][0]["function"]["arguments"], {"query": "gold"})
        self.assertEqual(msgs[3]["role"], "tool")


class TestResponseParsing(unittest.TestCase):
    def test_parses_tool_calls_dict_form(self):
        resp = {"message": {"tool_calls": [
            {"function": {"name": "web_search", "arguments": {"query": "gold"}}}
        ]}}
        turn = parse_response(resp)
        self.assertEqual(len(turn.tool_calls), 1)
        self.assertEqual(turn.tool_calls[0].name, "web_search")
        self.assertEqual(turn.tool_calls[0].args, {"query": "gold"})

    def test_parses_arguments_as_json_string(self):
        resp = {"message": {"tool_calls": [
            {"function": {"name": "web_search", "arguments": '{"query": "gold"}'}}
        ]}}
        turn = parse_response(resp)
        self.assertEqual(turn.tool_calls[0].args, {"query": "gold"})

    def test_final_text_with_think_stripped(self):
        resp = {"message": {"content": "<think>let me reason</think>Gold is $2400."}}
        turn = parse_response(resp)
        self.assertEqual(turn.tool_calls, ())
        self.assertEqual(turn.text, "Gold is $2400.")

    def test_object_style_response(self):
        class Fn:
            name = "web_search"
            arguments = {"query": "gold"}

        class TC:
            function = Fn()

        class Msg:
            tool_calls = [TC()]
            content = ""

        class Resp:
            message = Msg()

        turn = parse_response(Resp())
        self.assertEqual(turn.tool_calls[0].name, "web_search")


class TestOllamaChat(unittest.TestCase):
    def test_uses_manifest_model_and_passes_tools(self):
        m = AgentManifest(name="eva", model="qwen3:14b", system_prompt="s")
        fake = FakeClient([{"message": {"content": "Gold is $2400."}}])
        turn = ollama_chat(m, [{"role": "user", "content": "gold?"}],
                           [GEMINI_DECL], client=fake)
        self.assertEqual(turn.text, "Gold is $2400.")
        self.assertEqual(fake.calls[0]["model"], "qwen3:14b")
        # tools were converted to JSON-schema before the call
        self.assertEqual(
            fake.calls[0]["tools"][0]["function"]["parameters"]["type"], "object"
        )

    def test_default_model_when_manifest_blank(self):
        m = AgentManifest(name="eva", model="")
        fake = FakeClient([{"message": {"content": "ok"}}])
        ollama_chat(m, [{"role": "user", "content": "x"}], [], client=fake)
        self.assertEqual(fake.calls[0]["model"], DEFAULT_MODEL)

    def test_backend_failure_degrades_to_text(self):
        class Boom:
            def chat(self, **k):
                raise RuntimeError("connection refused")

        m = AgentManifest(name="eva")
        turn = ollama_chat(m, [{"role": "user", "content": "x"}], [], client=Boom())
        self.assertEqual(turn.tool_calls, ())
        self.assertIn("could not complete", turn.text)


class TestEndToEndWithRoleAgent(unittest.TestCase):
    """The adapter is a real model_fn AND Tier 2 still holds when driven locally."""

    def test_role_agent_runs_on_ollama_backend(self):
        m = AgentManifest(name="eva", model="qwen3:14b",
                          tools=("web_search",), max_iterations=5,
                          system_prompt="You are Eva.")
        fake = FakeClient([
            {"message": {"tool_calls": [
                {"function": {"name": "web_search", "arguments": {"query": "gold"}}}]}},
            {"message": {"content": "Gold is $2412/oz, sir."}},
        ])
        dispatched = []

        def dispatch_fn(name, args):
            dispatched.append((name, args))
            return "Gold spot 2412"

        def model_fn(manifest, messages, tools):
            return ollama_chat(manifest, messages, tools, client=fake)

        agent = RoleAgent(m, tool_declarations=[GEMINI_DECL],
                          dispatch_fn=dispatch_fn, model_fn=model_fn)
        result = agent.run("what is the gold price")
        self.assertTrue(result.converged)
        self.assertEqual(result.result, "Gold is $2412/oz, sir.")
        self.assertEqual(dispatched, [("web_search", {"query": "gold"})])

    def test_tier2_allowlist_holds_on_ollama(self):
        # Eva's allowlist is web_search only; a model that asks for send_message is blocked.
        m = AgentManifest(name="eva", model="qwen3:14b",
                          tools=("web_search",), max_iterations=3)
        fake = FakeClient([
            {"message": {"tool_calls": [
                {"function": {"name": "send_message", "arguments": {"x": 1}}}]}},
            {"message": {"content": "ok"}},
        ])
        blocked = []

        def dispatch_fn(name, args):
            # mimic main._run_role's allowlist guard
            if name not in m.tools:
                blocked.append(name)
                return f"Tool '{name}' is not in eva's allowlist."
            return "ran"

        agent = RoleAgent(m, tool_declarations=[GEMINI_DECL],
                          dispatch_fn=dispatch_fn,
                          model_fn=lambda mn, ms, t: ollama_chat(mn, ms, t, client=fake))
        agent.run("message john")
        self.assertEqual(blocked, ["send_message"])  # never actually ran


if __name__ == "__main__":
    unittest.main(verbosity=2)
