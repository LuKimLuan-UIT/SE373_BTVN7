# Challenge A — Kịch bản kiểm thử persistent memory

Ngày thực hiện: 22/10/2026. Phạm vi: lưu quy ước qua session, đọc lại sau restart,
thay thế quy ước lỗi thời và kiểm tra context thực sự được gửi tới model.

**Cập nhật cuối:** đã chạy 4/4 bước Challenge A với model thật và 5/5 tình huống
chat tự nhiên (gồm trường hợp không lưu). Phiên bản cuối có **61 pass, 3 xfail**
trong SE373. Chi tiết phiên bản mới và hướng dẫn chụp ảnh ở mục 9 bên dưới.

## 1. Mục tiêu và tiêu chí đạt

1. Session `s1` ghi quy ước đăng nhập dùng JWT; session mới `s2` đọc được từ memory,
   không cần nhận lịch sử của `s1`.
2. Khi đổi sang session cookie, session mới chỉ nhận quy ước hiện hành trong index.
   Mục JWT còn trong file chi tiết với trạng thái `superseded` và liên kết tới mục mới.
3. Dữ liệu tồn tại khi tạo lại runtime và khi khởi động một process Python độc lập.
4. Có bằng chứng từ file Markdown, kết quả tool và context, thay vì chỉ dựa vào câu
   trả lời của chatbot.

## 2. Cơ chế cần phân biệt

`Runtime.chat` đọc `data/sessions/<thread_id>.md` mỗi lượt và lưu lại sau khi agent
trả lời. Đây là lịch sử riêng của session. Quy ước dùng chung giữa session nằm tại
`data/memory/<user_id>/`: `MEMORY.md` là index, `<topic>.md` là chi tiết.

Agent được dựng bằng `create_agent`, có các tool `remember`, `recall`, `update`,
`supersede`, `forget`. Namespace dài hạn có dạng `("memory", user_id, topic)`;
`thread_id` được dùng làm nguồn của thông tin khi `Runtime.chat` ghi memory.

Với `MEMORY_PLACEMENT=system`, middleware đưa index vào system prompt. Với `end`,
middleware thêm digest ở cuối danh sách message. `injected_context()` và CLI
`context` chỉ cho thấy system prompt; ở chế độ `end` cần quan sát message thực tế
đến model mới xác nhận được digest. Các test về thứ tự prompt không đo cache hit,
TTL hay chi phí thực tế của nhà cung cấp.

## 3. Môi trường và cách chạy

Theo yêu cầu, dùng Miniconda `SE373` tại
`C:\Users\Asus\miniconda3\envs\SE373\python.exe` (Python 3.10.21).
`pyproject.toml` khai báo Python >=3.11: vì vậy chạy test từ source không có nghĩa
là đã xác nhận cài package được bằng `pip install -e .` trong Python 3.10.
Không nâng phiên bản Python của môi trường hiện tại.

Tại thư mục `memory_agent`, trong terminal đã có Conda:

```powershell
conda activate SE373
python -m pytest -q -ra
python -m pytest tests/test_challenge_a.py -v -rx
```

Nếu terminal chưa nhận `conda`, dùng trực tiếp executable:

```powershell
& C:/Users/Asus/miniconda3/envs/SE373/python.exe -m pytest -q -ra
```

Test dùng thư mục tạm, model giả và tool thật; không cần gửi API hay ghi đè memory
đang sử dụng. File `tests/test_challenge_a.py` bổ sung kiểm chứng bằng process độc
lập, context session mới, lỗi ghi file và bốn tình huống lỗi đã biết. Các lỗi đã
biết dùng `xfail(strict=True)`: xfail không phải PASS; nếu lỗi được sửa, XPASS sẽ
khiến lượt chạy báo lỗi để nhắc cập nhật test.

## 4. Ma trận kịch bản

| ID | Thao tác | Kỳ vọng / bằng chứng | Kiểm thử |
|---|---|---|---|
| CA-01 | Agent s1 gọi remember(auth, JWT) | Có auth.md, MEMORY.md và tool trả thành công | test_agent_remembers_convention_across_sessions |
| CA-02 | Runtime mới, session s2 gọi recall(auth) | Tool trả JWT từ file của cùng user | test_agent_remembers_convention_across_sessions |
| CA-03 | Writer process kết thúc; reader process mới đọc cùng thư mục | Nội dung và source s1 còn nguyên | test_memory_survives_separate_python_processes |
| CA-04 | s2 gọi supersede(key JWT, cookie); s3 hỏi lại | System prompt s3 có cookie, không có JWT hoặc câu đổi quy ước của s2; JWT cũ vẫn superseded | test_new_session_receives_only_current_convention |
| CA-05 | Ghi s1, tạo lại runtime, chat tiếp s1 | Model thấy câu hỏi cũ và câu mới | test_history_is_reused_across_turns |
| CA-06 | Tắt long-term memory | Context không chứa index; lịch sử session vẫn là cơ chế riêng | test_context_without_memory_feature |
| CA-07 | Đổi user u1 sang u2 | u2 không đọc được entry của u1 qua manager | test_memory_isolated_per_user |
| CA-08 | Update nội dung | Nội dung đổi, thời điểm tạo phải giữ nguyên và không rỗng | test_update_keeps_created_at + CA-B01 |
| CA-09 | Forget rồi mở lại store | Key biến mất, index không còn quy ước | test_forget_survives_reopening_store |
| CA-10 | remember có từ khóa trùng nhiều | Mục cũ superseded, chỉ còn một mục active | test_conflict_auto_supersedes_old_entry |
| CA-11 | remember(force=True) | Hai quyết định cùng active khi chủ động yêu cầu | test_force_keeps_both_entries |
| CA-12 | Ghi 40 mục | Context có tối đa 12 dòng tóm tắt; chi tiết đọc qua recall | test_index_is_short_and_details_not_injected |
| CA-13 | Không đổi memory, dựng context hai lần | Hai chuỗi context giống nhau | test_context_is_byte_identical_between_turns |
| CA-14 | Placement end | Model nhận SystemMessage digest cuối danh sách | test_placement_end_puts_digest_after_history |
| CA-15 | Store.put ném PermissionError | Tool báo không ghi được; không có entry mới | test_failed_write_is_reported_by_tool |
| CA-16 | Lịch sử có heading Markdown | Nội dung đọc lại phải nguyên vẹn | CA-B04 |

CA-06 chỉ kiểm tra context bị tắt; chưa phải bằng chứng model thật sẽ trả lời
"không biết". CA-07 chỉ kiểm tra namespace memory, chưa kiểm tra phân quyền API
hay cách ly lịch sử session theo user.

## 5. Các lỗi cần tái hiện

### CA-B01 — Timestamp không xuất hiện ở MemoryEntry

Sau `remember`, file có `created_at` và `updated_at`, nhưng
`MarkdownMemoryStore._to_item` loại hai trường khỏi `value` và đặt chúng ở thuộc
tính của `SearchItem`. `MemoryManager.entries` lại đọc timestamp từ `item.value`,
nên trả chuỗi rỗng. Test cũ so sánh thời điểm trước/sau update có thể vẫn pass
vì cả hai đều rỗng. Test mới so trực tiếp với timestamp thực sự của store.

Đề xuất: đọc `item.created_at` / `item.updated_at` khi tạo `MemoryEntry`.

### CA-B02 — Nguồn của mục thay thế mang session cũ

Ghi JWT từ s1; đặt `current_source=s2`; gọi tool `supersede` sang cookie.
`MemoryManager.supersede` truyền `source or entry.source` vào `remember`, do đó
giá trị s1 ngăn `remember` dùng nguồn hiện tại s2. Nội dung đổi nhưng audit nguồn
không phản ánh session thực hiện thay đổi.

Đề xuất: ưu tiên source được truyền rõ, tiếp đến current_source, sau cùng mới
fallback về nguồn cũ nếu cần. Giữ nguồn cũ trên entry bị thay thế.

### CA-B03 — Hai quy ước mâu thuẫn có thể cùng active

Gọi `remember("auth", "Dùng JWT")`, sau đó
`remember("auth", "Chuyển sang session cookie")`. Bộ phát hiện xung đột dùng
Jaccard của từ dài hơn hai ký tự, ngưỡng 0.4. Hai cách diễn đạt này không có từ
khóa chung đủ nhiều, nên không tự thay thế. Vì vậy phát biểu "không bao giờ có hai
mục mâu thuẫn cùng hiệu lực" trong README/prompt vượt quá điều mã đang bảo đảm.

Đề xuất: với thay đổi đã xác định, dùng `supersede` theo key; nếu cần tự phát hiện
thì bổ sung cách nhận diện quy ước có cấu trúc hoặc so sánh ngữ nghĩa. Không chỉ
hạ ngưỡng vì dễ thay thế nhầm hai quyết định khác nhau.

### CA-B04 — Heading làm mất nội dung lịch sử

Lưu HumanMessage chứa `## Authentication`. `load_history` xử lý mọi dòng `## `
như ranh giới role, nhưng chỉ nhận `User`/`Assistant`; phần phía sau heading khác
bị bỏ qua. Đây là trường hợp thường gặp khi hội thoại có nội dung Markdown.

Đề xuất: dùng định dạng phân định message có escaping hoặc metadata tách biệt,
kèm test roundtrip nội dung Markdown.

## 6. Kịch bản demo Challenge A với model thật (chưa thực hiện đầy đủ)

Cấu hình endpoint và khóa ban đầu được lưu riêng trong `.env` đã gitignore. Không
đưa khóa vào tài liệu. Ở lượt kiểm thử ban đầu, `MODEL_NAME` để trống vì chưa xác
minh được model từ endpoint.
Lượt gọi danh sách model tới miền tunnel do người dùng cung cấp bị bộ duyệt tự
động chặn do nguy cơ gửi credential đến tunnel công khai. Vì vậy không có kết quả
API thật hay bằng chứng về khả năng tự chọn tool của model thật.

Khi có kết nối API được phép và `MODEL_NAME` hợp lệ, thực hiện trên dữ liệu demo:

1. Chạy CLI `chat --thread ca-s1 "Dự án này dùng JWT để đăng nhập"`.
2. Chạy CLI `memory`, chụp index và auth.md; lấy key thực tế, không đoán key.
3. Dùng ca-s2 hỏi "Dự án này dùng gì để đăng nhập?"; kiểm tra recall và nội dung JWT.
4. Dùng ca-s3 yêu cầu thay JWT bằng session cookie; kiểm tra mục cũ superseded,
   mục mới active, nguồn và thời điểm.
5. Dừng ứng dụng; khởi động lại; dùng ca-s4 hỏi quy ước hiện hành. Kỳ vọng cookie.
6. Chạy CLI `context` với placement system; lưu bằng chứng index hiện hành.

Trong môi trường Conda, tiền tố lệnh CLI là:

```powershell
python scripts/demo_cli.py chat --thread ca-s1 "Dự án này dùng JWT để đăng nhập"
python scripts/demo_cli.py memory
python scripts/demo_cli.py context
```

Không dùng `wipe`/`reset` trên dữ liệu đang sử dụng để chuẩn bị demo.

## 7. Kết quả chạy

Lệnh thực thi: Python của Miniconda SE373, `-m pytest -q -ra
--junitxml=reports/pytest-se373.xml`. Kết quả: **54 passed, 4 xfailed trong 15.09s**,
exit code 0. Bao gồm 50 test ban đầu, 4 test bổ sung đạt và 4 test tái hiện lỗi đã
biết. Bốn xfail tương ứng CA-B01 tới CA-B04; chúng vẫn là yêu cầu chưa đạt.
Bằng chứng máy đọc được: [reports/pytest-se373.xml](reports/pytest-se373.xml).

`python -m pip check` trong cùng môi trường trả `No broken requirements found`.
Dependency kiểm thử đã được cài vào SE373; langchain-core được cập nhật từ 1.6.4
lên 1.6.13 và langsmith từ 0.14.0 lên 0.14.12 do yêu cầu của langchain-openai
1.7.2. Các lần chạy này không dùng bản dependency được khóa bằng `uv.lock`.

Không sửa mã nghiệp vụ trong lượt kiểm thử này. Model giả trả tool call theo kịch
bản định sẵn: kết quả chứng minh pipeline tool/store/context hoạt động theo input
đã chọn, chưa chứng minh model thật tự hiểu câu nói và tự chọn đúng tool.

## 8. Bổ sung: 9Router local và kiểm tra API thật

Đã cài npm global `9router@0.5.104` bằng Node.js gốc, chạy nền tại
`http://127.0.0.1:20128`. Memory Agent chạy bằng Python của Conda SE373 tại
`http://127.0.0.1:8000`. Script khởi động lại hai dịch vụ:
`scripts/start_local.ps1`.

`.env` hiện trỏ tới `http://127.0.0.1:20128/v1`, dùng khóa nội bộ riêng được tạo
qua API của 9Router và model `oc/glm-5.3-flash-free` từ danh sách OpenCode hiện
hành. Không cần tài khoản OpenCode. Cấu hình trước đó được sao lưu trong
`data/config-backups/env.before-9router`, cũng được gitignore.

Đã xác nhận hai mức: ChatOpenAI từ SE373 nhận `OK`; sau đó POST `/api/chat` của
ứng dụng web với session `router-smoke-20261022` cũng trả `OK`. Router log cho
thấy lượt ứng dụng có 5 tool được khai báo. Đây là kiểm tra kết nối, chưa kiểm
chứng model thật tự thực hiện đủ chuỗi nhớ/thay thế/đọc lại của Challenge A.

Một số model miễn phí cũ trong catalog 9Router trả lỗi không khả dụng hoặc 410
deprecated. Model đã chọn trả lời thành công; một lượt gặp 429 rồi retry thành
công. Không bảo đảm độ sẵn sàng hay hạn mức của dịch vụ miễn phí.

Không gửi khóa của endpoint tunnel trước đó qua 9Router. Lần chặn của bộ duyệt
tự động đối với endpoint đó vẫn chưa được giải quyết.

## 9. Model Codex thật, chat tự nhiên và harness (kết quả cuối)

### Lựa chọn model

Dùng `cx/gpt-6-luna` qua `http://127.0.0.1:20128/v1`, tài khoản Codex đã được người
dùng kết nối với 9Router, API key local mới lưu riêng trong `.env`. Không công bố
key, token đăng nhập hay email tài khoản trong bằng chứng.

Chọn Luna cho bài tập ít tool, quyết định ngắn và cần tiết kiệm. Theo
[bảng giá Codex chính thức](https://learn.chatgpt.com/docs/pricing), Standard có
mức tham chiếu mỗi triệu token input/cached-input/output: Luna 2.5/0.25/12.5
credits, Terra 50/5/300. Đây là bảng tham chiếu credit, không phải hoá đơn thực tế
của tài khoản subscription hay cam kết quota khi gọi qua gateway. Không benchmark
Terra: Luna đã hoàn thành toàn bộ kịch bản, không cần tốn thêm lượt so sánh.

### Hai lượt kiểm chứng

Lượt đầu trong `reports/challenge-live/`: 4/4 bước ghi JWT, recall session mới,
supersede sang cookie và recall sau restart đều đạt. Lượt này có yêu cầu lưu rõ
ràng. Bước 3/4 ban đầu bị bộ kiểm tra chuỗi đánh dấu sai vì mục hiện hành vẫn
nhắc "cookie thay JWT"; đã sửa kiểm tra theo key/status/superseded_by rồi đánh
giá lại trace gốc, không gọi lại model hay sửa dữ liệu gốc.

Lượt cuối dùng câu chat tự nhiên, không yêu cầu "lưu/nhớ", namespace
`challenge-a-natural-20261022`, model tự chọn tool:

| Session | Câu người dùng | Tool thực tế | Kết quả | Thời gian |
|---|---|---|---|---|
| natural-s1 | Bên mình đã chốt cơ chế đăng nhập của dự án là JWT. | remember | Ghi JWT, source natural-s1 | 3.98s |
| natural-s2 | Dự án mình đang đăng nhập bằng cơ chế nào? | recall | Trả JWT, không ghi thêm | 3.58s |
| natural-s3 | Nhóm vừa thống nhất bỏ JWT và chuyển hẳn sang session cookie cho đăng nhập. | recall → supersede | JWT cũ superseded, cookie active, source mới natural-s3 | 6.30s |
| natural-s4 | Hiện tại dự án mình dùng cơ chế đăng nhập nào? | recall | Sau restart vẫn trả cookie | 3.23s |
| natural-s5 | Chào bạn, hôm nay mình hơi buồn ngủ. | Không gọi tool | Phản hồi bình thường, không ghi memory | 1.46s |

Tất cả các session này nạp **0 message lịch sử** ở lần gọi đầu; mỗi bước chạy
trong process SE373 riêng, PID lần lượt 33892, 36268, 28152, 24116, 2980.
Ứng dụng web cũng đã restart giữa bước 3 và 4; không restart router hay xoá file.
Nguồn context có cookie ngay trước lần model đầu tiên của bước 4.

Tổng usage do gateway trả cho 5 bước: **18,504 input + 253 output token**, 10 lần
gọi model (bao gồm vòng tool), khoảng 0.0494225 credits nếu áp dụng mức tham chiếu
Standard ở trên và không có cached input. Gateway không báo cached token ở các
trace này; không suy ra chi phí/quota thực tế từ con số đó. Lượt đầu 4 bước có
14,730 input + 247 output token, không gộp vào tổng 5 bước cuối.

Bằng chứng máy đọc được:

- [reports/challenge-natural/step-1.json](reports/challenge-natural/step-1.json)
  tới `step-5.json`: kết quả, checks, PID, usage, thời gian.
- `reports/challenge-natural/trace-1.json` tới `trace-5.json`: câu hỏi/phản hồi,
  tool call/result, snapshot trước/sau, context thực gửi model và source.
- File nghiệp vụ: `data/memory/challenge-a-natural-20261022/project.md`,
  `MEMORY.md`, cùng lịch sử `data/sessions/natural-s*.md`.
- Trace UI: `data/sessions/traces/*.json`; vẫn mở được sau restart.

### Thay đổi theo yêu cầu thử nghiệm

Web mặc định là chat bình thường: ô nhập nhiều dòng, Enter gửi, Shift+Enter xuống
dòng, tạo session mới và chọn lại session cũ. Nút **Bằng chứng** mở panel theo nhu
cầu. **Chế độ chụp ảnh** ẩn sidebar/composer, hiện quyết định ghi và memory
trước/sau của đúng lượt chat. Không dùng các nút kịch bản để điều khiển model.
[SCREENSHOT_GUIDE.md](SCREENSHOT_GUIDE.md) chứa 5 câu để copy vào ô chat.

Model nhận diện quyết định bền vững theo ý nghĩa. Harness kiểm tra nội dung không
rỗng, topic hợp lệ, key thay thế tồn tại trong namespace user và còn active;
không tự supersede dựa trên từ khóa trong đường gọi tool của agent. Khi thay
thế, chỉ key được model chỉ ra mới bị đánh dấu superseded. Model vẫn có thể hiểu
sai ngữ nghĩa: harness này là kiểm tra cấu trúc/trạng thái, không phải model phán
xét thứ hai và không bảo đảm phát hiện mọi mâu thuẫn.

Đã sửa CA-B02: nguồn của mục thay thế ưu tiên session hiện tại. Test đó hiện PASS.
CA-B01 (timestamp trong MemoryEntry) và CA-B04 (heading trong lịch sử) còn xfail.
CA-B03 còn xfail khi gọi trực tiếp API thấp `MemoryManager.remember` dùng heuristic
cũ; đường tool dành cho agent đã bỏ cơ chế đoán xung đột đó. Kiểm thử cuối:
**61 passed, 3 xfailed trong 9.76s**. Test mới kiểm tra đề xuất có key sai/topic
sai bị từ chối mà không ghi, update rỗng bị từ chối, hai quyết định có nhiều từ
giống nhau không tự bị thay thế, cùng tính đúng đắn của trace/prompt callback.
