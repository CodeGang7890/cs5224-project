"""The Vertex AI (Gemini) backend of app/llm.py: app/llm_vertex.py, with a fake google-genai client."""

import unittest
from unittest.mock import MagicMock, patch

import httpx
from google.genai import errors, types

from app import config, llm, llm_vertex

UNPATCHED_GET_CLIENT = llm_vertex.get_client  # before the tests patch it

SCHEMA = {'type': 'object', 'properties': {'intents': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['intents']}


def text_response(text):
    return types.GenerateContentResponse(candidates=[
        types.Candidate(content=types.Content(role='model', parts=[types.Part(text=text)])),
    ])


def call_response(*calls):
    return types.GenerateContentResponse(candidates=[
        types.Candidate(content=types.Content(role='model', parts=[
            types.Part(function_call=types.FunctionCall(name=name, args=args)) for name, args in calls
        ])),
    ])


def api_error(code):
    return errors.APIError(code, {'error': {'code': code, 'message': 'boom', 'status': 'X'}})


class VertexTestCase(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        for patcher in (
            patch.object(config, 'LLM_PROVIDER', 'vertex_ai'),
            patch.object(config, 'LLM_MODEL', 'gemini-2.5-flash'),
            patch.object(llm_vertex, 'get_client', return_value=self.client),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def respond(self, *responses):
        self.client.models.generate_content.side_effect = list(responses)

    def call(self, index=0):
        """The keyword arguments of the index-th generate_content call."""
        return self.client.models.generate_content.call_args_list[index].kwargs


class StructuredTests(VertexTestCase):
    def test_returns_the_json_object_with_the_schema_and_temperature_0(self):
        self.respond(text_response('{"intents": ["order"]}'))
        history = [{'role': 'user', 'content': 'hi'}, {'role': 'assistant', 'content': 'Hello!'}, {'role': 'user', 'content': '2 kopi'}]

        self.assertEqual(llm.generate_structured('Route it.', history, SCHEMA), {'intents': ['order']})

        call = self.call()
        self.assertEqual(call['model'], 'gemini-2.5-flash')
        self.assertEqual([(c.role, [p.text for p in c.parts]) for c in call['contents']],
                         [('user', ['hi']), ('model', ['Hello!']), ('user', ['2 kopi'])])
        generation = call['config']
        self.assertEqual(generation.system_instruction, 'Route it.')
        self.assertEqual(generation.response_mime_type, 'application/json')
        self.assertEqual(generation.response_json_schema, SCHEMA)
        self.assertEqual(generation.temperature, 0.0)
        self.assertEqual(generation.seed, config.VERTEX_AI_OPTIONS['seed'])
        self.assertEqual(generation.thinking_config.thinking_budget, config.VERTEX_AI_THINKING_BUDGET)

    def test_invalid_json_or_not_an_object_is_an_llm_error(self):
        for text, message in (('not json', 'valid JSON'), ('[1, 2]', 'JSON object'), ('', 'valid JSON')):
            with self.subTest(text=text):
                self.respond(text_response(text))
                with self.assertRaisesRegex(llm.LLMError, message):
                    llm.generate_structured('Route it.', [{'role': 'user', 'content': 'hi'}], SCHEMA)


class ContentsTests(unittest.TestCase):
    def test_consecutive_messages_of_one_side_are_one_turn_and_empty_ones_are_skipped(self):
        contents = llm_vertex._contents([
            {'role': 'assistant', 'content': 'Welcome!'},
            {'role': 'assistant', 'content': 'How can I help?'},
            {'role': 'user', 'content': ''},
            {'role': 'user', 'content': 'A cake'},
        ])
        self.assertEqual([(c.role, [p.text for p in c.parts]) for c in contents],
                         [('model', ['Welcome!', 'How can I help?']), ('user', ['A cake'])])


class ChatReplyTests(VertexTestCase):
    def setUp(self):
        super().setUp()
        self.toolbox = MagicMock()
        self.toolbox.specs = [
            {'type': 'function', 'function': {'name': 'list_faqs', 'description': 'FAQs.',
                                              'parameters': {'type': 'object', 'properties': {}, 'required': []}}},
            {'type': 'function', 'function': {'name': 'get_product_details', 'description': 'One product.',
                                              'parameters': {'type': 'object', 'properties': {'product': {'type': 'string'}}, 'required': ['product']}}},
        ]
        self.toolbox.run.return_value = '[{"question": "Open?", "answer": "9-5"}]'

    def test_a_plain_reply(self):
        self.respond(text_response('Hi there!'))
        self.assertEqual(llm.generate_chat_reply('Be nice.', [{'role': 'user', 'content': 'hi'}], self.toolbox), 'Hi there!')
        declarations = self.call()['config'].tools[0].function_declarations
        self.assertEqual([d.name for d in declarations], ['list_faqs', 'get_product_details'])
        self.assertIsNone(declarations[0].parameters_json_schema)  # no arguments
        self.assertEqual(declarations[1].parameters_json_schema['required'], ['product'])
        self.assertEqual(self.call()['config'].temperature, config.VERTEX_AI_OPTIONS['temperature'])

    def test_tool_calls_are_run_and_their_results_sent_back(self):
        self.respond(call_response(('list_faqs', {})), text_response('We open 9-5.'))

        reply = llm.generate_chat_reply('Be nice.', [{'role': 'user', 'content': 'When do you open?'}], self.toolbox)

        self.assertEqual(reply, 'We open 9-5.')
        self.toolbox.run.assert_called_once_with('list_faqs', {})
        contents = self.call(1)['contents']
        self.assertEqual([c.role for c in contents], ['user', 'model', 'user'])
        self.assertEqual(contents[1].parts[0].function_call.name, 'list_faqs')
        result = contents[2].parts[0].function_response
        self.assertEqual((result.name, result.response), ('list_faqs', {'result': [{'question': 'Open?', 'answer': '9-5'}]}))

    def test_out_of_tool_rounds_it_must_answer(self):
        calls = [call_response(('list_faqs', {})) for _ in range(config.MAX_TOOL_ROUNDS)]
        self.respond(*calls, text_response('Sorry, here is what I know.'))

        reply = llm.generate_chat_reply('Be nice.', [{'role': 'user', 'content': 'hi'}], self.toolbox)

        self.assertEqual(reply, 'Sorry, here is what I know.')
        self.assertEqual(self.toolbox.run.call_count, config.MAX_TOOL_ROUNDS)
        last = self.call(config.MAX_TOOL_ROUNDS)['config']
        self.assertEqual(last.tool_config.function_calling_config.mode, types.FunctionCallingConfigMode.NONE)

    def test_without_a_toolbox_no_tools_are_declared(self):
        self.respond(text_response('Hi!'))
        self.assertEqual(llm.generate_chat_reply('Be nice.', [{'role': 'user', 'content': 'hi'}]), 'Hi!')
        self.assertIsNone(self.call()['config'].tools)

    def test_a_blocked_answer_is_an_empty_reply(self):
        self.respond(types.GenerateContentResponse(candidates=[]))
        self.assertEqual(llm.generate_chat_reply('Be nice.', [{'role': 'user', 'content': 'hi'}]), '')


class ReplyTests(VertexTestCase):
    def test_one_off_chat_uses_the_system_prompt_and_no_sampling_options(self):
        self.respond(text_response('Hello!'))
        self.assertEqual(llm.generate_reply('hi'), 'Hello!')
        generation = self.call()['config']
        self.assertEqual(generation.system_instruction, config.SYSTEM_PROMPT)
        self.assertIsNone(generation.temperature)


class ErrorTests(VertexTestCase):
    def test_failures_map_to_the_llm_errors(self):
        cases = {
            'rate limited': (api_error(429), llm.LLMUnavailableError),
            'server error': (api_error(503), llm.LLMUnavailableError),
            'bad request': (api_error(400), llm.LLMError),
            'timeout': (httpx.ReadTimeout('slow'), llm.LLMTimeoutError),
            'unreachable': (httpx.ConnectError('down'), llm.LLMUnavailableError),
        }
        for name, (error, expected) in cases.items():
            with self.subTest(name):
                self.client.models.generate_content.side_effect = error
                with self.assertRaises(expected) as raised:
                    llm.generate_reply('hi')
                self.assertIs(type(raised.exception), expected)

    def test_a_missing_project_is_unavailable(self):
        with patch.object(config, 'GOOGLE_CLOUD_PROJECT', ''):
            with self.assertRaisesRegex(llm.LLMUnavailableError, 'GOOGLE_CLOUD_PROJECT'):
                UNPATCHED_GET_CLIENT.__wrapped__()  # the function itself, without its cache


class ProviderTests(unittest.TestCase):
    def test_ollama_is_the_default_and_never_calls_vertex_ai(self):
        self.assertEqual(config.LLM_PROVIDER, 'ollama')
        with patch.object(llm_vertex, 'generate_reply') as vertex, patch('app.llm.get_client') as ollama:
            ollama.return_value.chat.return_value.message.content = 'Hi'
            self.assertEqual(llm.generate_reply('hi'), 'Hi')
        vertex.assert_not_called()

    def test_vertex_ai_routes_every_call_to_it(self):
        with patch.object(config, 'LLM_PROVIDER', 'vertex_ai'), patch('app.llm.get_client') as ollama, \
                patch.multiple(llm_vertex, generate_reply=MagicMock(return_value='a'),
                               generate_structured=MagicMock(return_value={'b': 1}),
                               generate_chat_reply=MagicMock(return_value='c')):
            self.assertEqual(llm.generate_reply('hi'), 'a')
            self.assertEqual(llm.generate_structured('s', [], SCHEMA), {'b': 1})
            self.assertEqual(llm.generate_chat_reply('s', []), 'c')
        ollama.assert_not_called()



if __name__ == '__main__':
    unittest.main()
