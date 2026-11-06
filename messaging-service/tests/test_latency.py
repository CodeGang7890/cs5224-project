import unittest

from app import latency


class LatencyLogTests(unittest.TestCase):
    """app/latency.py: the searchable `[LATENCY][TAG]…` lines and the SUMMARY."""

    def logged(self, block):
        with self.assertLogs('app.latency', level='INFO') as logs:
            block()
        return [line.split('app.latency:', 1)[1].strip() for line in logs.output]

    def test_tags_then_seconds_then_the_bound_fields(self):
        def block():
            with latency.bind(channel='whatsapp', msg='wamid.1'):
                latency.add_fields(chat=21)
                latency.log(['llm', 'order_status', 'reply'], 1.23456, grounded=True, intents=['booking', 'question'])
        line, = self.logged(block)
        self.assertEqual(
            line,
            '[LATENCY][LLM][ORDER_STATUS][REPLY] 1.235s channel=whatsapp msg=wamid.1 chat=21 grounded=True intents=booking,question',
        )

    def test_fields_end_with_their_bind_and_none_is_left_out(self):
        def block():
            with latency.bind(channel='sandbox'):
                pass
            latency.log(['SEND'], 0.5, message=None, number='1/2')
        line, = self.logged(block)
        self.assertEqual(line, '[LATENCY][SEND] 0.500s number=1/2')

    def test_timed_logs_errors_and_reraises(self):
        def block():
            with self.assertRaises(ValueError):
                with latency.timed('LLM', 'ROUTER') as timer:
                    timer.fields['intents'] = []
                    raise ValueError('boom')
        line, = self.logged(block)
        self.assertRegex(line, r'^\[LATENCY\]\[LLM\]\[ROUTER\] \d+\.\d{3}s intents=- status=error error=ValueError$')

    def test_the_summary_adds_up_each_stage_but_not_the_totals(self):
        def block():
            with latency.bind(channel='api', chat=3):
                latency.log(['LLM', 'ROUTER'], 0.25)
                latency.log(['LLM', 'EXTRACTION', 'SLOT_SELECTION'], 0.5)
                latency.log(['LLM', 'EXTRACTION', 'SLOT_SELECTION'], 0.25)  # visited twice: added up
                latency.log(['TURN'], 1.0)
                latency.log(['E2E'], 1.1)
                latency.summary(1.1, status='ok')
        *_, summary = self.logged(block)
        self.assertEqual(
            summary,
            '[LATENCY][SUMMARY] 1.100s channel=api chat=3 status=ok router=0.25 extraction.slot_selection=0.75',
        )


if __name__ == '__main__':
    unittest.main()
