"""Build Markdown/PDF from saved provider evidence and pytest XML; never calls a model."""
from pathlib import Path
import json
import re
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]


def f(value):
    return f"{value:,}".replace(",", ".")


def markdown_report():
    live = json.loads((ROOT / "reports/challenge-b-live/results.json").read_text(encoding="utf-8"))
    offline = json.loads((ROOT / "reports/challenge-b/results.json").read_text(encoding="utf-8"))
    suite = ET.parse(ROOT / "reports/pytest-challenge-b.xml").getroot().find("testsuite")
    passed = int(suite.attrib["tests"]) - int(suite.attrib.get("skipped", 0)) - int(suite.attrib.get("failures", 0)) - int(suite.attrib.get("errors", 0))
    b1 = live["b1"]
    native, code = (live["b2"]["runs"][mode] for mode in ("native", "code"))
    n, c = native["measurement"], code["measurement"]
    reduction = live["b2"]["reduction_percent_actual"]
    cp = b1["checkpoint"]
    text = f'''# BTVN7 - Challenge B: Context Management

SE373.R11 - Kỹ thuật xây dựng hệ thống Agentic AI. Nhóm 44. Ngày kiểm chứng: 26/10/2026.

## 1. Tổng quan

Challenge B mở rộng agent Challenge A hiện có bằng hai chức năng: B1 compact working context của một phiên dài thành checkpoint, rồi tiếp tục đúng task; B2 phân tích nhiều file log trong runtime để model chỉ nhận findings có giới hạn.

Kết quả chính trên model thật: B1 giữ được lỗi chưa giải quyết, constraints, lần thử thất bại và bước kế tiếp; B2 Code Mode đếm đúng 400 lỗi refresh_timeout. Tổng input do provider báo giảm từ {f(n['actual_input_tokens'])} xuống {f(c['actual_input_tokens'])} token ({reduction}%). Baseline xác định đúng loại lỗi nhưng chưa cung cấp count chính xác, nên không được đánh dấu hoàn thành task.

Không tạo lại project hay thay memory của A. Bản nộp submission_A được giữ nguyên. Báo cáo tham khảo cách chia mục tổng quan, môi trường, thiết kế và evaluation của báo cáo Challenge A; mọi số liệu B lấy từ artifact đã chạy.

## 2. Cấu hình môi trường và phạm vi dữ liệu

| Thành phần | Cấu hình đã dùng |
|---|---|
| Python | Conda SE373, Python 3.10.21; package metadata vẫn yêu cầu >=3.11 khi cài |
| Agent | LangChain create_agent / LangGraph; model/provider lấy từ Settings và .env |
| Provider | 9Router tại http://127.0.0.1:20128/v1; model {live['model']} |
| Web | FastAPI + HTML/JavaScript; trang B riêng tại /challenge-b |
| Dữ liệu B | History và log giả lập; memory/session trong data/challenge-b |
| Bảo mật cấu hình | Báo cáo và trace không chứa API key hoặc cấu hình client có secret |

Người dùng đã cho phép chạy provider thật với history/log fixture. Lần đầu endpoint chưa kết nối; router được khởi động bằng launcher hiện có. Các lượt kiểm chứng thành công lấy usage_metadata.input_tokens và output_tokens do provider trả. Đây là số provider/router báo, chưa được kiểm toán độc lập với tokenizer hoặc đối soát hóa đơn. Không biến token ước lượng thành usage thật.

## 3. Thiết kế agent và giao diện

### 3.1. Các thành phần tái sử dụng

Runtime.chat_with_trace, model client trong graph.py, tool registry, middleware inject AGENTS.md và index MEMORY.md, memory tools/lifecycle/store và PromptRecorder của A được tái sử dụng. Code Mode nối thêm tool run_code khi cấp thư mục log. Không thêm dependency runtime cho chức năng B.

### 3.2. B1 - Lựa chọn compact

Chọn checkpoint JSON có schema, kết hợp giữ nguyên human/system instructions, kế hoạch AI gần nhất nếu không quá 2.000 ký tự và không có tool calls, cùng archive đầy đủ. Agent hiện nạp history mỗi lượt nên thay active ngay tại Runtime là thay đổi nhỏ và dễ kiểm tra.

| Phương án | Ưu điểm | Hạn chế và quyết định |
|---|---|---|
| Sliding window | Nhanh, không gọi model thêm | Có thể mất constraint và kết luận thử nghiệm cũ; không dùng đơn độc |
| Cắt/deduplicate output | Deterministic, tốt với dòng lặp | Không bảo đảm giữ đúng dòng bằng chứng hoặc quan hệ giữa nhiều lượt |
| Summary tự do | Linh hoạt, nén được trạng thái | Khó phát hiện thiếu trường, có thể sai ngữ nghĩa |
| Checkpoint + giữ instructions/kế hoạch + archive | Có schema, truy vết được; phù hợp Runtime hiện tại | Có thêm lượt model; user history dài vẫn tăng; được chọn |
| Hierarchical summary / retrieval | Hữu ích khi history vượt cửa sổ một request | Thêm độ phức tạp, nhiều tầng có thể mất thông tin; chưa triển khai |

KEEP bằng code: user/system instructions và kế hoạch AI ngắn gần nhất. SUMMARIZE: goal, current_state, constraints, findings, failed_attempts, files, next_action, open_questions. DROP khỏi active: raw output lặp và các AI/tool messages đã được đại diện trong checkpoint. Archive gốc vẫn còn. Không cắt ToolMessage khỏi AI tool call tương ứng để đưa vào request mới.

Checkpoint được đưa vào system prompt chính và active history; prompt phân biệt trạng thái làm việc tạm với persistent memory. recall trống không có nghĩa là chưa có findings hay thử nghiệm. Chỉ ghi active mới khi checkpoint hợp lệ và nhỏ hơn. Schema lỗi hoặc không giảm kích thước giữ nguyên context; usage của lượt compact lỗi vẫn được ghi nhận.

Phân tích lựa chọn đầy đủ và các trường hợp kém hiệu quả: [CONTEXT_COMPACTION_DECISION.md](CONTEXT_COMPACTION_DECISION.md).

### 3.3. B2 - Luồng dữ liệu

Model nhận câu hỏi và mô tả tool, sinh code gửi run_code. Runtime đọc raw logs nội bộ, lọc theo level/substring, đếm từng error_type và chọn top-k. Chỉ findings có count, file, dòng và snippet ngắn được trả cho model. Model dùng findings để trả lời cuối.

```python
rows = read_logs()
errors = select(rows, level="ERROR")
result = summarize(errors, top=5)
```

Interpreter chỉ nhận assignment và ba API trên; không exec/eval/import/open/network. Chỉ đọc .log UTF-8 trực tiếp trong thư mục được cấp, không đi vào thư mục con. Format: timestamp LEVEL error_type message. Dòng không parse được được đếm riêng.

Giới hạn: 100 file; 1.000 directory entries; 8 MiB input; 50.000 records; 3 giây kiểm tra hợp tác; tối đa 5 nhóm, 8 tên file/nhóm, 2 snippets/nhóm, 120 ký tự/snippet; 12.000 bytes output. Dữ liệu thiếu hoặc lỗi đọc được đánh dấu complete=false. Đây không phải OS/container sandbox; time budget không ngắt cưỡng bức I/O và path checks chưa chống hoàn toàn TOCTOU.

### 3.4. Trang B riêng theo kiểu chat

Trang /challenge-b có một luồng hội thoại và ô nhập, không trộn bảng memory Challenge A. Usage hiển thị tổng input/output của phiên và lượt gần nhất, cộng mọi model round và lượt compact. Context hiển thị input ước lượng cho lượt kế, gồm active messages, instructions và tool schemas, chưa gồm tin nhắn đang gõ.

Ngưỡng demo mặc định 8.000 token ước lượng; cảnh báo từ 80%, đổi màu khi vượt ngưỡng và có nút compact. Người dùng có thể chỉnh ngưỡng. Đây không phải context limit đã xác minh của model và không tự chặn gửi. Sau compact, chat hiển thị working context trước/sau, phần trăm giảm và checkpoint mở rộng. Tool/findings/context request nằm trong phần bằng chứng có thể mở.

History model nằm ở data/challenge-b/sessions; timeline UI và usage nằm ở data/challenge-b/chat-ui. Các thông báo giao diện không bị gửi trở lại model như hội thoại thật. Baseline mở đoạn chat riêng để giữ cùng task và không hưởng findings của Code Mode.

### 3.5. Chế độ Offline không model

Trang B mặc định Offline · 0 API; có lựa chọn Provider .env riêng theo từng chat, không tự fallback sang provider. Offline không cần key/model và không khởi tạo client LLM. Compact dùng schema cùng trích dẫn theo marker bước kế tiếp, failed-attempt lines và nguồn file/dòng; giữ nguyên user/system instructions và kế hoạch ngắn. Nó không suy luận ngữ nghĩa tổng quát. B2 chạy template code qua runtime thật rồi render count/evidence bằng code, không giả vờ model sinh code.

Usage Offline bằng 0 vì không có request, không phải usage giả do provider trả. Context vẫn là kích thước giả định để quan sát trước/sau. Baseline Offline chỉ đối chứng dung lượng raw output với findings, không chứng minh chất lượng LLM hay phần trăm tiết kiệm hóa đơn. Có test chặn build_model và chạy trọn luồng không key. Sáu kịch bản thao tác và đáp án chuẩn nằm trong CHALLENGE_B_SCENARIOS.md.

## 4. Evaluation

### 4.1. B1 - Compact và continuation bằng model thật

Kịch bản có 1.600 dòng debug lặp, lỗi 401 chưa sửa, constraint giữ /refresh và không log token, lần thử timeout 30s không hiệu quả, bằng chứng auth.py:184 / race.log:7 và kế hoạch thêm concurrency test. Các file/dòng này thuộc kịch bản giả lập, không phải lỗi đã tìm thấy trong repository.

| Đại lượng | Trước | Sau |
|---|---:|---:|
| Active context serialized UTF-8 bytes | {f(b1['before']['serialized_bytes'])} | {f(b1['after']['serialized_bytes'])} |
| Active tokens ước lượng, ceil(bytes/4) | {f(b1['before']['estimated_tokens'])} | {f(b1['after']['estimated_tokens'])} |

Giảm {((b1['before']['estimated_tokens']-b1['after']['estimated_tokens'])/b1['before']['estimated_tokens']*100):.2f}% active tokens ước lượng. Không coi đây là giảm tổng chi phí cả phiên. Provider báo lượt compact dùng {f(sum(u['input_tokens'] for u in b1['compaction_usage']))} input tokens; continuation dùng {f(b1['continuation_input']['actual_input_tokens'])} input tokens qua {b1['continuation_input']['requests']} lượt model. Lượt compact phát sinh thêm chi phí.

Checkpoint thực tế:

```json
{json.dumps(cp, ensure_ascii=False, indent=2)}
```

Phản hồi continuation thực tế:

{b1['continuation_reply']}

Nhận xét: agent tiếp tục đúng đường dẫn test và thứ tự bước, giữ constraints và nêu đúng timeout không hiệu quả. Request spy xác nhận raw debug không xuất hiện trong continuation. Archive/restart/preservation còn được kiểm tra tự động. Kết quả này chỉ áp dụng tình huống đã thử, không chứng minh summary luôn đúng.

### 4.2. B2 - Code Mode và baseline trên cùng task

Câu hỏi cho cả hai phương pháp: {live['b2']['question']}

Fixture gốc có 4 log và 1 file .txt không liên quan. Mỗi log lặp 80 lần để kiểm tra context; tổng 1.040 dòng, trong đó 80 dòng không parse và 720 bản ghi ERROR. Không deduplicate trước khi đếm vì dòng lặp cũng là lần xuất hiện theo định nghĩa fixture.

| Loại lỗi | Count gốc | Count khi nhân 80 |
|---|---:|---:|
| refresh_timeout | 5 | 400 |
| db_connection | 3 | 240 |
| invalid_token | 1 | 80 |

| Phương pháp | Tổng lượt model | Input provider báo | Input ước lượng |
|---|---:|---:|---:|
| Native raw-output baseline | {n['requests']} | {f(n['actual_input_tokens'])} | {f(n['estimated_input_tokens'])} |
| Code Mode | {c['requests']} | {f(c['actual_input_tokens'])} | {f(c['estimated_input_tokens'])} |

Giảm input provider báo: ({n['actual_input_tokens']} - {c['actual_input_tokens']}) / {n['actual_input_tokens']} x 100 = {reduction}%. Tổng bao gồm tất cả request trong task, không chỉ lượt trả lời cuối. Ước lượng tính JSON messages, tool-call metadata và tool schemas của từng request bằng UTF-8 bytes/4.

Phản hồi Code Mode:

{code['reply']}

Phản hồi native baseline:

{native['reply']}

Nhận xét: Code Mode quét đủ 4 file, trả đúng các count 400/240/80; evidence refresh_timeout tại auth.log:1 và billing.log:2 khớp nguồn. Request spy không thấy marker INFO hoặc toàn bộ raw log trong Code Mode. Các snippet ngắn làm bằng chứng vẫn được phép. Baseline không cung cấp count chính xác theo yêu cầu; vì vậy kết quả tổng thể ghi completed with failed quality checks, không trình bày cả hai là PASS. So sánh trên cùng task được yêu cầu, nhưng hai phương pháp không có chất lượng đầu ra tương đương trong lần chạy này.

### 4.3. Thất bại ban đầu và cách sửa

Lần live trước sửa được giữ trong [attempt-before-fix.json](reports/challenge-b-live/attempt-before-fix.json). Checkpoint bỏ tests/test_refresh.py trong next_action; continuation còn nói chưa biết cách đã thử dù checkpoint chứa timeout. Một findings còn tự đếm số dòng debug không cần thiết. Bộ test model giả ban đầu chưa phát hiện các lỗi này.

Đã sửa: giữ kế hoạch AI ngắn gần nhất nguyên văn; yêu cầu summary giữ đường dẫn và thứ tự hành động, không tự bịa count; inject checkpoint vào system prompt chính và phân biệt với persistent memory. Lần sau sửa đạt B1 theo kiểm tra định danh và đọc phản hồi. Chấp nhận tăng context một ít để giữ khả năng tiếp tục đúng task. Không sửa baseline để che kết quả chưa đạt.

Một lần thao tác chat UI bổ sung được lưu trong [ui-chat-observation.json](reports/challenge-b-live/ui-chat-observation.json): model vẫn giữ file và constraint nhưng đề xuất kiểm tra auth.py trước khi thêm test, khác thứ tự kế hoạch gốc. Đây là lỗi chất lượng continuation còn lại, không tính là PASS đầy đủ về thứ tự. Vì vậy chỉ kết luận lần CLI ở mục 4.1 đạt, không khẳng định mọi lần B1 đều đúng. Chưa thử tiếp bằng model theo yêu cầu tiết kiệm token; các kiểm tra sau đó chỉ offline.

### 4.4. Kiểm thử offline và hồi quy

Kết quả cuối: {passed} passed, {suite.attrib.get('skipped', '0')} xfailed. Các test chạy không cần API key. Baseline A trước thay đổi: 65 passed, 3 xfailed. Ba xfail đã biết (timestamp MemoryEntry, heuristic thay thế, Markdown heading trong history) được giữ, không coi là PASS.

Test B bao gồm schema lỗi, compact không giảm kích thước, provider lỗi, archive/restart/delete, continuation, kế hoạch gần nhất, golden counts/evidence, AST/API không được cấp, lỗi file/path escape, input/time/output budget, request spy, namespace A/B, natural chat, context meter, đủ/thiếu usage, và usage của compact thất bại. Các test web cần Windows asyncio socketpair; chạy ngoài sandbox và dùng basetemp trong workspace để tránh hạn chế môi trường.

Demo offline được chạy lại sau sửa: B1 {f(offline['b1']['before']['estimated_tokens'])} → {f(offline['b1']['after']['estimated_tokens'])} estimated active tokens; B2 {f(offline['b2']['measurements']['native']['estimated_input_tokens'])} → {f(offline['b2']['measurements']['code']['estimated_input_tokens'])} estimated total input. Model có kịch bản chỉ chứng minh harness/data flow, tách khỏi kết quả provider thật ở trên.

## 5. Cách chạy và bằng chứng

```powershell
# Từ memory_agent, Python có dependencies
.\\run_web.cmd
# Mở http://127.0.0.1:8000/challenge-b
python scripts/challenge_b_demo.py --output reports/challenge-b
python scripts/challenge_b_live.py --output reports/challenge-b-live
python -m pytest -q --basetemp=data/pytest-b --junitxml=reports/pytest-challenge-b.xml
```

Trang B: chọn Phiên mẫu, quan sát cảnh báo context, Compact rồi gửi “Tiếp tục từ bước kế tiếp”. Để thử B2, chọn câu hỏi log chuẩn và gửi; mở tool/findings để đối chiếu. Native baseline nằm trong menu Cách đo, mở chat riêng. Dữ liệu B sống qua reload; không dùng namespace A.

Artifact nguồn: [kết quả live](reports/challenge-b-live/results.json), [lần live chưa đạt](reports/challenge-b-live/attempt-before-fix.json), [kết quả offline](reports/challenge-b/results.json), [request spy offline](reports/challenge-b/code-prompts.json), [pytest XML](reports/pytest-challenge-b.xml). Ảnh giao diện trong reports/challenge-b/screenshots là các lần thao tác UI riêng, có thể khác vài token do model sinh checkpoint khác; không trộn số UI với bảng CLI.

Module mới/chính: context.py, code_mode.py, metrics.py, challenge_b_lab.py, challenge_b_scenarios.py, ui/challenge_b.py và ui/challenge_b_chat.html. Runtime/graph/config/tracing/session deletion được mở rộng; memory store/tools của A không đổi.

## 6. Giới hạn và kết luận

Trong lần CLI đã ghi, B1 nén active và tiếp tục đúng task; lần UI bổ sung vẫn lệch thứ tự nên cần người dùng kiểm tra kế hoạch; B2 trả đúng count/evidence với input thấp hơn baseline do provider báo. Chưa benchmark nhiều model, nhiều dạng task hoặc điểm hòa vốn chi phí compact. Bytes/4 có thể khác đáng kể usage provider, nhất là qua router; không coi các đại lượng là một.

Chưa có OS sandbox, hard timeout I/O, retrieval archive tự động hoặc khóa ghi liên process. Compact kích hoạt thủ công; giao diện cảnh báo theo ngân sách demo, không theo context limit provider đã xác minh. Human history quá dài vẫn tăng; parser log chỉ hỗ trợ format công bố. Độ đúng ngữ nghĩa của summary và lựa chọn tool vẫn phụ thuộc model. Các kết quả không bảo đảm đúng với mọi cách diễn đạt.
'''
    (ROOT / "CHALLENGE_B_REPORT.md").write_text(text, encoding="utf-8")
    return text



if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    markdown_report()
    print(ROOT / "CHALLENGE_B_REPORT.md")
