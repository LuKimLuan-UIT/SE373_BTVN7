# Lựa chọn thuật toán compact cho agent hiện tại

Ngày đánh giá: 26/10/2026. Đây là quyết định theo kiến trúc và workload của project,
không phải kết luận một thuật toán luôn tốt nhất cho mọi agent.

## Bối cảnh và tiêu chí

Agent dùng `create_agent`, nạp lại hội thoại từ Markdown ở mỗi lượt. `AGENTS.md`
và index `MEMORY.md` được middleware inject; chi tiết memory chỉ đọc qua `recall`.
Không có tokenizer, vector store hay sandbox Python sẵn có. Provider được chọn
qua cấu hình và có thể thay đổi, nên không thể dựa vào API compact riêng của một model.

B1 cần giữ một lỗi chưa sửa, constraints, bằng chứng, kết luận thử nghiệm thất bại
và next action. Workload kiểm thử có nhiều output debug lặp lại; chính output đó
chiếm phần lớn context. Ưu tiên: giữ instructions chính xác; giữ trạng thái công việc;
khả năng kiểm tra/restart; giảm input; ít thay đổi Challenge A; chi phí/độ trễ.

## Các phương án đã cân nhắc

| Phương án | Ưu điểm | Nhược điểm trong project này | Quyết định |
|---|---|---|---|
| Giữ nguyên history | Không thêm lượt summary; giữ nguyên nội dung đã lưu | Input tăng qua từng lượt; log lặp vẫn gửi lại | Là baseline, không giải B1 |
| Sliding window: giữ N tin nhắn cuối | Đơn giản, nhanh, không gọi model thêm | Constraint hoặc lần thử thất bại ở đầu phiên có thể biến mất; cắt giữa AI/tool làm request không hợp lệ | Không dùng đơn độc |
| Cắt/deduplicate output tool theo số dòng | Deterministic; hiệu quả với log trùng, ít latency | Dòng cuối/đầu không nhất thiết chứa bằng chứng; không tự tổng hợp goal, trạng thái, kết luận của nhiều lượt | Không chọn làm thuật toán B1 chính; B2 dùng xử lý dữ liệu có cấu trúc thay cho raw output |
| Summary văn xuôi bằng LLM | Linh hoạt, nén được quan hệ giữa các lượt | Khó kiểm tra trường bị bỏ sót; có thể trộn giả thuyết với fact hoặc làm mất constraint | Không dùng độc lập |
| Checkpoint JSON bằng LLM + giữ user/system instructions/kế hoạch gần nhất + archive | Kiểm tra schema; giữ instructions bằng code; trạng thái có nguồn và next action; tái sử dụng provider/agent hiện có | Thêm một lượt LLM; schema không chứng minh ngữ nghĩa; giữ toàn bộ user text làm context tiếp tục tăng | **Chọn cho B1** |
| Hierarchical/chunked summarization | Xử lý được history lớn hơn cửa sổ một request | Nhiều lượt model; thông tin có thể mất qua nhiều tầng; phức tạp hơn nhu cầu demo hiện tại | Chưa triển khai; cần nếu phiên quá lớn để compact một lượt |
| Retrieval/vector memory thay history | Chỉ lấy phần liên quan; hữu ích ở tập dữ liệu lớn | Phải thêm retrieval/index; có thể bỏ sót quan hệ goal–constraint–thử nghiệm; không nên biến trạng thái debug tạm thành memory lâu dài của A | Không dùng thay checkpoint trong phạm vi này |

Các nhận xét về phương án chưa triển khai là phân tích thiết kế, **không phải**
kết quả benchmark đối đầu đã chạy.

## Thuật toán được triển khai

1. Người dùng gọi `Runtime.compact`, CLI `compact`, hoặc `POST /api/compact`
   giữa các lượt chat đã hoàn tất. Không cắt graph khi còn tool call đang chờ.
2. Đọc `active` và `archive`. Với session A cũ chưa có JSON, lấy history Markdown.
3. Gửi active context và schema cho **model đang cấu hình**. Không nạp toàn bộ
   memory dài hạn; middleware tiếp tục quản lý memory riêng khi chat.
4. Model viết `goal`, `current_state`, `constraints`, `findings`, `failed_attempts`,
   `files`, `next_action`, `open_questions`. Prompt yêu cầu giữ nguồn và phân biệt giả thuyết.
5. Pydantic kiểm tra đủ trường, kiểu, giới hạn kích thước và trường rỗng.
   `next_action` phải có tối thiểu 12 ký tự; đây chỉ là kiểm tra cấu trúc,
   không phải bộ chứng minh hành động đúng.
6. **KEEP bằng code:** toàn bộ human messages và system instructions nguyên văn;
   giữ thêm AI narrative gần nhất nếu không quá 2.000 ký tự và không có tool calls.
   Instructions từ `AGENTS.md` vẫn được graph inject. Digest memory cũ được bỏ
   vì middleware nạp index hiện hành; checkpoint cũ được thay bằng checkpoint mới.
7. **SUMMARIZE:** AI/tool outputs, findings, lỗi chưa sửa, quyết định còn hiệu lực
   và các cách đã thử được thể hiện trong checkpoint. Không giữ một ToolMessage
   rời khỏi AI tool call tương ứng trong active context mới.
8. **DROP khỏi active:** raw debug lặp và các AI/tool messages cũ, sau khi đã
   đại diện trạng thái bằng checkpoint. Archive giữ nguyên nội dung gốc.
9. Chỉ ghi active mới khi checkpoint hợp lệ và serialized bytes giảm.
   Model/schema lỗi, checkpoint quá lớn hoặc không giảm kích thước: không thay context.
10. Lượt chat sau chỉ nạp active; transcript/archive phục vụ hiển thị và audit.
    Khi compact lại, model đọc checkpoint trước cùng thông tin mới rồi thay checkpoint.

Không cắt theo N tin nhắn bất kỳ. Chỉ giữ một kế hoạch AI gần nhất nếu ngắn và
không còn tool calls; giới hạn 2.000 ký tự nhằm tránh giữ lại output dài trong
đường bảo vệ này, không phải ngưỡng tối ưu đã benchmark. Checkpoint được inject
vào system prompt chính để phân biệt working state với persistent memory.
Đây là nén có mất chi tiết, không phải lossless.

## Hiệu quả đã quan sát và cách diễn giải

Demo offline dùng graph/tool thật và model có kịch bản với checkpoint chuẩn:

| Đại lượng | Trước | Sau |
|---|---:|---:|
| Active context serialized UTF-8 bytes | 57.346 | 1.751 |
| Token ước lượng, `ceil(bytes / 4)` | 14.337 | 438 |

Giảm **96,94% token ước lượng** trên fixture chứa 1.600 dòng debug lặp.
Kiểm thử kiểm tra lỗi 401, constraint API và token, thử timeout không hiệu quả,
bằng chứng `auth.py:184` / `race.log:7`, next action và archive sau restart.
Các file/dòng này thuộc **kịch bản giả lập**, không phải lỗi đã tìm thấy trong code project.

Lượt compact tiêu thụ thêm **15.458 input token ước lượng**. Lượt continuation
có **2.094 input token ước lượng**, gồm instructions và tool schemas.
Do đó giảm active context **không đồng nghĩa** tổng chi phí ngay lượt đầu giảm.
Về nguyên tắc, chỉ amortize chi phí compact khi tổng input tránh gửi lại ở
các lượt tiếp theo lớn hơn chi phí compact. Chưa benchmark điểm hòa vốn theo
provider thật, latency hoặc output tokens.

Checkpoint trong demo được model giả trả theo đáp án chuẩn. Kết quả chứng minh
việc thay context, preservation của instructions, archive và contract continuation;
**chưa chứng minh** model thật luôn chọn đúng thông tin khi tóm tắt. Sau khi được người dùng cho phép, đã chạy provider thật; xem mục kiểm chứng bên dưới.

## Khi cách chọn này kém hiệu quả

- Nhiều raw log nằm trong **human messages**: giữ nguyên user text nên khó nén.
  Nên đưa log qua B2; không âm thầm xoá nội dung người dùng để đạt số đẹp.
- Hội thoại ngắn: checkpoint + schema overhead có thể lớn hơn history; harness
  từ chối ghi nếu active không nhỏ hơn, nhưng lượt summary đã gọi vẫn có chi phí.
- History vượt cửa sổ model trước khi compact: một lượt summary không giải quyết
  được. Cần compact sớm hoặc bổ sung chunked summarization; hiện kích hoạt thủ công.
- Quyết định quan trọng chỉ có trong AI/tool output: phụ thuộc chất lượng summary.
  Schema hợp lệ không bảo đảm không bỏ sót; đã kiểm chứng một kịch bản thật, còn cần đánh giá trên nhiều task/model.
- Nhiều writer/process đồng thời: web dùng lock trong process; JSON replace tránh
  file ghi dở nhưng chưa có khóa giao dịch giữa các process CLI.
- Cần context chính xác từng byte: phải truy xuất archive; agent chưa có tool tự
  chọn đoạn archive để phục hồi. Audit hiện qua `WorkingContext.load()` hoặc file JSON.

## Vì sao B2 chọn tổng hợp trong runtime

B2 dùng **lọc + đếm chính xác + top-k + evidence giới hạn** thay vì nhờ LLM tóm tắt
raw logs. Đây là nén kết quả xử lý ở nguồn, khác với summary ngữ nghĩa của B1.

- Đọc tất cả log nằm trong capability và giới hạn, parse từng dòng rồi lọc level/
  substring. `Counter` đếm từng error_type; không sampling và không deduplicate
  trước khi đếm. Dòng lặp cũng là lần xuất hiện theo định nghĩa fixture; bỏ nó
  sẽ làm sai đáp án. Ưu điểm là count tái lập được; nhược điểm là cần quét dữ liệu
  và parser chỉ hỗ trợ format đã công bố.
- Xếp hạng theo count giảm dần, tie theo tên type để kết quả deterministic.
  Trả tối đa 5 nhóm, đồng thời giữ `groups_total`, `matched_records` và count
  của từng nhóm được trả. Giới hạn này giảm payload nhưng không trả toàn bộ
  phân bố khi có nhiều loại lỗi; người dùng cần biết các nhóm ngoài top bị lược.
- Với mỗi nhóm: giữ tổng số file, tối đa 8 tên file và 2 bằng chứng từ các file
  khác nhau, theo thứ tự tên file/dòng. Evidence giúp truy lại kết quả, không
  phải mẫu ngẫu nhiên hay chứng minh bao quát mọi biến thể thông điệp.
- Nếu không đọc được file hoặc chạm input budget, đánh dấu `complete=false`.
  Khi đó count chỉ là phần đã đọc; không được coi là kết quả toàn bộ dataset.

Không chọn sampling vì bài cần đáp án count chuẩn. Không chọn nén tự do bằng
LLM vì vẫn phải chuyển raw logs vào context và phép đếm khó kiểm chứng.
Python subset với ba capability phù hợp phạm vi hiện tại, tránh chạy code tùy ý
trong process giữ API credential; đổi lại chưa hỗ trợ phân tích tùy biến như
percentile latency, join request-id hay regex người dùng. Mở rộng phải bổ sung
API có giới hạn và tests, không mở thẳng `exec`.

Trên workload 4 log × 80, native baseline và Code Mode đều có 2 lượt model;
tổng estimated input là 21.020 và 3.922 tokens, giảm 81,34% trong demo offline.
Đó là hiệu quả của việc gửi findings thay raw output, không phải bằng chứng
Code Mode luôn rẻ hơn ở log nhỏ: tool description/schema có overhead riêng.

## Cơ sở tham khảo

[Tài liệu LangChain về short-term memory](https://github.com/langchain-ai/docs/blob/main/src/oss/langchain/short-term-memory.mdx)
mô tả trimming và summarization như các cách quản lý history. Việc chọn checkpoint
riêng ở đây nhằm đáp ứng schema, archive và kiểm tra continuation của bài tập.
[Tham chiếu trim_messages](https://reference.langchain.com/python/langchain-core/messages/utils/trim_messages)
nêu yêu cầu chuỗi message hợp lệ, bao gồm quan hệ AI/tool; đó là lý do không cắt
tùy tiện theo số message.

[Lost in the Middle](https://arxiv.org/abs/2307.03172) cho thấy trong các thí nghiệm
của bài báo, vị trí thông tin ảnh hưởng khả năng sử dụng long context. Đây chỉ là
động lực kiểm tra chất lượng continuation; không suy ra rằng compact ở project
này làm model chính xác hơn, cũng không coi kết quả đó áp dụng chắc chắn cho model đang cấu hình.

## Bổ sung sau kiểm chứng provider thật

Lần live đầu bỏ đường dẫn tests/test_refresh.py trong next_action; continuation
còn nói chưa có cách đã thử dù checkpoint có timeout. Vì vậy đã bổ sung giữ kế
hoạch AI ngắn gần nhất, yêu cầu giữ file/thứ tự hành động, không tự bịa count của
log bị lược, và đưa checkpoint vào system prompt chính. Đây là sửa theo bằng
chứng thực thi, chấp nhận tăng active context để giữ correctness. Lần chưa đạt
được lưu tại reports/challenge-b-live/attempt-before-fix.json.

Sau sửa, B1 thật giảm 14.337 xuống 462 estimated active tokens (96,78%);
continuation nêu đúng test trước, kiểm tra session lock sau, giữ constraints và
nhắc timeout không hiệu quả. Provider báo compact dùng 1.808 input tokens,
continuation dùng 2.073 input tokens. Các số provider báo không đồng nhất với
heuristic bytes/4 và chưa được đối soát tokenizer/billing độc lập.

B2 thật: baseline 23.532 input tokens, Code Mode 4.296, giảm 81,74% theo usage
provider. Code Mode trả count 400 với file/dòng đúng; baseline không cung cấp
count chính xác, nên so sánh này không phải hai đầu ra chất lượng tương đương.
Chi tiết và phản hồi nguyên văn nằm trong CHALLENGE_B_REPORT.md.

Giao diện chat cảnh báo ở 80% ngân sách demo do người dùng đặt, mặc định 8.000
token ước lượng. Đây là heuristic quan sát; không tự compact/chặn gửi và không
khẳng định đó là context limit của model.

## Lựa chọn Offline để không tốn API

Offline là phương án riêng do người dùng chọn, không giả làm LLM. Thuật toán
trích xuất theo schema và mẫu: giữ nguồn file/dòng, câu thử nghiệm thất bại và
nguyên văn next action sau marker Tiếp theo/Bước kế tiếp/Next action/Next step.
User/system instructions cùng kế hoạch gần nhất vẫn được giữ. Ưu điểm: 0 API,
tái lập được, không paraphrase làm đổi thứ tự trong kịch bản chuẩn. Nhược điểm:
chỉ hiểu cấu trúc/mẫu công bố, không thay summary ngữ nghĩa của model tổng quát.
B2 Offline chạy template read/filter/count trong runtime, không tuyên bố model
đã tự viết code. Unknown intent trả hướng dẫn hỗ trợ, không tự gọi provider.

Đặt Offline làm mặc định theo yêu cầu tiết kiệm token. Mỗi chat gắn mode riêng;
đổi sang Provider mở chat khác để usage không bị trộn. Test chặn build_model
chứng minh không có đường gọi provider ở luồng Offline. Usage 0 là số request
thực sự không phát sinh, không phải metadata provider được bịa ra. Context bar
chỉ ước lượng dung lượng giả định, không có tiền API hay model quota ẩn.
