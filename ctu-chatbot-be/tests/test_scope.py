from langchain_core.messages import AIMessageChunk, HumanMessage

from app.services.chat import scope


class Classifier:
    def __init__(self, reply="regulation", error=None):
        self.reply, self.error, self.calls = reply, error, 0

    def stream(self, messages):
        self.calls += 1
        if self.error:
            raise self.error
        yield AIMessageChunk(content=self.reply)


def _ask(llm, text, score, earlier=()):
    history = [HumanMessage(content=t) for t in earlier] + [HumanMessage(content=text)]
    return scope.classify(llm, history, score)


def test_high_score_goes_to_regulation_without_llm_call():
    llm = Classifier("external")
    assert _ask(llm, "ĐTBCTL của mình thấp thì sao?", 0.8) == scope.REGULATION
    assert llm.calls == 0


def test_explicit_article_and_smalltalk_skip_llm():
    llm = Classifier("external")
    assert _ask(llm, "Điều 14 nói gì?", 0.3) == scope.REGULATION
    assert _ask(llm, "xin chào", 0.6) == scope.SMALLTALK
    assert _ask(llm, "cảm ơn bạn nhé", 0.6) == scope.SMALLTALK
    assert llm.calls == 0


def test_uncertain_band_uses_llm_classifier():
    assert _ask(Classifier("external"), "Học phí một tín chỉ năm nay bao nhiêu?", 0.7) == scope.EXTERNAL
    assert _ask(Classifier("offtopic"), "Cách nấu phở?", 0.55) == scope.OFFTOPIC
    assert _ask(Classifier("Regulation."), "Học cải thiện thế nào?", 0.7) == scope.REGULATION


def test_long_message_starting_with_greeting_is_not_smalltalk():
    llm = Classifier("external")
    text = "chào bạn, cho mình hỏi học phí ngành CNTT năm nay là bao nhiêu và đóng ở đâu vậy?"
    assert _ask(llm, text, 0.65) == scope.EXTERNAL


def test_any_failure_falls_back_to_regulation():
    assert _ask(Classifier(error=RuntimeError("429")), "câu mơ hồ", 0.65) == scope.REGULATION
    assert _ask(Classifier("không biết"), "câu mơ hồ", 0.65) == scope.REGULATION
    assert scope.classify(Classifier(), [], 0.1) == scope.REGULATION


def test_followup_gets_previous_question_as_context():
    seen = []

    class Spy(Classifier):
        def stream(self, messages):
            seen.append(messages[-1].content)
            return super().stream(messages)

    _ask(Spy("external"), "còn năm ngoái thì sao?", 0.6, earlier=["Học phí năm nay bao nhiêu?"])
    assert "Học phí năm nay" in seen[0]


def test_classifier_supports_dynamic_document_routes_and_disabled_targets():
    routes = [
        {"id": "regulation", "label": "Quy chế học vụ", "prompt": "quy chế", "kind": "document"},
        {"id": "academic-calendar", "label": "Lịch học", "prompt": "lịch học và lịch thi", "kind": "document"},
    ]
    assert scope.classify(Classifier("academic-calendar"), [HumanMessage(content="Lịch thi học kỳ này?")], 0.9, routes) == "academic-calendar"

    only_custom_route = [routes[1]]
    assert scope.classify(Classifier("regulation"), [HumanMessage(content="Điều 14 nói gì?")], 0.95, only_custom_route) == "academic-calendar"
