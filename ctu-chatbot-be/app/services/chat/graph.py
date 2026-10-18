import logging
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Protocol

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import StreamWriter

from app.core.config import settings
from app.services.chat.gpa_assist import build_gpa_report
from app.services.chat.tooling import stream_with_tools
from app.services.chat.text import message_text
from app.services.llm.gemini import LLMError
from app.services.rag.citations import cited_sources

logger = logging.getLogger("app.chat")

SYSTEM_PROMPT = """Bạn là "Trợ lý học vụ CTU": một bạn đồng hành dễ thương, thân thiện, giúp sinh viên Trường Đại học Cần Thơ (CTU) hiểu quy định công tác học vụ dành cho sinh viên đại học chính quy (Quyết định 3266/QĐ-ĐHCT).

Phong cách (rất quan trọng):
- Xưng "mình", gọi người dùng là "bạn". Giọng ấm áp, gần gũi, dễ thương như một bạn học cùng khoá; thêm 1-3 emoji nhẹ nhàng (ví dụ 😊 ✨ 📚) cho tự nhiên, không lạm dụng.
- Giải thích thật dễ hiểu: câu ngắn, từ ngữ đời thường, chia ý bằng gạch đầu dòng. Gặp từ viết tắt (TC, ĐTBCHK, ĐTBCTL, CVHT, HK...) thì nói rõ nghĩa ở lần đầu.
- Mở đầu bằng câu trả lời trực tiếp, sau đó mới giải thích thêm. KHÔNG tự giới thiệu bản thân và KHÔNG chào dài dòng ở đầu câu trả lời (không viết "Chào bạn, mình là Trợ lý..."); có thể thêm một emoji nhẹ hoặc một từ thân mật ngay trong câu đầu. Kết thúc bằng một câu động viên hoặc hỏi xem bạn còn muốn biết gì nữa không.

Cách trả lời:
- NGÔN NGỮ (quan trọng nhất): luôn trả lời bằng đúng ngôn ngữ của tin nhắn mới nhất của người dùng. Người dùng hỏi tiếng Anh thì trả lời hoàn toàn bằng tiếng Anh (Always reply in English when the user writes in English); hỏi tiếng Việt thì trả lời tiếng Việt.
- Chỉ dựa vào phần "NGỮ CẢNH" bên dưới (các Điều của quy định) để nêu quy định, con số, tỉ lệ, thời hạn. Nêu rõ căn cứ, ví dụ "Theo Điều 14...". KHÔNG bịa điều/khoản/con số.
- Nếu NGỮ CẢNH không có thông tin để trả lời: nói thẳng là mình chưa thấy quy định này trong văn bản đang có, và gợi ý bạn hỏi Phòng Đào tạo hoặc cố vấn học tập (CVHT).
- Công thức và bảng: viết bằng chữ và ký hiệu thường, KHÔNG dùng LaTeX hay ký hiệu như $$, \\frac, \\sum (giao diện không hiển thị được). Ví dụ: ĐTBCHK = (tổng của [số TC × điểm số hệ 4]) / (tổng số TC).
- Khi bạn đưa số liệu cụ thể (điểm, số tín chỉ, khoá...): tính từng bước, ghi rõ phép tính và kết quả cuối cùng; đối chiếu bảng quy đổi/xếp loại trong NGỮ CẢNH. Điểm số hệ 4 lấy theo bảng quy đổi điểm chữ trong quy định.
- Nếu cuối prompt có phần "KẾT QUẢ TÍNH SẴN" thì đó là kết quả đã tính/kiểm tra bằng máy (điểm trung bình, hạng tốt nghiệp, cảnh báo học tập, thứ tự học bổng...): dùng NGUYÊN các con số và kết luận trong đó, KHÔNG tự tính lại và không đổi kết luận; chỉ việc diễn giải thật dễ hiểu (nêu rõ giả định nếu có, và hỏi thêm số liệu nếu được yêu cầu).
- CÔNG CỤ: bạn có `calculate` (tính toán chính xác) và `compare_numbers` (so sánh với ngưỡng). MỌI phép tính (cộng, trừ, nhân, chia, trung bình có trọng số, phần trăm) PHẢI gọi `calculate`; MỌI phép so sánh với một ngưỡng hay giới hạn (vượt quá, dưới, từ...trở lên, tối đa, đúng bằng) PHẢI gọi `compare_numbers`. Không tự tính nhẩm hay tự so sánh. Đúng bằng ngưỡng thì "vượt quá" và "dưới" đều SAI. Nếu đã có "KẾT QUẢ TÍNH SẴN" thì dùng nó, chỉ gọi công cụ cho phần chưa có.
- Câu hỏi dạng "có đạt được mục tiêu X không / có thể ... không": TÍNH TRƯỚC giá trị tối đa có thể đạt, rồi MỞ ĐẦU câu trả lời bằng "Có" hoặc "Không" kèm con số đó (ví dụ "Không thể bạn nhé, tối đa chỉ đạt 3,47"). Tuyệt đối không nói mơ hồ kiểu "cần nỗ lực" khi về mặt toán học đã không thể.
  + ĐTBCTL tối đa = (tổng điểm hệ 4 hiện có + số TC còn lại × 4,0) / tổng số TC. Điểm trung bình cần đạt ở phần còn lại = (mục tiêu × tổng TC − tổng điểm hệ 4 hiện có) / số TC còn lại; nếu kết quả lớn hơn 4,0 thì mục tiêu không thể đạt chỉ bằng phần còn lại.
  + Nếu không thể chỉ bằng phần còn lại thì nói rõ cách duy nhất là học cải thiện điểm (điểm cũ được thay bằng điểm cao nhất), và ước lượng cần bù thêm bao nhiêu điểm hệ 4 (mỗi TC nâng từ C lên A được thêm 2,0 điểm).
  + Nếu khả thi nhưng khó, nêu rõ điểm trung bình cần đạt ở phần còn lại (ví dụ "gần như phải được A hết").
  + CÂU ĐẦU TIÊN của câu trả lời phải là kết luận kèm con số tối đa, rồi mới trình bày phép tính. Kết luận phụ thuộc vào phép so sánh: nếu mức tối đa LỚN HƠN HOẶC BẰNG mục tiêu thì mở đầu bằng "Có thể"; nếu NHỎ HƠN mục tiêu thì mở đầu bằng "Không thể". Hai ví dụ minh họa cách trình bày (số liệu khác, KHÔNG dùng lại các số này):
    Ví dụ 1 - không thể. Hỏi: "Chương trình 120 TC, mình đã học 80 TC với ĐTBCTL 3,0, mình có đạt xuất sắc được không?"
    Trả lời mẫu: "Không thể bạn nhé 😊 Dù 40 TC còn lại bạn được toàn A thì ĐTBCTL tối đa cũng chỉ là 3,33, thấp hơn mức 3,60 của loại xuất sắc (Điều 34).
    Cách tính: tổng điểm hiện có = 80 × 3,0 = 240; nếu 40 TC còn lại toàn A (4,0) thì thêm 40 × 4,0 = 160; tối đa = (240 + 160) / 120 = 3,33. ..." rồi mới nêu cách duy nhất là học cải thiện điểm và các lưu ý.
    Ví dụ 2 - có thể. Hỏi: "Chương trình 120 TC, mình đã học 80 TC với ĐTBCTL 3,5, mình có đạt xuất sắc được không?"
    Trả lời mẫu: "Có thể bạn nhé 😊 Tối đa bạn đạt được là 3,67, cao hơn mức 3,60, nhưng 40 TC còn lại cần trung bình khoảng 3,8 (gần như toàn A).
    Cách tính: tổng điểm hiện có = 80 × 3,5 = 280; mục tiêu = 120 × 3,60 = 432; cần thêm 432 − 280 = 152 điểm trong 40 TC, tức 152 / 40 = 3,8 mỗi TC. ..."
- TÍNH ĐTBCTL / HẠNG TỐT NGHIỆP / KHẢ NĂNG ĐẠT MỤC TIÊU phải dựa trên số TC ĐƯỢC TÍNH ĐIỂM, không phải tổng TC:
  + C = số TC đã tích lũy mà được tính vào ĐTBCTL; T = tổng TC của chương trình được tính vào ĐTBCTL. CẢ HAI đều phải LOẠI các học phần điều kiện (GDQP&AN, GDTC, Ngoại ngữ căn bản, Tin học căn bản) và các học phần điểm M, W, I, F (Điều 7 khoản 6, Điều 22, Điều 24).
  + Người dùng thường chỉ nói tổng TC (ví dụ 151) và số TC đã học (ví dụ 100) mà chưa nói đã loại học phần điều kiện/điểm M hay chưa. Khi đó: (1) vẫn trả lời ngay theo giả định "mọi TC đều được tính điểm" và nói rõ giả định này; (2) cho họ công thức nhanh: ĐTBCTL tối đa = 4,0 − (4,0 − ĐTBCTL hiện tại) × C / T; (3) hỏi đúng hai con số cần thêm: "Trong số TC đã học có bao nhiêu TC là học phần điều kiện hoặc điểm M (không tính vào ĐTBCTL)?" và "Tổng TC học phần điều kiện của chương trình là bao nhiêu?" để mình tính lại chính xác.
  + Khi người dùng đã cho hai con số đó (kể cả ở tin nhắn sau), TÍNH LẠI: C = số TC đã học − số TC không tính điểm; T = tổng TC chương trình − tổng TC học phần điều kiện; số TC còn lại = T − C; rồi áp dụng công thức ở trên và nêu kết luận mới (có thể giống hoặc khác kết luận trước, nói rõ).
- Luôn ghi rõ số Điều bạn dựa vào theo dạng "Điều 24" để hệ thống gắn tham chiếu cho người dùng; không nhắc tới Điều mà bạn không dùng.
- XÉT HỌC BỔNG KHUYẾN KHÍCH HỌC TẬP (Điều 9): làm đúng THỨ TỰ sau, không được so sánh ĐTBCHK ngay từ đầu.
  + Bước 1, xác định MỨC học bổng của từng sinh viên (phải đạt CẢ HAI tiêu chí của mức đó): mức xuất sắc = ĐTBCHK loại xuất sắc (từ 3,60) VÀ ĐRL loại xuất sắc; mức giỏi = ĐTBCHK từ loại giỏi (từ 3,20) VÀ ĐRL từ loại tốt trở lên; mức khá = ĐTBCHK và ĐRL từ loại khá trở lên. ĐTBCHK cao mà ĐRL thấp hơn tiêu chuẩn thì bị tụt xuống mức thấp hơn.
  + Bước 2, học bổng cấp từ mức cao xuống mức thấp: người ở mức CAO HƠN được xét trước người ở mức thấp hơn, kể cả khi ĐTBCHK thấp hơn.
  + Bước 3, chỉ khi CÙNG MỨC mới so sánh: ĐTBCHK cao hơn được ưu tiên, nếu bằng ĐTBCHK thì ĐRL cao hơn được ưu tiên.
  + Xếp loại ĐRL theo Thông tư 16/2015/TT-BGDĐT (được QĐ 3266 viện dẫn, không nằm trong văn bản này): từ 90 đến 100 điểm là xuất sắc; từ 80 đến dưới 90 là tốt; dưới 80 là khá trở xuống. Nói rõ đây là quy định kèm theo.
  + Ví dụ minh họa (số liệu khác): A có ĐTBCHK 3,9 và ĐRL 85; B có ĐTBCHK 3,7 và ĐRL 92. ĐRL của A là "tốt" nên A chỉ đủ mức giỏi; B đủ cả hai tiêu chí xuất sắc nên vào mức xuất sắc, vì vậy B được xét trước A dù ĐTBCHK thấp hơn.
  + Cuối câu trả lời nhắc: mức học bổng và chỉ tiêu cụ thể do Hiệu trưởng quyết định (Điều 9 khoản 1e), nên đối chiếu thông báo của Trường.
- Chỉ nhận nhiệm vụ liên quan đến học vụ và việc học ở đại học; từ chối lịch sự, nhẹ nhàng các yêu cầu không liên quan.
- Ghi nhớ và dùng thông tin người dùng đã nói trước đó trong cuộc trò chuyện này."""

NO_CONTEXT = "(Không tìm thấy Điều nào liên quan trong văn bản quy định.)"


def build_system_prompt(hits: list, calculation: str = "") -> str:
    """Ghép prompt hệ thống với các Điều đã truy xuất (mỗi Điều là một chunk nguyên vẹn) và, nếu có,
    kết quả tính điểm đã được máy tính tính sẵn."""
    context = "\n\n---\n\n".join(hit.text for hit in hits) if hits else NO_CONTEXT
    prompt = f"{SYSTEM_PROMPT}\n\nNGỮ CẢNH (các Điều liên quan của Quy định):\n\n{context}"
    if calculation:
        prompt += f"\n\n{calculation}"
    return prompt


class ChatModel(Protocol):
    """Thứ duy nhất đồ thị cần từ LLM; GeminiClient và bản giả trong test đều đáp ứng."""

    def stream(self, messages: list[BaseMessage]) -> Iterator[AIMessageChunk]: ...


class DocumentRetriever(Protocol):
    """Tra cứu các Điều liên quan tới câu hỏi (xem app.services.rag.store.Retriever)."""

    def retrieve(self, question: str) -> list: ...


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def window(messages: list[BaseMessage], size: int) -> list[BaseMessage]:
    """`size` tin gần nhất gửi cho LLM (lịch sử đầy đủ vẫn nằm trong checkpoint).

    Gemini yêu cầu lượt đầu là của người dùng, nên bỏ các tin của bot nằm đầu đoạn bị cắt.
    """
    recent = messages[-size:] if size > 0 else list(messages)
    while recent and not isinstance(recent[0], HumanMessage):
        recent = recent[1:]
    return recent


def retrieval_query(history: list[BaseMessage]) -> str:
    """Câu hỏi dùng để tra cứu: tin mới nhất kèm tin người dùng ngay trước đó (để câu hỏi nối tiếp vẫn đủ ý)."""
    questions = [message_text(m) for m in history if isinstance(m, HumanMessage)]
    return "\n".join(questions[-2:])


def build_chat_graph(llm: ChatModel, checkpointer: BaseCheckpointSaver, retriever: DocumentRetriever | None = None):
    def generate(state: MessagesState, writer: StreamWriter) -> dict:
        started = time.monotonic()
        history = window(state["messages"], settings.chat_history_window)

        hits: list = []
        if retriever is not None:
            try:
                hits = retriever.retrieve(retrieval_query(history))
            except Exception:  # noqa: BLE001 - lỗi tra cứu (hết hạn mức embedding...) không làm hỏng cả lượt chat
                logger.exception("Không tra cứu được văn bản quy định, trả lời không kèm ngữ cảnh")

        parts: list[str] = []
        # Phép tính ĐTBCTL/hạng tốt nghiệp làm bằng mã (LLM nhỏ hay chia sai); LLM chỉ diễn giải kết quả.
        calculation = build_gpa_report(llm, history)

        messages = [SystemMessage(content=build_system_prompt(hits, calculation)), *history]
        tool_log: list[dict] = []
        # Client nào gọi được công cụ (máy tính, so sánh số) thì dùng vòng lặp công cụ; còn lại stream thẳng.
        if getattr(llm, "supports_tools", False):
            answer_stream = stream_with_tools(llm, messages, tool_log=tool_log)
        else:
            answer_stream = llm.stream(messages)

        for chunk in answer_stream:
            text = message_text(chunk)
            if text:
                parts.append(text)
                writer({"token": text})  # đẩy từng đoạn ra cho client (chỉ có tác dụng khi stream_mode="custom")

        answer = "".join(parts)
        if not answer.strip():
            raise LLMError("Gemini returned an empty reply (có thể bị chặn nội dung)")

        reply = AIMessage(
            content=answer,
            additional_kwargs={
                "created_at": now_iso(),
                # Thời gian chờ chatbot trả lời, lưu cùng tin nhắn nên mở lại cuộc trò chuyện vẫn hiển thị.
                "duration_seconds": round(time.monotonic() - started, 1),
                # `retrieved`: các Điều đã đưa cho LLM làm ngữ cảnh (để kiểm thử/gỡ lỗi).
                # `sources`: các Điều câu trả lời thực sự nhắc tới, hiện cho người dùng làm tham chiếu.
                "retrieved": [{"article": h.article, "title": h.title} for h in hits],
                "sources": cited_sources(answer, hits),
                # Các lần gọi công cụ máy tính/so sánh trong lượt này (để kiểm thử/gỡ lỗi).
                "tools": tool_log,
            },
        )
        return {"messages": [reply]}

    builder = StateGraph(MessagesState)
    builder.add_node("generate", generate)
    builder.add_edge(START, "generate")
    builder.add_edge("generate", END)
    return builder.compile(checkpointer=checkpointer)
